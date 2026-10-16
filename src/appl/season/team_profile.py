"""
Your team against the league, in depth. Pure, no I/O.

  profile       - each category: where you rank, how far from the league average (in
                  standard deviations), and whether it is a strength or a weak spot
  contributions - each of your players: what they add per category, who carries you in a
                  category, who drags one down, and how many games they play this week and next
  league_grid   - your chance in a typical weekly matchup against every other team
  scouting      - each rival's strengths and weak spots, their injuries, and what you could
                  trade each other (their weakness is your strength, and the reverse)
"""

from datetime import timedelta
from statistics import mean, pstdev

from ..draft.ranker import NEGATIVE_CATEGORIES, PERCENT_STATS
from .analyzer import _ranks
from .schedule import WINDOW_DAYS
from .snapshot import week_around

DRAG_Z = -1.0  # a player this far below the average player in a category pulls it down
STRENGTH_Z = 1.0
LEAN = 0.6  # a category won this often counts as a win in the projected record
SWING = (0.35, 0.65)  # a category this close to a coin flip is up for grabs
CARRIERS_PER_CATEGORY = 1
SCOUT_PLAYERS = 3
FIT_LIMIT = 3


class TeamProfile:
    def __init__(self, analyzer, player_data=None):
        self.a = analyzer
        self.data = player_data  # a season.player_status.PlayerData, or None
        self.n = len(analyzer.totals)
        self._third = max(1, round(self.n / 3))
        self._ranks = {c: _ranks(analyzer._values[c], c) for c in analyzer.categories}

    # --- helpers ------------------------------------------------------------

    def _label(self, team: int, category: str) -> str:
        rank = self._ranks[category][team]
        return "strong" if rank <= self._third else "weak" if rank > self.n - self._third else "middle"

    def _z(self, team: int, category: str) -> float:
        """Standard deviations from the league average, positive meaning better."""
        values = self.a._values[category]
        spread = pstdev(values) or 1.0
        z = (values[team] - mean(values)) / spread
        return -z if category in NEGATIVE_CATEGORIES else z

    # --- your team ------------------------------------------------------------

    def profile(self) -> list[dict]:
        a = self.a
        rows = []
        for c in a.categories:
            digits = 3 if c in PERCENT_STATS else 1
            values = a._values[c]
            rows.append({
                "category": c,
                "punted": c in a.punts,
                "rank": self._ranks[c][a.me],
                "value": round(values[a.me], digits),
                "league_avg": round(mean(values), digits),
                "z": round(self._z(a.me, c), 2),
                "label": self._label(a.me, c),
            })
        return rows

    def _games(self, team: str | None, start, days: int):
        s = self.a.schedule
        return s.games(team, start, days) if s is not None and s.covers(start, days) else None

    def contributions(self) -> dict:
        a = self.a
        week = getattr(a.snapshot, "week", None) or week_around(a.today)
        this_start = max(a.today, week.start)
        this_days = max(0, (week.end - this_start).days + 1)
        next_start = week.end + timedelta(days=1)
        counted = a.counted
        players = []
        for p in a.players[a.me]:
            z = {c: p["z"][c] for c in a.categories}
            form = self.data.form(p["name"]) if self.data else None
            players.append({
                "name": p["name"],
                "pos": p.get("pos"),
                "team": p.get("team"),
                "injury": a._injury(p["name"]),
                "z": z,
                "value": round(sum(z[c] for c in counted), 2),
                "strengths": [c for c in counted if z[c] >= STRENGTH_Z],
                "drags": [c for c in counted if z[c] <= DRAG_Z],
                "games_this_week": self._games(p.get("team"), this_start, this_days),
                "games_next_week": self._games(p.get("team"), next_start, WINDOW_DAYS),
                "minutes_trend": form.get("minutes_trend") if form else None,
            })
        players.sort(key=lambda r: r["value"], reverse=True)
        carriers = {}
        for c in counted:
            best = sorted(players, key=lambda r: r["z"][c], reverse=True)[:CARRIERS_PER_CATEGORY]
            carriers[c] = [r["name"] for r in best if r["z"][c] > 0]
        risers = self.data.risers(a._names(a.me)) if self.data else []
        return {"players": players, "carriers": carriers, "risers": risers}

    # --- the league -----------------------------------------------------------

    def league_grid(self) -> list[dict]:
        """Chance of winning each counted category in a typical week against every other
        team, from season-long totals. Hardest matchup first."""
        a = self.a
        rows = []
        for t in range(self.n):
            if t == a.me:
                continue
            probs = {c: round(a._beat_prob(c, a._values[c][a.me], a._values[c][t]), 3) for c in a.counted}
            wins = sum(p >= LEAN for p in probs.values())
            losses = sum(p <= 1 - LEAN for p in probs.values())
            rows.append({
                "index": t,
                "name": a._team_name(t),
                "expected_wins": round(sum(probs.values()), 2),
                "record": {"wins": wins, "losses": losses, "ties": len(probs) - wins - losses},
                "categories": probs,
                "swing": [c for c, p in probs.items() if SWING[0] <= p <= SWING[1]],
            })
        rows.sort(key=lambda r: r["expected_wins"])
        return rows

    def scouting(self) -> list[dict]:
        """One card per rival: where they are strong and weak, who is hurt, and the
        categories you could trade each other for."""
        a = self.a
        cards = []
        for t in range(self.n):
            if t == a.me:
                continue
            cats = a.categories
            players = sorted(a.players[t], key=lambda p: sum(p["z"][c] for c in a.counted), reverse=True)
            cards.append({
                "index": t,
                "name": a._team_name(t),
                "ranks": {c: self._ranks[c][t] for c in cats},
                "strengths": [c for c in cats if self._label(t, c) == "strong"],
                "weaknesses": [c for c in cats if self._label(t, c) == "weak"],
                "injuries": [{"name": p["name"], "status": a._injury(p["name"])}
                             for p in a.players[t] if a._injury(p["name"])],
                "top_players": [p["name"] for p in players[:SCOUT_PLAYERS]],
                # They are weak where I am strong: what I can offer, and the reverse
                "you_offer": [c for c in a.counted
                              if self._label(t, c) == "weak" and self._label(a.me, c) == "strong"][:FIT_LIMIT],
                "you_need": [c for c in a.counted
                             if self._label(t, c) == "strong" and self._label(a.me, c) == "weak"][:FIT_LIMIT],
            })
        return cards

    def report(self) -> dict:
        return {
            "profile": self.profile(),
            "contributions": self.contributions(),
            "grid": self.league_grid(),
            "scouting": self.scouting(),
        }
