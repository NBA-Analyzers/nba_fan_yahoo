"""
A league as it stands today: settings plus every team's current roster.

Manual leagues are rebuilt from the stored draft picks and recorded moves.
Yahoo and ESPN leagues are read live (the platform is the source of truth), cached briefly.
"""

import logging
import time
from dataclasses import dataclass, field

from ..draft.manual_league import current_rosters
from ..draft.positions import starting_slots
from ..draft.ranker import categories_from_yahoo

logger = logging.getLogger(__name__)

YAHOO_CACHE_SECONDS = 15 * 60
# (league_id, user) -> snapshot. Per user: `my_team` depends on who is looking.
_yahoo_cache: dict[tuple[str, str | None], tuple[float, "LeagueSnapshot"]] = {}
_espn_cache: dict[tuple[str, str | None], tuple[float, "LeagueSnapshot"]] = {}


@dataclass
class LeagueSnapshot:
    key: str  # stable id for caches, e.g. "manual:<id>" or "yahoo:<league key>"
    name: str
    categories: list[str]
    team_names: list[str]
    my_team: int
    rosters: list[list[str]]
    slots: dict = field(default_factory=dict)
    opponent: int | None = None  # this week's head-to-head opponent, when known
    injuries: dict[str, str] = field(default_factory=dict)  # player name -> "out" | "questionable"

    @property
    def num_teams(self) -> int:
        return len(self.rosters)

    @property
    def roster_size(self) -> int:
        sizes = [len(r) for r in self.rosters if r]
        return max(sizes) if sizes else 13

    def rostered(self) -> list[str]:
        return [name for roster in self.rosters for name in roster]


OUT_STATUSES = {"INJ", "O", "OUT", "SUSP", "IL", "IL+"}
QUESTIONABLE_STATUSES = {"GTD", "DTD", "Q", "P", "D"}


def injury_level(status) -> str | None:
    """Yahoo's player status as "out", "questionable" or None (healthy / not on a team)."""
    code = str(status or "").strip().upper()
    if code in OUT_STATUSES:
        return "out"
    if code in QUESTIONABLE_STATUSES:
        return "questionable"
    return None


def from_manual(league: dict) -> LeagueSnapshot:
    return LeagueSnapshot(
        key=f"manual:{league['id']}",
        name=league["name"],
        categories=list(league["categories"]),
        team_names=list(league["team_names"]),
        my_team=league["my_slot"] - 1,
        rosters=current_rosters(league),
        slots=starting_slots(league["slots"]) if league.get("slots") else {},
    )


def _current_opponent(league, league_id: str, keys: list, my_key) -> int | None:
    """Index of this week's opponent in a head-to-head league, or None."""
    try:
        from ..fantasy_integrations.yahoo.sync_league.sync_yahoo_league import parse_matchups

        raw = league.matchups(league.current_week())
        scoreboard = raw["fantasy_content"]["league"][1]["scoreboard"]["0"]["matchups"]
        for m in parse_matchups(scoreboard):
            pair = [m["team_1"]["team_key"], m["team_2"]["team_key"]]
            if my_key in pair:
                other = pair[1 - pair.index(my_key)]
                return keys.index(other) if other in keys else None
    except Exception as e:
        logger.info(f"League {league_id}: no head-to-head opponent found: {e}")
    return None


def from_yahoo(league, league_id: str, user: str | None = None,
               now=time.monotonic) -> LeagueSnapshot:
    """`league` is a yahoo_fantasy_api League. Reads settings and every roster.
    `user` (the viewer's Yahoo guid) keys the cache, since `my_team` is theirs."""
    cache_key = (league_id, user)
    cached = _yahoo_cache.get(cache_key)
    if cached and now() - cached[0] < YAHOO_CACHE_SECONDS:
        return cached[1]

    settings = league.settings()
    teams = league.teams()  # team_key -> {"name": ..., ...}
    my_key = next(
        (k for k, t in teams.items() if str(t.get("is_owned_by_current_login")) == "1"),
        None,
    ) or league.team_key()
    keys = sorted(teams, key=lambda k: int(str(k).rsplit(".", 1)[-1]))

    rosters = []
    injuries: dict[str, str] = {}

    def note(players):
        for p in players:
            level = injury_level(p.get("status"))
            if level and p.get("name"):
                injuries[p["name"]] = level

    for key in keys:
        try:
            players = league.to_team(key).roster()
        except Exception as e:
            logger.warning(f"League {league_id}: roster for {key} failed: {e}")
            players = []
        note(players)
        rosters.append([p["name"] for p in players if p.get("name")])

    try:
        note(league.free_agents("Util"))
    except Exception as e:
        logger.warning(f"League {league_id}: free agent injuries failed: {e}")

    my_index = keys.index(my_key) if my_key in keys else 0
    snapshot = LeagueSnapshot(
        key=f"yahoo:{league_id}",
        name=settings.get("name", league_id),
        categories=categories_from_yahoo(league.stat_categories()),
        team_names=[teams[k].get("name", k) for k in keys],
        my_team=my_index,
        rosters=rosters,
        injuries=injuries,
        opponent=_current_opponent(league, league_id, keys, my_key),
    )
    _yahoo_cache[cache_key] = (now(), snapshot)
    return snapshot


def _espn_opponent(league, league_id: str, me, teams: list) -> int | None:
    """Index of this week's opponent, or None (bye week, or no matchup found)."""
    try:
        for m in league.scoreboard(league.currentMatchupPeriod):
            pair = [m.home_team, m.away_team]
            if me in pair:
                other = pair[1 - pair.index(me)]
                return teams.index(other) if other in teams else None
    except Exception as e:
        logger.info(f"League {league_id}: no head-to-head opponent found: {e}")
    return None


def from_espn(league, league_id: str, swid: str | None = None, user: str | None = None,
              now=time.monotonic) -> LeagueSnapshot:
    """`league` is an espn_api basketball League. `swid` (the viewer's cookie) finds
    their team; without it the first team stands in. Cached per (league, user)."""
    from ..fantasy_integrations.espn import espn_league_info as info

    cache_key = (league_id, user)
    cached = _espn_cache.get(cache_key)
    if cached and now() - cached[0] < YAHOO_CACHE_SECONDS:
        return cached[1]

    teams = info.sorted_teams(league)
    injuries: dict[str, str] = {}

    def note(players):
        for p in players:
            level = info.injury_level(getattr(p, "injuryStatus", None))
            if level and getattr(p, "name", None):
                injuries[p.name] = level

    rosters = []
    for team in teams:
        players = list(getattr(team, "roster", []) or [])
        note(players)
        rosters.append([p.name for p in players if getattr(p, "name", None)])
    try:
        note(league.free_agents(size=50))
    except Exception as e:
        logger.warning(f"League {league_id}: free agent injuries failed: {e}")

    me = info.my_team(league, swid)
    snapshot = LeagueSnapshot(
        key=f"espn:{league_id}",
        name=getattr(league.settings, "name", None) or league_id,
        categories=info.categories(league),
        team_names=[getattr(t, "team_name", None) or f"Team {t.team_id}" for t in teams],
        my_team=teams.index(me) if me in teams else 0,
        rosters=rosters,
        injuries=injuries,
        opponent=_espn_opponent(league, league_id, me, teams) if me else None,
    )
    _espn_cache[cache_key] = (now(), snapshot)
    return snapshot
