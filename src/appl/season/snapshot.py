"""
A league as it stands today: settings plus every team's current roster.

Manual leagues are rebuilt from the stored draft picks and recorded moves.
Yahoo and ESPN leagues are read live (the platform is the source of truth), cached briefly.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from ..draft.manual_league import current_rosters
from ..draft.player_pool import normalize_name
from ..draft.positions import required_slots, starting_slots
from ..draft.ranker import categories_from_yahoo, unsupported_categories

logger = logging.getLogger(__name__)

YAHOO_CACHE_SECONDS = 15 * 60
# (league_id, user) -> snapshot. Per user: `my_team` depends on who is looking.
_yahoo_cache: dict[tuple[str, str | None], tuple[float, "LeagueSnapshot"]] = {}
_espn_cache: dict[tuple[str, str | None], tuple[float, "LeagueSnapshot"]] = {}
# (snapshot key, week number) -> a finished week's results. Finished weeks don't change.
_week_cache: dict[tuple[str, int], "PastWeek"] = {}


@dataclass
class MatchWeek:
    """The week a head-to-head matchup is played in (Monday to Sunday), and what each
    team has scored in it so far. `live` maps a team index to raw stats (FGM, FGA, FTM,
    FTA, FG3M, PTS, REB, AST, STL, BLK, TOV), holding only the ones the platform reported."""
    number: int | None
    start: date
    end: date
    live: dict[int, dict[str, float]] = field(default_factory=dict)


@dataclass
class PastWeek:
    """A finished head-to-head week: each team's raw stats (as in `MatchWeek.live`) and
    who played whom, as pairs of team indexes."""
    number: int
    lines: dict[int, dict[str, float]]
    pairs: list[tuple[int, int]]


def week_around(day: date) -> MatchWeek:
    """The Monday-to-Sunday week `day` falls in, with no week number or scores."""
    start = day - timedelta(days=day.weekday())
    return MatchWeek(number=None, start=start, end=start + timedelta(days=6))


def _number(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


YAHOO_COUNTING = {"10": "FG3M", "12": "PTS", "15": "REB", "16": "AST", "17": "STL", "18": "BLK", "19": "TOV"}
YAHOO_PAIRS = {"9004003": ("FGM", "FGA"), "9007006": ("FTM", "FTA")}


def yahoo_live_line(stats: dict | None) -> dict[str, float]:
    """Raw stats from one Yahoo scoreboard team (`parse_matchups` -> `stats`, keyed by the
    stat's label). Makes and attempts arrive together as "123/250". Blank values are skipped."""
    from ..fantasy_integrations.yahoo.sync_league.sync_yahoo_league import STAT_ID_TO_NAME

    id_of = {label: stat_id for stat_id, label in STAT_ID_TO_NAME.items()}
    line: dict[str, float] = {}
    for label, value in (stats or {}).items():
        stat_id = id_of.get(label)
        if stat_id in YAHOO_PAIRS:
            made, _, attempts = str(value).partition("/")
            made, attempts = _number(made), _number(attempts)
            if made is not None and attempts is not None:
                line[YAHOO_PAIRS[stat_id][0]], line[YAHOO_PAIRS[stat_id][1]] = made, attempts
        elif stat_id in YAHOO_COUNTING:
            number = _number(value)
            if number is not None:
                line[YAHOO_COUNTING[stat_id]] = number
    return line


ESPN_LIVE_KEYS = {"PTS": "PTS", "REB": "REB", "AST": "AST", "STL": "STL", "BLK": "BLK", "TO": "TOV",
                  "3PM": "FG3M", "FGM": "FGM", "FGA": "FGA", "FTM": "FTM", "FTA": "FTA"}


def espn_live_line(cats: dict | None) -> dict[str, float]:
    """Raw stats from one ESPN matchup side (`home_team_cats` / `away_team_cats`)."""
    line: dict[str, float] = {}
    for key, entry in (cats or {}).items():
        stat = ESPN_LIVE_KEYS.get(key)
        number = _number((entry or {}).get("score")) if stat else None
        if number is not None:
            line[stat] = number
    return line


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
    scoring: str = "roto"  # "roto", "h2h" (head-to-head categories) or "points" (not analyzable)
    week: MatchWeek | None = None  # this week's dates and live scores, when the platform says
    warnings: list[str] = field(default_factory=list)  # things the analysis can't honor, for the user
    # Reads the finished weeks from the platform on first use: it costs a call per week,
    # and only the league analysis needs it. None when there are none to read (manual).
    history: Callable[[], list[PastWeek]] | None = field(default=None, repr=False, compare=False)

    @property
    def num_teams(self) -> int:
        return len(self.rosters)

    @property
    def roster_size(self) -> int:
        sizes = [len(r) for r in self.rosters if r]
        return max(sizes) if sizes else 13

    def rostered(self) -> list[str]:
        return [name for roster in self.rosters for name in roster]

    def with_injuries(self, extra: dict[str, str]) -> "LeagueSnapshot":
        """A copy with injuries from another source merged in; what the snapshot already says
        wins. A copy, because platform snapshots are cached and shared between requests."""
        known = {normalize_name(n) for n in self.injuries}
        merged = dict(self.injuries)
        for name, level in extra.items():
            if normalize_name(name) not in known:
                merged[name] = level
        return replace(self, injuries=merged)


def past_weeks(key: str, current: int | None, read_week) -> Callable[[], list[PastWeek]]:
    """A loader for weeks 1 to `current - 1`. `read_week(number)` returns a PastWeek or
    None; a week that fails is left out and tried again next time, one that worked is
    kept for good."""
    def load() -> list[PastWeek]:
        weeks = []
        for number in range(1, int(current or 1)):
            cached = _week_cache.get((key, number))
            if cached is None:
                try:
                    cached = read_week(number)
                except Exception as e:
                    logger.info(f"{key}: week {number} results unavailable: {e}")
                if cached is None:
                    continue
                _week_cache[(key, number)] = cached
            weeks.append(cached)
        return weeks

    return load


def _yahoo_past_week(league, keys: list, number: int) -> PastWeek | None:
    from ..fantasy_integrations.yahoo.sync_league.sync_yahoo_league import parse_matchups

    raw = league.matchups(number)
    scoreboard = raw["fantasy_content"]["league"][1]["scoreboard"]["0"]["matchups"]
    lines, pairs = {}, []
    for m in parse_matchups(scoreboard):
        a, b = m["team_1"]["team_key"], m["team_2"]["team_key"]
        if a not in keys or b not in keys:
            continue
        pairs.append((keys.index(a), keys.index(b)))
        for side in ("team_1", "team_2"):
            lines[keys.index(m[side]["team_key"])] = yahoo_live_line(m[side].get("stats"))
    return PastWeek(number, lines, pairs) if pairs else None


def _espn_past_week(league, teams: list, number: int) -> PastWeek | None:
    lines, pairs = {}, []
    for m in league.scoreboard(number):
        if m.home_team not in teams or m.away_team not in teams:  # a bye
            continue
        pairs.append((teams.index(m.home_team), teams.index(m.away_team)))
        for team, cats in ((m.home_team, getattr(m, "home_team_cats", None)),
                           (m.away_team, getattr(m, "away_team_cats", None))):
            lines[teams.index(team)] = espn_live_line(cats)
    return PastWeek(number, lines, pairs) if pairs else None


def scoring_from_text(text) -> str:
    """"roto", "h2h" or "points" from a platform's scoring type ("head", "headpoint",
    "H2H_CATEGORY", "ROTO", "TOTAL_POINTS" ...)."""
    code = str(text or "").lower()
    if "point" in code:
        return "points"
    if "head" in code or "h2h" in code:
        return "h2h"
    return "roto"


def _scoring_warnings(scoring: str, unsupported: list[str]) -> list[str]:
    warnings = []
    if scoring == "points":
        warnings.append("This is a points league. The app's analysis works on categories, "
                        "so its category advice is only a rough guide here.")
    if unsupported:
        warnings.append("These scored stats aren't analyzed: " + ", ".join(unsupported) + ".")
    return warnings


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
        week=week_around(date.today()),
    )


def _current_matchup(league, league_id: str, keys: list, my_key) -> tuple[int | None, MatchWeek | None]:
    """This week's opponent (index, or None) and the week with both teams' live stats.
    Anything missing leaves the week out, and the page falls back to projecting."""
    try:
        from ..fantasy_integrations.yahoo.sync_league.sync_yahoo_league import parse_matchups

        week_number = league.current_week()
        raw = league.matchups(week_number)
        scoreboard = raw["fantasy_content"]["league"][1]["scoreboard"]["0"]["matchups"]
        for m in parse_matchups(scoreboard):
            pair = [m["team_1"]["team_key"], m["team_2"]["team_key"]]
            if my_key not in pair:
                continue
            other = pair[1 - pair.index(my_key)]
            week = _yahoo_week(league, league_id, week_number)
            for side in ("team_1", "team_2"):
                team = m[side]
                if team["team_key"] in keys:
                    week.live[keys.index(team["team_key"])] = yahoo_live_line(team.get("stats"))
            return (keys.index(other) if other in keys else None), week
    except Exception as e:
        logger.info(f"League {league_id}: no head-to-head opponent found: {e}")
    return None, None


def _yahoo_week(league, league_id: str, number: int) -> MatchWeek:
    try:
        start, end = league.week_date_range(number)
        return MatchWeek(number=number, start=start, end=end)
    except Exception as e:
        logger.info(f"League {league_id}: no dates for week {number}, using the calendar week: {e}")
        week = week_around(date.today())
        week.number = number
        return week


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
    stat_categories = league.stat_categories()
    scoring = scoring_from_text(settings.get("scoring_type"))
    try:
        slots = required_slots(league.positions())
    except Exception as e:
        logger.info(f"League {league_id}: roster slots unavailable: {e}")
        slots = {}
    opponent, week = _current_matchup(league, league_id, keys, my_key)
    try:
        current = league.current_week()
    except Exception as e:
        logger.info(f"League {league_id}: current week unknown: {e}")
        current = None
    snapshot = LeagueSnapshot(
        key=f"yahoo:{league_id}",
        name=settings.get("name", league_id),
        categories=categories_from_yahoo(stat_categories),
        team_names=[teams[k].get("name", k) for k in keys],
        my_team=my_index,
        rosters=rosters,
        slots=slots,
        injuries=injuries,
        opponent=opponent,
        week=week,
        scoring=scoring,
        warnings=_scoring_warnings(scoring, unsupported_categories(stat_categories)),
        history=past_weeks(f"yahoo:{league_id}", current, lambda n: _yahoo_past_week(league, keys, n)),
    )
    _yahoo_cache[cache_key] = (now(), snapshot)
    return snapshot


def _espn_matchup(league, league_id: str, me, teams: list) -> tuple[int | None, MatchWeek | None]:
    """This week's opponent (index, or None: bye week or no matchup) and the week with
    both teams' live category scores."""
    try:
        number = league.currentMatchupPeriod
        for m in league.scoreboard(number):
            pair = [m.home_team, m.away_team]
            if me not in pair:
                continue
            other = pair[1 - pair.index(me)]
            week = week_around(date.today())
            week.number = number
            for team, cats in ((m.home_team, getattr(m, "home_team_cats", None)),
                               (m.away_team, getattr(m, "away_team_cats", None))):
                if team in teams:
                    week.live[teams.index(team)] = espn_live_line(cats)
            return (teams.index(other) if other in teams else None), week
    except Exception as e:
        logger.info(f"League {league_id}: no head-to-head opponent found: {e}")
    return None, None


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
    scoring = scoring_from_text(getattr(league.settings, "scoring_type", None))
    opponent, week = _espn_matchup(league, league_id, me, teams) if me else (None, None)
    snapshot = LeagueSnapshot(
        key=f"espn:{league_id}",
        name=getattr(league.settings, "name", None) or league_id,
        categories=info.categories(league),
        team_names=[getattr(t, "team_name", None) or f"Team {t.team_id}" for t in teams],
        my_team=teams.index(me) if me in teams else 0,
        rosters=rosters,
        slots=info.starting_slots(league),
        injuries=injuries,
        opponent=opponent,
        week=week,
        scoring=scoring,
        warnings=_scoring_warnings(scoring, info.unsupported_categories(league)),
        history=past_weeks(f"espn:{league_id}", getattr(league, "currentMatchupPeriod", None),
                           lambda n: _espn_past_week(league, teams, n)),
    )
    _espn_cache[cache_key] = (now(), snapshot)
    return snapshot
