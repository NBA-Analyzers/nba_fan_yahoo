"""
The tools the chat model can call. Each wraps the deterministic season analysis,
so every number in an answer comes from code, not from the model's memory.

A Toolkit is built per request for one league (see `league_toolkit_factory`), for
manual, Yahoo and ESPN leagues alike.
"""

import json
import logging
from datetime import date

from ..season import player_status, snapshot as snapshots
from ..season.analyzer import SeasonAnalyzer
from ..season.player_status import PlayerData
from ..season.schedule import Schedule
from ..season.service import manual_id_from_chat, ranker_for, stat_line

logger = logging.getLogger(__name__)

MAX_RESULT_CHARS = 8000
RISER_POOL = 60

_PUNTS = {
    "type": "array",
    "items": {"type": "string"},
    "description": "Categories to ignore (punt), e.g. [\"FT%\", \"TO\"]. Leave out to count them all.",
}


def _spec(name: str, description: str, properties: dict | None = None, required: list | None = None) -> dict:
    return {"type": "function", "function": {
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": properties or {}, "required": required or []},
    }}


TOOL_SPECS = [
    _spec("get_team_overview",
          "START HERE. Your team's place in the league, your rank in every category (strong/middle/weak, "
          "the gap to the next team), your injured players, the scoring format, data warnings and the "
          "plain-language advice the app computed."),
    _spec("get_standings", "Every team's estimated category totals, ranks and roto points."),
    _spec("get_matchup",
          "Projected category-by-category result for this week against your head-to-head opponent, "
          "with which categories to chase and which to concede. Only available when the opponent is known.",
          {"opponent": {"type": "string", "description": "Opponent team name, if you want a different one."}}),
    _spec("suggest_pickups",
          "Free agents worth adding, each paired with the best player to drop. Respects roster positions.",
          {"punts": _PUNTS}),
    _spec("suggest_streamers",
          "Free agents ranked by value times games in the next 7 days (back-to-backs included).",
          {"punts": _PUNTS}),
    _spec("find_risers",
          "Free agents whose minutes have risen most over the last 14 days versus their season average: "
          "an early sign of a bigger role."),
    _spec("suggest_drops", "Your players who add least to the categories you count.", {"punts": _PUNTS}),
    _spec("suggest_trades",
          "1-for-1 and 2-for-1 trades that raise your score while the other team still gets fair value.",
          {"punts": _PUNTS}),
    _spec("get_team_roster",
          "A team's players with per-game stats and injuries. Defaults to your own team.",
          {"team": {"type": "string", "description": "Team name (or part of it)."}}),
    _spec("lookup_player",
          "One player's per-game stats, z-scores, injury status and note, recent form (last 7/14/30 days "
          "and the minutes trend), percent owned, games left this week and this season, and which team "
          "rosters him.",
          {"name": {"type": "string", "description": "Player name."}}, ["name"]),
]


class Toolkit:
    def __init__(self, ranker, snapshot, schedule: Schedule | None = None, today: date | None = None,
                 data: PlayerData | None = None):
        self.ranker = ranker
        self.snapshot = snapshot
        self.schedule = schedule
        self.today = today or date.today()
        self.data = data or PlayerData.empty()
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

    def _scheduled(self) -> bool:
        return self.schedule is not None and self.schedule.covers(self.today)

    def _injury_info(self, name: str) -> dict | None:
        """Level from the league (or the report), plus the report's note when it has one."""
        level = self._analyzer()._injury(name)
        detail = self.data.injury(name)
        if not level and not detail:
            return None
        return {"level": level or detail["level"], "note": (detail or {}).get("note"),
                "reported": (detail or {}).get("reported")}

    def _owned(self, name: str):
        owned = self.data.ownership(name)
        return owned["percent_owned"] if owned else None

    def _decorate(self, rows: list[dict], key: str = "add") -> list[dict]:
        """Add percent owned and the injury note to rows that name a player under `key`."""
        for row in rows:
            name = row.get(key) or row.get("name")
            if name:
                row["percent_owned"] = self._owned(name)
                info = self._injury_info(name)
                if info and info.get("note"):
                    row["injury_note"] = info["note"]
        return rows

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
        analyzer = self._analyzer()
        report = analyzer.report()
        return {
            "as_of": self.today.isoformat(),
            "league": report["league_name"],
            "scoring": report["scoring"],
            "score_unit": ("expected categories won per weekly matchup" if analyzer.h2h
                           else "roto points (a point per team you beat in each category)"),
            "my_team": report["my_team"],
            "categories": report["my_categories"],
            "advice": [a["text"] for a in report["advice"]],
            "injuries": [{**r, **{k: v for k, v in (self._injury_info(r["name"]) or {}).items() if k == "note"}}
                         for r in report["injuries"]],
            "warnings": report["warnings"],
            "data_notes": {
                "injury_report_as_of": self.data.injuries_as_of,
                "ownership_as_of": self.data.ownership_as_of,
                "schedule_loaded": self._scheduled(),
            },
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
        return {"pickups": self._decorate(self._analyzer(punts).pickups())}

    def tool_suggest_streamers(self, punts=None):
        result = self._analyzer(punts).streaming()
        result["players"] = self._decorate(result["players"], key="name")
        return result

    def tool_find_risers(self):
        pool = [fa["name"] for fa in self._analyzer()._free_agents(limit=RISER_POOL)]
        risers = self.data.risers(pool)
        if not risers:
            return {"risers": [], "note": "No minutes data for free agents yet (it needs a few games "
                                          "this season), so no role changes can be spotted."}
        return {"risers": self._decorate(risers, key="name")}

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
        games = {}
        if self._scheduled():
            team = player.get("team")
            games = {
                "games_next_7_days": self.schedule.games(team, self.today),
                "games_rest_of_this_week": self.schedule.games_rest_of_week(team, self.today),
                "games_rest_of_season": self.schedule.games_remaining(team, self.today),
            }
        return {
            "name": player["name"],
            **stat_line(player),
            "z_scores": {c: round(z, 2) for c, z in (player.get("z") or {}).items()},
            "injury": self._injury_info(player["name"]),
            "recent_form": self.data.form(player["name"]),
            "percent_owned": self._owned(player["name"]),
            **games,
            "rostered_by": owner,
        }


# --- building a Toolkit for one chat request ------------------------------------

def _yahoo_snapshot(league_id: str, user_id: str):
    """The Yahoo league as the signed-in user sees it, or None when Yahoo isn't connected."""
    from flask import session

    from ..fantasy_integrations.yahoo.sync_league.yahoo_service import get_yahoo_sdk

    guid = session.get("user")
    token_store = session.get("token_store", {})
    if not guid or guid not in token_store:
        return None
    game = get_yahoo_sdk(token_store, {"user": guid})
    if game is None:
        return None
    return snapshots.from_yahoo(game.to_league(league_id), league_id, user=guid)


def league_toolkit_factory(manual_store=None, espn_service=None, schedule: Schedule | None = None,
                           yahoo_snapshot=_yahoo_snapshot, load_data=player_status.load):
    """Builds a Toolkit for a chat request about any of the user's leagues, else None
    (the chat then answers from retrieval alone). League access was already checked by
    the chat router; `user_id` comes from the signed-in session, never from the client."""

    def snapshot_for(request: dict):
        league_id, user_id = request.get("league_id"), request.get("user_id")
        if not league_id or not user_id:
            return None

        manual_id = manual_id_from_chat(league_id)
        if manual_id is not None:
            if manual_store is None:
                return None
            return snapshots.from_manual(manual_store.get(user_id, manual_id))

        from ..fantasy_integrations.espn.espn_service import espn_id_from_chat

        espn_id = espn_id_from_chat(league_id)
        if espn_id is not None:
            if espn_service is None:
                return None
            league, swid = espn_service.load_league(user_id, espn_id)
            return snapshots.from_espn(league, espn_id, swid=swid, user=user_id)

        return yahoo_snapshot(league_id, user_id)

    def build(request: dict) -> Toolkit | None:
        try:
            snap = snapshot_for(request)
        except Exception as e:  # unknown league, expired login, platform down: answer without tools
            logger.warning("Chat tools unavailable for league %s: %s", request.get("league_id"), e)
            return None
        if snap is None:
            return None
        data = load_data()
        # The nightly injury report fills in for manual leagues only. Yahoo and ESPN list every
        # injured player, so one they leave out is healthy even if the report is older and says not
        if snap.key.startswith("manual:"):
            snap = snap.with_injuries(data.injury_levels())
        return Toolkit(ranker_for(snap), snap, schedule, data=data)

    return build
