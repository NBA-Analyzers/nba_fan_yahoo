"""ESPN's public player-status feeds: the league-wide injury report and fantasy
ownership (percent owned / started). Neither needs a login."""

import json
import logging
from typing import Optional

from ..http import RateLimiter, with_retry

logger = logging.getLogger(__name__)

INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
OWNERSHIP_URL = (
    "https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{year}"
    "/segments/0/leaguedefaults/3"
)
OWNERSHIP_LIMIT = 700
TIMEOUT_SECONDS = 30

OUT_WORDS = ("out", "injured reserve", "suspen")
QUESTIONABLE_WORDS = ("day-to-day", "day to day", "questionable", "doubtful", "probable", "game time")


def injury_level(status: Optional[str]) -> Optional[str]:
    """ESPN's injury-report wording as "out", "questionable" or None."""
    text = str(status or "").strip().lower()
    if any(word in text for word in OUT_WORDS):
        return "out"
    if any(word in text for word in QUESTIONABLE_WORDS):
        return "questionable"
    return None


def parse_injuries(payload: dict) -> dict[str, dict]:
    """{player name: {level, status, note, date, team}} from the injury report."""
    found = {}
    for team in payload.get("injuries", []) or []:
        for row in team.get("injuries", []) or []:
            name = (row.get("athlete") or {}).get("displayName")
            level = injury_level(row.get("status"))
            if not name or not level:
                continue
            found[name] = {
                "level": level,
                "status": row.get("status"),
                "note": row.get("shortComment"),
                "date": row.get("date"),
                "team": team.get("displayName"),
            }
    return found


def parse_ownership(payload: dict) -> dict[str, dict]:
    """{player name: {percent_owned, percent_started, change}} from ESPN's fantasy player list."""
    found = {}
    for row in payload.get("players", []) or []:
        player = row.get("player") or {}
        owned = player.get("ownership") or {}
        name = player.get("fullName")
        if not name or owned.get("percentOwned") is None:
            continue
        found[name] = {
            "percent_owned": round(float(owned["percentOwned"]), 1),
            "percent_started": round(float(owned.get("percentStarted") or 0), 1),
            "change": round(float(owned.get("percentChange") or 0), 1),
        }
    return found


class EspnStatusSource:
    def __init__(self, get=None, limiter: RateLimiter | None = None, sleep=None):
        if get is None:
            import requests

            get = requests.get
        self._get = get
        self._limiter = limiter or RateLimiter(0.2)
        self._retry_kwargs = {"sleep": sleep} if sleep else {}

    def _json(self, url: str, label: str, params: dict | None = None, headers: dict | None = None) -> dict:
        all_headers = {"User-Agent": "Mozilla/5.0", **(headers or {})}

        def call():
            self._limiter.wait()
            response = self._get(url, headers=all_headers, params=params, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()

        return with_retry(call, label=label, **self._retry_kwargs)

    def injuries(self) -> dict[str, dict]:
        return parse_injuries(self._json(INJURIES_URL, "ESPN injuries"))

    def ownership(self, season_year: int, limit: int = OWNERSHIP_LIMIT) -> dict[str, dict]:
        """The `limit` most-owned players. `season_year` is the year the season ends."""
        filters = {"players": {"limit": limit, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}
        payload = self._json(
            OWNERSHIP_URL.format(year=season_year), "ESPN ownership",
            params={"view": "kona_player_info"},
            headers={"X-Fantasy-Filter": json.dumps(filters)},
        )
        return parse_ownership(payload)
