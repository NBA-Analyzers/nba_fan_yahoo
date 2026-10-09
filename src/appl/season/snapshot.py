"""
A league as it stands today: settings plus every team's current roster.

Manual leagues are rebuilt from the stored draft picks and recorded moves.
Yahoo leagues are read live (Yahoo is the source of truth), cached briefly.
"""

import logging
import time
from dataclasses import dataclass, field

from ..draft.manual_league import current_rosters
from ..draft.positions import starting_slots
from ..draft.ranker import categories_from_yahoo

logger = logging.getLogger(__name__)

YAHOO_CACHE_SECONDS = 15 * 60
_yahoo_cache: dict[str, tuple[float, "LeagueSnapshot"]] = {}


@dataclass
class LeagueSnapshot:
    key: str  # stable id for caches, e.g. "manual:<id>" or "yahoo:<league key>"
    name: str
    categories: list[str]
    team_names: list[str]
    my_team: int
    rosters: list[list[str]]
    slots: dict = field(default_factory=dict)

    @property
    def num_teams(self) -> int:
        return len(self.rosters)

    @property
    def roster_size(self) -> int:
        sizes = [len(r) for r in self.rosters if r]
        return max(sizes) if sizes else 13

    def rostered(self) -> list[str]:
        return [name for roster in self.rosters for name in roster]


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


def from_yahoo(league, league_id: str, now=time.monotonic) -> LeagueSnapshot:
    """`league` is a yahoo_fantasy_api League. Reads settings and every roster."""
    cached = _yahoo_cache.get(league_id)
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
    for key in keys:
        try:
            players = league.to_team(key).roster()
        except Exception as e:
            logger.warning(f"League {league_id}: roster for {key} failed: {e}")
            players = []
        rosters.append([p["name"] for p in players if p.get("name")])

    snapshot = LeagueSnapshot(
        key=f"yahoo:{league_id}",
        name=settings.get("name", league_id),
        categories=categories_from_yahoo(league.stat_categories()),
        team_names=[teams[k].get("name", k) for k in keys],
        my_team=keys.index(my_key) if my_key in keys else 0,
        rosters=rosters,
    )
    _yahoo_cache[league_id] = (now(), snapshot)
    return snapshot
