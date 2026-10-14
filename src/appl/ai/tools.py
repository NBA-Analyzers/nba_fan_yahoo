"""
The tools the chat model can call. Each wraps the deterministic season analysis,
so every number in an answer comes from code, not from the model's memory.

A Toolkit is built per request for one league (see `manual_toolkit_factory`).
"""

import json
import logging
from datetime import date

from ..season.analyzer import SeasonAnalyzer
from ..season.service import manual_id_from_chat, ranker_for, stat_line
from ..season import snapshot as snapshots
from ..season.schedule import Schedule

logger = logging.getLogger(__name__)

MAX_RESULT_CHARS = 8000

_PUNTS = {
    "type": "array",
    "items": {"type": "string"},
    "description": "Categories to ignore (punt), e.g. [\"FT%\", \"TOV\"]. Leave out to count them all.",
}


def _spec(name: str, description: str, properties: dict | None = None, required: list | None = None) -> dict:
    return {"type": "function", "function": {
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": properties or {}, "required": required or []},
    }}


TOOL_SPECS = [
    _spec("get_team_overview",
          "Your team's place in the league, your rank in every category (strong/middle/weak, "
          "the gap to the next team), your injured players, and the plain-language advice the app computed."),
    _spec("get_standings", "Every team's estimated category totals, ranks and roto points."),
    _spec("get_matchup",
          "Projected category-by-category result for this week against your head-to-head opponent, "
          "with which categories to chase and which to concede. Only available when the opponent is known.",
          {"opponent": {"type": "string", "description": "Opponent team name, if you want a different one."}}),
    _spec("suggest_pickups", "Free agents worth adding, each paired with the best player to drop.",
          {"punts": _PUNTS}),
    _spec("suggest_streamers",
          "Free agents ranked by value times games in the next 7 days (back-to-backs included).",
          {"punts": _PUNTS}),
    _spec("suggest_drops", "Your players who add least to the categories you count.", {"punts": _PUNTS}),
    _spec("suggest_trades",
          "1-for-1 and 2-for-1 trades that raise your roto points while the other team still gets fair value.",
          {"punts": _PUNTS}),
    _spec("get_team_roster",
          "A team's players with per-game stats. Defaults to your own team.",
          {"team": {"type": "string", "description": "Team name (or part of it)."}}),
    _spec("lookup_player",
          "One player's per-game stats, z-scores, injury status, games in the next 7 days, "
          "and which team (if any) rosters him.",
          {"name": {"type": "string", "description": "Player name."}}, ["name"]),
]


class Toolkit:
    def __init__(self, ranker, snapshot, schedule: Schedule | None = None, today: date | None = None):
        self.ranker = ranker
        self.snapshot = snapshot
        self.schedule = schedule
        self.today = today or date.today()
        self._analyzers: dict[tuple, SeasonAnalyzer] = {}

    @property
    def specs(self) -> list[dict]:
        return TOOL_SPECS

    # --- plumbing -----------------------------------------------------------

    def _analyzer(self, punts=None, opponent: int | None = None) -> SeasonAnalyzer:
        punts = tuple(p for p in (punts or []) if isinstance(p, str))
        key = (punts, opponent)
        if key not in self._analyzers:
            self._analyzers[key] = SeasonAnalyzer(
                self.ranker, self.snapshot, list(punts), schedule=self.schedule,
                today=self.today, opponent=opponent,
            )
        return self._analyzers[key]

    def _team_index(self, name: str | None) -> int | None:
        if not name:
            return None
        wanted = name.strip().lower()
        names = [(n or "").lower() for n in self.snapshot.team_names]
        for i, n in enumerate(names):
            if n == wanted:
                return i
        matches = [i for i, n in enumerate(names) if wanted in n]
        return matches[0] if len(matches) == 1 else None

    def call(self, name: str, arguments: dict) -> str:
        """Run a tool and return JSON text for the model. Errors come back as
        {"error": ...} so the model can recover instead of the chat failing."""
        handler = getattr(self, f"tool_{name}", None) if name in {s["function"]["name"] for s in TOOL_SPECS} else None
        if handler is None:
            result = {"error": f"Unknown tool {name}"}
        else:
            try:
                result = handler(**{k: v for k, v in arguments.items()})
            except TypeError as e:
                result = {"error": f"Bad arguments: {e}"}
            except Exception as e:
                logger.error("Chat tool %s failed: %s", name, e, exc_info=True)
                result = {"error": "The tool failed; tell the user this data is unavailable."}
        text = json.dumps(result, default=str, separators=(",", ":"))
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + '..."[truncated]"'
        return text

    # --- tools --------------------------------------------------------------

    def tool_get_team_overview(self):
        report = self._analyzer().report()
        return {
            "as_of": self.today.isoformat(),
            "league": report["league_name"],
            "my_team": report["my_team"],
            "categories": report["my_categories"],
            "advice": [a["text"] for a in report["advice"]],
            "injuries": report["injuries"],
            "players_not_found_in_stats": report["unmatched"],
        }

    def tool_get_standings(self):
        return {"as_of": self.today.isoformat(),
                "teams": sorted(self._analyzer().standings(), key=lambda t: t["place"])}

    def tool_get_matchup(self, opponent: str | None = None):
        index = self._team_index(opponent)
        if opponent and index is None:
            return {"error": f'No single team matches "{opponent}"', "teams": self.snapshot.team_names}
        return self._analyzer(opponent=index).matchup()

    def tool_suggest_pickups(self, punts=None):
        return {"pickups": self._analyzer(punts).pickups()}

    def tool_suggest_streamers(self, punts=None):
        return self._analyzer(punts).streaming()

    def tool_suggest_drops(self, punts=None):
        return {"drops": self._analyzer(punts).drops()}

    def tool_suggest_trades(self, punts=None):
        return {"trades": self._analyzer(punts).trades()}

    def tool_get_team_roster(self, team: str | None = None):
        index = self._team_index(team) if team else self.snapshot.my_team
        if index is None:
            return {"error": f'No single team matches "{team}"', "teams": self.snapshot.team_names}
        analyzer = self._analyzer()
        return {
            "team": analyzer._team_name(index),
            "is_my_team": index == self.snapshot.my_team,
            "players": [
                {"name": n, "injury": analyzer._injury(n), **stat_line(self.ranker.find(n))}
                for n in self.snapshot.rosters[index]
            ],
        }

    def tool_lookup_player(self, name: str):
        player = self.ranker.find(name)
        if player is None:
            return {"error": f'No player called "{name}" in the stats list',
                    "did_you_mean": self.ranker.suggest_names(name)}
        owner = next((self.snapshot.team_names[i] for i, r in enumerate(self.snapshot.rosters)
                      if player["name"] in r), None)
        games = None
        if self.schedule is not None and self.schedule.covers(self.today):
            games = self.schedule.games(player.get("team"), self.today)
        return {
            "name": player["name"],
            **stat_line(player),
            "z_scores": {c: round(z, 2) for c, z in (player.get("z") or {}).items()},
            "injury": self._analyzer()._injury(player["name"]),
            "games_next_7_days": games,
            "rostered_by": owner,
        }


def manual_toolkit_factory(store, schedule: Schedule | None = None):
    """Builds a Toolkit for a chat request about a manual league, else None.
    League access was already checked by the chat router."""

    def build(chat_request: dict) -> Toolkit | None:
        manual_id = manual_id_from_chat(chat_request.get("league_id"))
        user_id = chat_request.get("user_id")
        if not manual_id or not user_id:
            return None
        try:
            league = store.get(user_id, manual_id)
        except KeyError:
            return None
        snap = snapshots.from_manual(league)
        return Toolkit(ranker_for(snap), snap, schedule)

    return build
