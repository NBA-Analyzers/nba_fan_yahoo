"""
Jev as the final chooser: picks one player from the ranker's shortlist.

The ranker does the arithmetic (Jev can't), so every player goes to Jev with
precomputed, labeled z-scores. Jev returns the pick plus a confidence and a
probability per option. If Jev is unavailable, callers fall back to the
ranker's top pick (see `decide`).

Modes:
  manual - ranking only, Jev is not called
  assist - Jev recommends, the manager decides
  auto   - Jev's pick stands when its confidence clears the threshold,
           otherwise the manager chooses between the likeliest options
"""

import hashlib
import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# JEV_API_KEY lives in src/.env, which the app's own load_dotenv does not read
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

MODES = ("manual", "assist", "auto")
MODEL = "jev-latest"
TIMEOUT_SECONDS = 8.0
# Uncalibrated starting point; tune on mock drafts before trusting auto mode
CONFIDENCE_THRESHOLD = float(os.environ.get("JEV_CONFIDENCE_THRESHOLD", "0.6"))
FAILURE_COOLDOWN_SECONDS = 30
# Mock drafts: 8 candidates gave Jev usable confidence and better teams than 25
SHORTLIST_SIZE = 8
TOP_OPTIONS = 3
MAX_PREFERENCE_CHARS = 500

INSTRUCTIONS = (
    "Which player should this fantasy basketball manager draft next? "
    "Category values are z-scores where higher is always better. "
    "Prefer players who are strong in the counted categories and who cover the "
    "roster's weakest counted categories. Ignore punted categories entirely. "
    "Follow the manager's stated preference when there is one."
)

_client = None
_cache: dict[str, dict] = {}
_failed_until = 0.0


def is_configured() -> bool:
    return bool(os.environ.get("JEV_API_KEY"))


def _get_client():
    global _client
    if _client is None:
        from typesafe_sdk import RetryPolicy, TypeSafeClient

        _client = TypeSafeClient(
            api_key=os.environ["JEV_API_KEY"],
            model=MODEL,
            timeout=TIMEOUT_SECONDS,
            retry=RetryPolicy(max_retries=1),
        )
    return _client


def _signed(value: float) -> str:
    return f"{value:+.1f}"


def _describe(rec: dict, counted: list[str]) -> dict:
    description = {
        "team": rec.get("team") or "FA",
        "games_played": rec["games_played"],
        "minutes": rec["minutes"],
        "category_z": {c: _signed(rec["z"][c]) for c in counted},
    }
    if rec.get("strengths"):
        description["strong_in"] = rec["strengths"]
    if rec.get("weaknesses"):
        description["weak_in"] = rec["weaknesses"]
    return description


def build_request(
    shortlist: list[dict],
    roster: list[str],
    punts: list[str],
    categories: list[str],
    roster_profile: dict,
    preference: str = "",
) -> tuple[dict, dict]:
    """Return (state, criteria) for the Jev call."""
    counted = [c for c in categories if c not in punts]
    state = {
        "situation": "Fantasy basketball category draft. Choose the next player.",
        "counted_categories": counted,
        "punted_categories": [c for c in punts if c in categories],
        "my_roster": roster,
    }
    if roster:
        state["roster_strength"] = {c: _signed(roster_profile[c]) for c in counted}
    if preference.strip():
        state["manager_preference"] = preference.strip()[:MAX_PREFERENCE_CHARS]

    criteria = {rec["name"]: _describe(rec, counted) for rec in shortlist}
    return state, criteria


def explain(rec: dict, roster_profile: dict, punts: list[str], has_roster: bool) -> str:
    """One plain sentence on why the player fits, from the numbers (no LLM)."""
    fixes = []
    if has_roster:
        fixes = [
            c
            for c, avg in roster_profile.items()
            if c not in punts and avg <= -0.5 and rec["z"].get(c, 0) >= 0.5
        ]
    # A category the player fixes is mentioned once, as a fix
    strengths = [
        c for c in rec.get("strengths", []) if c not in punts and c not in fixes
    ]
    parts = []
    if strengths:
        parts.append(f"strong in {', '.join(strengths)}")
    if fixes:
        parts.append(f"helps your weak {', '.join(fixes)}")
    if not parts:
        return "A balanced contributor across the categories you are counting."
    sentence = " and ".join(parts)
    return sentence[0].upper() + sentence[1:] + "."


def choose(
    shortlist: list[dict],
    roster: list[str],
    punts: list[str],
    categories: list[str],
    roster_profile: dict,
    preference: str = "",
    client=None,
) -> dict | None:
    """Ask Jev to pick from the shortlist. Returns None if Jev can't answer."""
    global _failed_until

    if len(shortlist) < 2:
        return None
    # An injected client (tests) bypasses the key check, cooldown and cache
    use_shared_state = client is None
    if use_shared_state and not is_configured():
        return None
    if use_shared_state and time.monotonic() < _failed_until:
        return None

    state, criteria = build_request(
        shortlist, roster, punts, categories, roster_profile, preference
    )
    cache_key = hashlib.sha1(
        json.dumps([state, criteria], sort_keys=True).encode()
    ).hexdigest()
    if use_shared_state and cache_key in _cache:
        return _cache[cache_key]

    try:
        from typesafe_sdk import Choice

        response = (client or _get_client()).system_one(
            state,
            {"pick": Choice(criteria=criteria, instructions=INSTRUCTIONS)},
        )
        answer = response.choices["pick"]
    except Exception as e:
        logger.error(f"Jev call failed: {e}")
        if use_shared_state:
            _failed_until = time.monotonic() + FAILURE_COOLDOWN_SECONDS
        return None

    likeliest = sorted(answer.probabilities.items(), key=lambda kv: kv[1], reverse=True)
    result = {
        "pick": answer.choice,
        "confidence": round(answer.confidence, 3),
        "options": [
            {"name": name, "probability": round(p, 3)}
            for name, p in likeliest[:TOP_OPTIONS]
        ],
    }
    if use_shared_state:
        if len(_cache) > 256:
            _cache.clear()
        _cache[cache_key] = result
    return result


def decide(
    mode: str,
    shortlist: list[dict],
    roster: list[str],
    punts: list[str],
    categories: list[str],
    roster_profile: dict,
    preference: str = "",
    client=None,
) -> dict | None:
    """The decision the page shows. None in manual mode (ranking only)."""
    if mode not in MODES or mode == "manual" or not shortlist:
        return None

    by_name = {rec["name"]: rec for rec in shortlist}
    engine_pick = shortlist[0]["name"]
    jev = choose(
        shortlist, roster, punts, categories, roster_profile, preference, client
    )

    if jev is None or jev["pick"] not in by_name:
        # Jev unavailable: the ranker's top pick stands
        return {
            "mode": mode,
            "source": "engine",
            "pick": engine_pick,
            "confidence": None,
            "options": [],
            "engine_pick": engine_pick,
            "agrees_with_engine": True,
            "needs_manager": mode == "assist",
            "reason": explain(shortlist[0], roster_profile, punts, bool(roster)),
            "note": "Jev is unavailable, showing the ranking's top pick."
            if is_configured()
            else "JEV_API_KEY is not set, showing the ranking's top pick.",
        }

    confident = jev["confidence"] >= CONFIDENCE_THRESHOLD
    return {
        "mode": mode,
        "source": "jev",
        "pick": jev["pick"],
        "confidence": jev["confidence"],
        "options": jev["options"],
        "engine_pick": engine_pick,
        "agrees_with_engine": jev["pick"] == engine_pick,
        "needs_manager": mode == "assist" or not confident,
        "reason": explain(by_name[jev["pick"]], roster_profile, punts, bool(roster)),
        "note": None
        if mode == "assist" or confident
        else f"Jev is only {jev['confidence']:.0%} sure, so you decide.",
    }
