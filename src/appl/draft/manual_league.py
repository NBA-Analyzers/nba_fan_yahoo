"""
A league entered by hand, for drafting without a Yahoo connection.

The manager types in the league settings, logs each pick as it happens and adds
notes before, during and after the draft. Each league is one JSON file per user.
`ManualDraftTracker` answers the same questions as `YahooDraftTracker`, so the
ranker and the draft page work unchanged.
"""

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from .ranker import CATEGORIES
from .yahoo_draft import next_snake_pick

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "draft" / "manual"
STATUSES = ("drafting", "finished")
MAX_NOTE_LENGTH = 1000
_ID = re.compile(r"[0-9a-f]{12}")
_lock = threading.Lock()


class ManualLeagueError(ValueError):
    """Bad input from the manager; the message is safe to show them."""


def snake_team(pick_index: int, num_teams: int) -> int:
    """0-based draft slot that makes the pick at 0-based `pick_index` in a snake draft."""
    rnd, pos = divmod(pick_index, num_teams)
    return pos if rnd % 2 == 0 else num_teams - 1 - pos


def _int(raw, field, low, high, default=None):
    if raw in (None, ""):
        if default is None:
            raise ManualLeagueError(f"{field} is required")
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ManualLeagueError(f"{field} must be a number") from None
    if not low <= value <= high:
        raise ManualLeagueError(f"{field} must be between {low} and {high}")
    return value


def clean_settings(raw: dict, current: dict | None = None) -> dict:
    """Validated settings from a form. `current` supplies defaults when editing."""
    cur = current or {}
    num_teams = _int(raw.get("num_teams"), "Number of teams", 2, 30, cur.get("num_teams", 12))
    categories = raw.get("categories", cur.get("categories", CATEGORIES))
    wanted = {"STL" if str(c).strip().upper() == "ST" else str(c).strip().upper() for c in categories}
    categories = [c for c in CATEGORIES if c in wanted]
    if not categories:
        raise ManualLeagueError("Pick at least one scoring category")

    names = list(raw.get("team_names") or cur.get("team_names") or [])
    names = [str(n).strip()[:40] for n in names][:num_teams]
    names += [""] * (num_teams - len(names))
    names = [n or f"Team {i + 1}" for i, n in enumerate(names)]

    is_auction = bool(raw.get("is_auction", cur.get("is_auction", False)))
    return {
        "name": (str(raw.get("name", cur.get("name", ""))).strip() or "My league")[:60],
        "num_teams": num_teams,
        "roster_size": _int(raw.get("roster_size"), "Roster size", 1, 30, cur.get("roster_size", 13)),
        "categories": categories,
        "is_auction": is_auction,
        "budget": _int(raw.get("budget"), "Auction budget", 1, 10000, cur.get("budget", 200)),
        "my_slot": _int(raw.get("my_slot"), "Your draft slot", 1, num_teams, cur.get("my_slot", 1)),
        "team_names": names,
    }


class ManualLeagueStore:
    def __init__(self, directory: Path = DATA_DIR):
        self.directory = Path(directory)

    # --- files --------------------------------------------------------------

    def _user_dir(self, user: str) -> Path:
        return self.directory / sha256(user.encode()).hexdigest()[:16]

    def _path(self, user: str, league_id: str) -> Path:
        if not _ID.fullmatch(league_id or ""):
            raise KeyError(league_id)
        return self._user_dir(user) / f"{league_id}.json"

    def _write(self, user: str, league: dict) -> None:
        path = self._path(user, league["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(league, indent=1), encoding="utf-8")
        os.replace(tmp, path)

    # --- leagues ------------------------------------------------------------

    def list(self, user: str) -> list[dict]:
        leagues = []
        for path in self._user_dir(user).glob("*.json"):
            try:
                league = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            leagues.append(summary(league))
        return sorted(leagues, key=lambda l: l["created"], reverse=True)

    def get(self, user: str, league_id: str) -> dict:
        """Raises KeyError for an unknown league."""
        try:
            return json.loads(self._path(user, league_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise KeyError(league_id) from None

    def create(self, user: str, raw: dict) -> dict:
        league = {
            "id": uuid.uuid4().hex[:12],
            "created": _now(),
            "status": "drafting",
            "picks": [],
            "notes": [],
            **clean_settings(raw),
        }
        with _lock:
            self._write(user, league)
        return league

    def delete(self, user: str, league_id: str) -> None:
        with _lock:
            self._path(user, league_id).unlink(missing_ok=True)

    def _modify(self, user: str, league_id: str, change) -> dict:
        with _lock:
            league = self.get(user, league_id)
            change(league)
            self._write(user, league)
        return league

    def update_settings(self, user: str, league_id: str, raw: dict) -> dict:
        def change(league):
            new = clean_settings(raw, league)
            if league["picks"]:
                if new["is_auction"] != league["is_auction"]:
                    raise ManualLeagueError("Can't switch snake/auction after picks are logged")
                if any(p["team"] >= new["num_teams"] for p in league["picks"]):
                    raise ManualLeagueError("A logged pick belongs to a team that would no longer exist")
            league.update(new)

        return self._modify(user, league_id, change)

    def set_status(self, user: str, league_id: str, status: str) -> dict:
        if status not in STATUSES:
            raise ManualLeagueError("Unknown status")
        return self._modify(user, league_id, lambda league: league.update(status=status))

    # --- picks --------------------------------------------------------------

    def add_pick(self, user: str, league_id: str, player_name: str, team=None, cost=None) -> dict:
        """Log the next pick. Snake picks go to whoever is on the clock unless `team`
        (1-based) says otherwise; auction picks need a team and a price."""
        player_name = str(player_name or "").strip()[:80]
        if not player_name:
            raise ManualLeagueError("Enter a player's name")

        def change(league):
            n = league["num_teams"]
            if any(p["player_name"].lower() == player_name.lower() for p in league["picks"]):
                raise ManualLeagueError(f"{player_name} was already picked")
            if league["is_auction"]:
                idx = _int(team, "Team", 1, n) - 1
                price = _int(cost, "Price", 0, league["budget"])
            else:
                idx = _int(team, "Team", 1, n, 0) - 1 if team not in (None, "") else snake_team(len(league["picks"]), n)
                price = None
            league["picks"].append({"team": idx, "player_name": player_name, "cost": price})

        return self._modify(user, league_id, change)

    def undo_pick(self, user: str, league_id: str) -> dict:
        def change(league):
            if not league["picks"]:
                raise ManualLeagueError("No picks to undo")
            league["picks"].pop()

        return self._modify(user, league_id, change)

    # --- notes --------------------------------------------------------------

    def add_note(self, user: str, league_id: str, text: str) -> dict:
        text = str(text or "").strip()[:MAX_NOTE_LENGTH]
        if not text:
            raise ManualLeagueError("Write something first")

        def change(league):
            league["notes"].append({
                "id": uuid.uuid4().hex[:8],
                "ts": _now(),
                # Before the first pick, during the draft, or after it was marked finished
                "phase": "after" if league["status"] == "finished"
                else ("before" if not league["picks"] else "during"),
                "pick_count": len(league["picks"]),
                "text": text,
            })

        return self._modify(user, league_id, change)

    def delete_note(self, user: str, league_id: str, note_id: str) -> dict:
        return self._modify(
            user, league_id,
            lambda league: league.update(notes=[n for n in league["notes"] if n["id"] != note_id]),
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def summary(league: dict) -> dict:
    return {
        "id": league["id"], "name": league["name"], "created": league["created"],
        "status": league["status"], "is_auction": league["is_auction"],
        "num_teams": league["num_teams"], "picks": len(league["picks"]),
        "total_picks": league["num_teams"] * league["roster_size"],
    }


class ManualDraftTracker:
    """Same interface the draft routes use on YahooDraftTracker, backed by a stored league."""

    def __init__(self, league: dict):
        self.league = league
        self.league_id = league["id"]

    @property
    def cache_key(self) -> str:
        """Rankers are cached per key; any scoring-relevant setting change makes a new one."""
        lg = self.league
        return f"manual:{lg['id']}:{lg['num_teams']}:{lg['roster_size']}:{','.join(lg['categories'])}"

    def league_info(self) -> dict:
        lg = self.league
        return {
            "name": lg["name"],
            "num_teams": lg["num_teams"],
            "roster_size": lg["roster_size"],
            "is_auction": lg["is_auction"],
            "draft_status": lg["status"],
            "stat_categories": [{"display_name": c} for c in lg["categories"]],
            "slots": {},
        }

    def yahoo_ranks(self) -> dict:
        return {}

    def state(self, draft_position: int | None = None) -> dict:
        lg = self.league
        n, size = lg["num_teams"], lg["roster_size"]
        mine = lg["my_slot"] - 1
        names = lg["team_names"]

        picks, rosters = [], [[] for _ in range(n)]
        for i, p in enumerate(lg["picks"]):
            picks.append({
                "pick": i + 1,
                "round": i // n + 1,
                "team_key": f"t{p['team']}",
                "team_name": names[p["team"]],
                "player_name": p["player_name"],
                "cost": p["cost"],
                "is_mine": p["team"] == mine,
            })
            rosters[p["team"]].append({"name": p["player_name"], "cost": p["cost"]})

        total_picks = n * size
        state = {
            "league_name": lg["name"],
            "draft_status": lg["status"],
            "is_auction": lg["is_auction"],
            "num_teams": n,
            "roster_size": size,
            "picks": picks,
            "taken_names": [p["player_name"] for p in picks],
            "my_roster": [p["player_name"] for p in picks if p["is_mine"]],
            "manual": {
                "settings": {k: lg[k] for k in (
                    "name", "num_teams", "roster_size", "categories", "is_auction",
                    "budget", "my_slot", "team_names")},
                "status": lg["status"],
                "notes": lg["notes"],
                "total_picks": total_picks,
                "complete": len(picks) >= total_picks,
                "rosters": [
                    {"index": i, "name": names[i], "is_mine": i == mine, "players": rosters[i]}
                    for i in range(n)
                ],
            },
        }

        if lg["is_auction"]:
            teams = []
            for i in range(n):
                left = lg["budget"] - sum(r["cost"] or 0 for r in rosters[i])
                open_spots = max(size - len(rosters[i]), 0)
                teams.append({
                    "team_key": f"t{i}", "name": names[i], "budget_left": left,
                    "spots_left": open_spots,
                    "max_bid": max(left - open_spots, 0) if open_spots else 0,
                    "is_mine": i == mine,
                })
            state.update(
                teams=teams,
                my_budget_left=teams[mine]["budget_left"],
                my_open_spots=teams[mine]["spots_left"],
                league_budget_left=sum(t["budget_left"] for t in teams),
                league_budget_total=n * lg["budget"],
                league_spots_left=sum(t["spots_left"] for t in teams),
            )
        else:
            next_pick = next_snake_pick(len(picks), n, lg["my_slot"])
            state.update(
                needs_draft_position=False,
                my_next_pick=next_pick,
                picks_until_my_turn=next_pick - len(picks) - 1,
            )
            if len(picks) < total_picks:
                clock = snake_team(len(picks), n)
                state["manual"]["on_the_clock"] = {"index": clock, "name": names[clock]}
        return state


def user_key(google_user: dict | None) -> str:
    """Stable id for the logged-in Google user (same field the chat access check uses)."""
    google_user = google_user or {}
    return str(google_user.get("sub") or google_user.get("email") or google_user.get("name") or "anonymous")
