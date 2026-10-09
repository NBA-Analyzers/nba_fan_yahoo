"""
A league entered by hand, for drafting without a Yahoo connection.

The manager types in the league settings, logs each pick as it happens and adds
notes before, during and after the draft. After the draft, adds, drops and trades
are recorded as moves, so the rosters stay current for the season analysis.
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

from .positions import clean_slots, roster_size as slots_roster_size, starting_slots
from .ranker import CATEGORIES
from .yahoo_draft import next_snake_pick

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "draft" / "manual"
STATUSES = ("drafting", "finished")
MAX_NOTE_LENGTH = 1000
_ID = re.compile(r"[0-9a-f]{12}")
_lock = threading.RLock()


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

    # Roster spots by position. When they are given, they decide the roster size;
    # leagues made before this existed keep a plain roster size and no position checks.
    slots = cur.get("slots")
    if raw.get("slots") is not None:
        try:
            slots = clean_slots(raw["slots"], cur.get("slots"))
        except ValueError as e:
            raise ManualLeagueError(str(e)) from None
        if not 1 <= slots_roster_size(slots) <= 30:
            raise ManualLeagueError("A team needs between 1 and 30 roster spots (the injured list doesn't count)")
    roster_size = (
        slots_roster_size(slots) if slots
        else _int(raw.get("roster_size"), "Roster size", 1, 30, cur.get("roster_size", 13))
    )

    is_auction = bool(raw.get("is_auction", cur.get("is_auction", False)))
    return {
        "name": (str(raw.get("name", cur.get("name", ""))).strip() or "My league")[:60],
        "num_teams": num_teams,
        "roster_size": roster_size,
        "slots": slots,
        "categories": categories,
        "is_auction": is_auction,
        "budget": _int(raw.get("budget"), "Auction budget", 1, 10000, cur.get("budget", 200)),
        "my_slot": _int(raw.get("my_slot"), "Your draft slot", 1, num_teams, cur.get("my_slot", 1)),
        "team_names": names,
    }


def user_hash(user: str) -> str:
    """Folder or document name for a user, so raw ids (emails) stay out of paths."""
    return sha256(user.encode()).hexdigest()[:16]


class FileBackend:
    """One JSON file per league: <directory>/<user>/<id>.json.

    Fine for local development. A Cloud Run container's disk is wiped on every
    restart, so deployed apps use FirestoreBackend instead.
    """

    def __init__(self, directory: Path = DATA_DIR):
        self.directory = Path(directory)

    def _user_dir(self, user: str) -> Path:
        return self.directory / user_hash(user)

    def _path(self, user: str, league_id: str) -> Path:
        return self._user_dir(user) / f"{league_id}.json"

    def read(self, user: str, league_id: str) -> dict:
        try:
            return json.loads(self._path(user, league_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise KeyError(league_id) from None

    def write(self, user: str, league: dict) -> None:
        with _lock:
            path = self._path(user, league["id"])
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(league, indent=1), encoding="utf-8")
            os.replace(tmp, path)

    def list(self, user: str) -> list[dict]:
        leagues = []
        for path in self._user_dir(user).glob("*.json"):
            try:
                leagues.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return leagues

    def delete(self, user: str, league_id: str) -> None:
        with _lock:
            self._path(user, league_id).unlink(missing_ok=True)

    def modify(self, user: str, league_id: str, change) -> dict:
        """Read, apply `change(league)`, write. If `change` raises, nothing is saved."""
        with _lock:
            league = self.read(user, league_id)
            change(league)
            self.write(user, league)
        return league


class FirestoreBackend:
    """Layout: <root>/<user hash>/leagues/<league id> -> the league as one document.

    Survives Cloud Run restarts and redeploys. Changes run in a Firestore
    transaction, so two requests can't overwrite each other's picks, even with
    more than one instance. The client is created on first use, so building the
    backend needs no credentials.
    """

    def __init__(self, client=None, root: str = "manual_leagues", transactional=None):
        self._client_obj = client
        self.root = root
        self._transactional = transactional

    def _client(self):
        if self._client_obj is None:
            from google.cloud import firestore

            self._client_obj = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"))
        return self._client_obj

    def _leagues(self, user: str):
        return self._client().collection(self.root).document(user_hash(user)).collection("leagues")

    def read(self, user: str, league_id: str) -> dict:
        snap = self._leagues(user).document(league_id).get()
        if not snap.exists:
            raise KeyError(league_id)
        return snap.to_dict()

    def write(self, user: str, league: dict) -> None:
        self._leagues(user).document(league["id"]).set(league)

    def list(self, user: str) -> list[dict]:
        return [snap.to_dict() for snap in self._leagues(user).stream()]

    def delete(self, user: str, league_id: str) -> None:
        self._leagues(user).document(league_id).delete()

    def modify(self, user: str, league_id: str, change) -> dict:
        """Read, apply `change(league)`, write, all in one transaction. If `change`
        raises, nothing is saved. Firestore may re-run it on contention, so `change`
        must only depend on the league it is given."""
        transactional = self._transactional
        if transactional is None:
            from google.cloud import firestore

            transactional = firestore.transactional
        ref = self._leagues(user).document(league_id)

        def run(transaction):
            snap = ref.get(transaction=transaction)
            if not snap.exists:
                raise KeyError(league_id)
            league = snap.to_dict()
            change(league)
            transaction.set(ref, league)
            return league

        return transactional(run)(self._client().transaction())


class ManualLeagueStore:
    def __init__(self, directory: Path = DATA_DIR, backend=None):
        self.backend = backend or FileBackend(directory)

    @staticmethod
    def _check(league_id: str) -> None:
        if not _ID.fullmatch(league_id or ""):
            raise KeyError(league_id)

    # --- leagues ------------------------------------------------------------

    def list(self, user: str) -> list[dict]:
        leagues = []
        for league in self.backend.list(user):
            try:
                leagues.append(summary(league))
            except (KeyError, TypeError):
                continue  # a malformed record shouldn't hide the others
        return sorted(leagues, key=lambda l: l["created"], reverse=True)

    def get(self, user: str, league_id: str) -> dict:
        """Raises KeyError for an unknown league."""
        self._check(league_id)
        return self.backend.read(user, league_id)

    def create(self, user: str, raw: dict) -> dict:
        league = {
            "id": uuid.uuid4().hex[:12],
            "created": _now(),
            "status": "drafting",
            "picks": [],
            "notes": [],
            "moves": [],
            **clean_settings(raw),
        }
        self.backend.write(user, league)
        return league

    def delete(self, user: str, league_id: str) -> None:
        self._check(league_id)
        self.backend.delete(user, league_id)

    def _modify(self, user: str, league_id: str, change) -> dict:
        self._check(league_id)
        return self.backend.modify(user, league_id, change)

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

    @staticmethod
    def _clean_pick(league: dict, player_name, team, cost, position: int, skip: int | None = None) -> dict:
        """A validated pick for 0-based `position`. `skip` is the pick being edited,
        which doesn't count as a duplicate of itself."""
        player_name = str(player_name or "").strip()[:80]
        if not player_name:
            raise ManualLeagueError("Enter a player's name")
        n = league["num_teams"]
        done = next(
            (i for i, p in enumerate(league["picks"]) if i != skip and p["player_name"].lower() == player_name.lower()),
            None,
        )
        if done is not None:
            team_idx = league["picks"][done]["team"]
            by = league["team_names"][team_idx] if team_idx < len(league["team_names"]) else f"Team {team_idx + 1}"
            raise ManualLeagueError(f"{player_name} was already picked (pick #{done + 1}, {by})")
        if league["is_auction"]:
            idx = _int(team, "Team", 1, n) - 1
            price = _int(cost, "Price", 0, league["budget"])
        else:
            idx = _int(team, "Team", 1, n, 0) - 1 if team not in (None, "") else snake_team(position, n)
            price = None
        return {"team": idx, "player_name": player_name, "cost": price}

    def add_pick(self, user: str, league_id: str, player_name: str, team=None, cost=None) -> dict:
        """Log the next pick. Snake picks go to whoever is on the clock unless `team`
        (1-based) says otherwise; auction picks need a team and a price."""
        def change(league):
            league["picks"].append(self._clean_pick(league, player_name, team, cost, len(league["picks"])))

        return self._modify(user, league_id, change)

    @staticmethod
    def _pick_index(league: dict, number: int) -> int:
        if not 1 <= number <= len(league["picks"]):
            raise ManualLeagueError(f"There is no pick #{number}")
        return number - 1

    def edit_pick(self, user: str, league_id: str, number: int, player_name, team=None, cost=None) -> dict:
        """Correct any logged pick (1-based `number`): the player, the team or the price."""
        def change(league):
            i = self._pick_index(league, number)
            league["picks"][i] = self._clean_pick(league, player_name, team, cost, i, skip=i)

        return self._modify(user, league_id, change)

    def delete_pick(self, user: str, league_id: str, number: int) -> dict:
        """Remove any logged pick. Later picks keep their teams and prices but move up a number."""
        def change(league):
            league["picks"].pop(self._pick_index(league, number))

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

    # --- moves after the draft (adds, drops, trades) -------------------------

    def add_move(self, user: str, league_id: str, raw: dict) -> dict:
        """Record a roster change. Raises ManualLeagueError if it doesn't fit the
        current rosters (dropping a player the team doesn't have, and so on)."""
        def change(league):
            move = _clean_move(league, raw)
            rosters = current_rosters(league)
            _apply_move(rosters, move, league["team_names"], strict=True)
            league.setdefault("moves", []).append(move)

        return self._modify(user, league_id, change)

    def delete_move(self, user: str, league_id: str, move_id: str) -> dict:
        """Remove a recorded move, unless a later move depends on it."""
        def change(league):
            remaining = [m for m in league.get("moves", []) if m["id"] != move_id]
            if len(remaining) == len(league.get("moves", [])):
                raise ManualLeagueError("That move doesn't exist")
            rosters = draft_rosters(league)
            for move in remaining:
                try:
                    _apply_move(rosters, move, league["team_names"], strict=True)
                except ManualLeagueError:
                    raise ManualLeagueError(
                        "A later move depends on this one; delete that one first"
                    ) from None
            league["moves"] = remaining

        return self._modify(user, league_id, change)


MOVE_KINDS = ("add", "drop", "trade")
MAX_MOVE_PLAYERS = 5


def _names(raw) -> list[str]:
    if isinstance(raw, str):
        raw = raw.split(",")
    names = [str(n).strip()[:80] for n in (raw or [])]
    return [n for n in names if n][:MAX_MOVE_PLAYERS]


def _clean_move(league: dict, raw: dict) -> dict:
    kind = raw.get("kind")
    if kind not in MOVE_KINDS:
        raise ManualLeagueError("Choose add, drop or trade")
    n = league["num_teams"]
    team = _int(raw.get("team"), "Team", 1, n, league["my_slot"]) - 1
    add, drop = _names(raw.get("add")), _names(raw.get("drop"))
    move = {"id": uuid.uuid4().hex[:8], "ts": _now(), "kind": kind, "team": team,
            "add": add, "drop": drop}
    if kind == "add" and not add:
        raise ManualLeagueError("Name the player who was picked up")
    if kind == "drop" and (add or not drop):
        raise ManualLeagueError("Name the player who was dropped")
    if kind == "trade":
        partner = _int(raw.get("partner"), "Trade partner", 1, n) - 1
        if partner == team:
            raise ManualLeagueError("A team can't trade with itself")
        if not add or not drop:
            raise ManualLeagueError("A trade needs players going both ways")
        move["partner"] = partner
    return move


def _team_name(names: list[str], index: int) -> str:
    return names[index] if index < len(names) else f"Team {index + 1}"


def _apply_move(rosters: list[list[str]], move: dict, team_names: list[str], strict: bool) -> None:
    """Change `rosters` in place. strict: refuse moves that don't fit (for new
    moves); otherwise apply what still fits (replaying after picks were edited)."""
    def owner(name):
        low = name.lower()
        return next((i for i, r in enumerate(rosters) if any(p.lower() == low for p in r)), None)

    def remove(team, name):
        low = name.lower()
        rosters[team][:] = [p for p in rosters[team] if p.lower() != low]

    team = move["team"]
    if team >= len(rosters):
        if strict:
            raise ManualLeagueError("That team no longer exists")
        return

    if move["kind"] == "trade":
        partner = move.get("partner", -1)
        if not 0 <= partner < len(rosters):
            if strict:
                raise ManualLeagueError("That team no longer exists")
            return
        give, get = move["drop"], move["add"]
        if strict:
            for name in give:
                if owner(name) != team:
                    raise ManualLeagueError(f"{_team_name(team_names, team)} doesn't have {name}")
            for name in get:
                if owner(name) != partner:
                    raise ManualLeagueError(f"{_team_name(team_names, partner)} doesn't have {name}")
        for name in give:
            if owner(name) == team:
                remove(team, name)
                rosters[partner].append(name)
        for name in get:
            if owner(name) == partner:
                remove(partner, name)
                rosters[team].append(name)
        return

    for name in move["drop"]:
        if owner(name) != team:
            if strict:
                raise ManualLeagueError(f"{_team_name(team_names, team)} doesn't have {name}")
            continue
        remove(team, name)
    for name in move["add"]:
        held = owner(name)
        if held is not None:
            if strict:
                raise ManualLeagueError(f"{name} is already on {_team_name(team_names, held)}")
            continue
        rosters[team].append(name)


def draft_rosters(league: dict) -> list[list[str]]:
    """Each team's players as drafted (index = 0-based team)."""
    rosters = [[] for _ in range(league["num_teams"])]
    for p in league["picks"]:
        if p["team"] < len(rosters):
            rosters[p["team"]].append(p["player_name"])
    return rosters


def current_rosters(league: dict) -> list[list[str]]:
    """Each team's players today: the draft plus every recorded move."""
    rosters = draft_rosters(league)
    for move in league.get("moves", []):
        _apply_move(rosters, move, league["team_names"], strict=False)
    return rosters


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
            "slots": starting_slots(lg["slots"]) if lg.get("slots") else {},
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
                    "budget", "my_slot", "team_names")} | {"slots": lg.get("slots")},
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


def default_store() -> ManualLeagueStore:
    """Firestore on Cloud Run (which sets K_SERVICE), files everywhere else.
    Override with MANUAL_LEAGUE_STORE=firestore or =file."""
    kind = os.environ.get("MANUAL_LEAGUE_STORE") or ("firestore" if os.environ.get("K_SERVICE") else "file")
    if kind == "firestore":
        return ManualLeagueStore(backend=FirestoreBackend())
    return ManualLeagueStore()
