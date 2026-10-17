"""
Getting ready for this week's head-to-head matchup. Pure, no I/O.

Where the Season page's matchup card projects a fresh seven days, this works on the
real week: what each side has scored so far (when the platform reports it) plus what
each roster is expected to add over the days that are left. From that:

  scoreboard - per category: so far, projected final, the chance of winning it, and
               whether to protect it, chase it or give it up
  days       - per remaining day: who plays, how many can start, bench conflicts and
               open slots (the days a streamer can actually play)
  streamers  - free agents who help the categories still in play, counted only on
               the days there is a slot for them
  plan       - the above turned into an ordered list of things to do
"""

import math
from datetime import date, timedelta

from ..draft.positions import FLEX_SLOT, assign, eligible_from_listed_position
from ..draft.ranker import COUNTING_STATS, NEGATIVE_CATEGORIES, PERCENT_STATS
from .analyzer import (
    DEFAULT_WEEK_GAMES, QUESTIONABLE_WEIGHT, STATS, STRONG_Z, STREAM_POOL, WEEKLY_NOISE, WEEKLY_NOISE_PCT,
    ZERO, _add, _line, _round, category_value,
)
from .snapshot import MatchWeek, week_around

PROTECT_ABOVE = 0.75  # a category I win this often is safe: don't spend moves on it
CONCEDE_BELOW = 0.25  # ... and one I win this rarely is lost: don't chase it
LEAN = 0.6  # between a toss-up and a clear result
MAX_STREAMERS = 8
DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _day_name(day: date) -> str:
    return DAY_NAMES[day.weekday()]


def _needed(category: str) -> list[str]:
    """The raw stats a category is built from."""
    return list(PERCENT_STATS[category]) if category in PERCENT_STATS else [COUNTING_STATS[category]]


def _tuple(live: dict) -> tuple:
    return tuple(float(live.get(s, 0.0)) for s in STATS)


def _verdict(p: float) -> str:
    if p >= PROTECT_ABOVE + 0.05:
        return "win"
    if p >= LEAN:
        return "lean win"
    if p > 1 - LEAN:
        return "toss-up"
    if p > 1 - PROTECT_ABOVE - 0.05:
        return "lean loss"
    return "loss"


def _stance(p: float) -> str:
    return "protect" if p > PROTECT_ABOVE else "concede" if p < CONCEDE_BELOW else "chase"


class MatchupPlanner:
    def __init__(self, analyzer, week: MatchWeek | None = None, today: date | None = None):
        self.a = analyzer
        self.today = today or analyzer.today
        self.week = week or getattr(analyzer.snapshot, "week", None) or week_around(self.today)
        self.me = analyzer.me
        self.opponent = analyzer.opponent
        self.schedule = analyzer.schedule
        self.first = max(self.today, self.week.start)
        self.rest_days = max(0, (self.week.end - self.first).days + 1)
        self.total_days = (self.week.end - self.week.start).days + 1
        self._scheduled = self.schedule is not None and self.schedule.covers(self.week.start, self.total_days)
        self._rows: list[dict] | None = None

    # --- the week's numbers --------------------------------------------------

    def _weight(self, player: dict) -> float:
        injury = self.a._injury(player["name"])
        return 0.0 if injury == "out" else QUESTIONABLE_WEIGHT if injury else 1.0

    def _games(self, player: dict, start: date, days: int) -> float:
        if days <= 0:
            return 0.0
        if self._scheduled:
            return float(self.schedule.games(player.get("team"), start, days))
        return DEFAULT_WEEK_GAMES * days / 7

    def _projection(self, team: int, start: date, days: int) -> tuple[tuple, float]:
        """A roster's summed line over `days` from `start`, and the player-games behind it."""
        total, games_total = ZERO, 0.0
        for p in self.a.players[team]:
            games = self._games(p, start, days) * self._weight(p)
            total = _add(total, tuple(x * games for x in _line(p)))
            games_total += games
        return total, games_total

    def _live(self, team: int) -> dict:
        return (getattr(self.week, "live", None) or {}).get(team) or {}

    def _known(self, category: str) -> bool:
        """True when both sides' stats so far are reported for this category."""
        needed = _needed(category)
        return all(s in self._live(t) for t in (self.me, self.opponent) for s in needed)

    def _win_prob(self, category: str, mine: float, theirs: float, week_left: float) -> float:
        """Chance I win the category. The doubt shrinks with the share of the week still to play."""
        edge = theirs - mine if category in NEGATIVE_CATEGORIES else mine - theirs
        spread = WEEKLY_NOISE_PCT if category in PERCENT_STATS else WEEKLY_NOISE * max(abs(mine), abs(theirs), 1.0)
        sigma = spread * math.sqrt(week_left)
        if sigma <= 0:
            return 1.0 if edge > 0 else 0.0 if edge < 0 else 0.5
        return 0.5 * (1 + math.erf(edge / (2 * sigma)))

    def scoreboard(self) -> list[dict]:
        if self.opponent is None:
            return []
        if self._rows is not None:
            return self._rows
        mine_rest, _ = self._projection(self.me, self.first, self.rest_days)
        theirs_rest, _ = self._projection(self.opponent, self.first, self.rest_days)
        mine_full, _ = self._projection(self.me, self.week.start, self.total_days)
        theirs_full, _ = self._projection(self.opponent, self.week.start, self.total_days)
        mine_live, theirs_live = _tuple(self._live(self.me)), _tuple(self._live(self.opponent))
        share = self.rest_days / self.total_days if self.total_days else 0.0

        rows = []
        for c in self.a.categories:
            known = self._known(c)
            if known:
                mine_total, theirs_total = _add(mine_live, mine_rest), _add(theirs_live, theirs_rest)
            else:  # nothing reliable so far: project the whole week for both sides
                mine_total, theirs_total = mine_full, theirs_full
            mine, theirs = category_value(mine_total, c), category_value(theirs_total, c)
            p = self._win_prob(c, mine, theirs, share if known else 1.0)
            punted = c in self.a.punts
            rows.append({
                "category": c,
                "known": known,
                "mine_so_far": _round(category_value(mine_live, c), c) if known else None,
                "theirs_so_far": _round(category_value(theirs_live, c), c) if known else None,
                "mine_rest": _round(category_value(mine_rest, c), c),
                "theirs_rest": _round(category_value(theirs_rest, c), c),
                "mine": _round(mine, c),
                "theirs": _round(theirs, c),
                "win_prob": round(p, 3),
                "verdict": _verdict(p),
                "stance": "punted" if punted else _stance(p),
                "punted": punted,
            })
        self._rows = rows
        return rows

    def _counted(self) -> list[dict]:
        return [r for r in self.scoreboard() if not r["punted"]]

    def _in_play(self) -> list[str]:
        """Categories that can still swing: worth a move."""
        return [r["category"] for r in self._counted() if r["stance"] == "chase"]

    def _play_value(self, player: dict) -> float:
        """What a player is worth to the categories still in play (all counted ones when none are)."""
        cats = self._in_play() or [r["category"] for r in self._counted()]
        return sum(player["z"][c] for c in cats)

    # --- days ----------------------------------------------------------------

    def _day_list(self) -> list[date]:
        return [self.first + timedelta(d) for d in range(self.rest_days)]

    def _playing(self, team: int, day: date) -> list[dict]:
        if not self._scheduled:
            return []
        return [p for p in self.a.players[team]
                if self._weight(p) > 0 and self.schedule.games(p.get("team"), day, 1)]

    def _start(self, players: list[dict]) -> int:
        eligible = [eligible_from_listed_position(p.get("pos")) or {FLEX_SLOT} for p in players]
        return assign(eligible, self.a.slots)[0]

    def days(self) -> list[dict]:
        """One row per remaining day. Empty when the schedule doesn't cover the week."""
        if self.opponent is None or not self._scheduled:
            return []
        slots = sum(self.a.slots.values())
        rows = []
        for day in self._day_list():
            mine, theirs = self._playing(self.me, day), self._playing(self.opponent, day)
            row = {"date": day.isoformat(), "day": _day_name(day), "mine": len(mine), "theirs": len(theirs),
                   "starters": None, "open_slots": None, "sit": []}
            if self.a.slots:
                started = self._start(mine)
                row["starters"] = started
                row["open_slots"] = slots - started
                row["sit"] = self._sit(mine, started)
            rows.append(row)
        return rows

    def _sit(self, playing: list[dict], started: int) -> list[str]:
        """Who to bench on a day with more players than starting spots: the ones that
        help the categories in play least, as long as the lineup stays as full."""
        extra = len(playing) - started
        if extra <= 0:
            return []
        keep = list(playing)
        sat = []
        for p in sorted(playing, key=self._play_value):
            if len(sat) == extra:
                break
            rest = [q for q in keep if q is not p]
            if self._start(rest) == started:
                keep, sat = rest, sat + [p["name"]]
        return sat

    # --- free agents ---------------------------------------------------------

    def streamers(self) -> list[dict]:
        if self.opponent is None or not self._scheduled:
            return []
        days = self._day_list()
        open_days = [d for d, row in zip(days, self.days()) if row["open_slots"] is None or row["open_slots"] > 0]
        cats = self._in_play()
        found = []
        for fa in self.a._free_agents(limit=STREAM_POOL):
            dates = [d for d in self.schedule.dates(fa.get("team"), self.first, self.rest_days) if d in open_days]
            if not dates:
                continue
            injury = self.a._injury(fa["name"])
            value = (sum(fa["z"][c] for c in cats) if cats else self.a._value(self.me, fa)) \
                * (QUESTIONABLE_WEIGHT if injury else 1.0)
            if value <= 0:
                continue
            found.append({
                "name": fa["name"], "team": fa.get("team"), "pos": fa.get("pos"), "injury": injury,
                "days": [_day_name(d) for d in dates], "games": len(dates),
                "value": round(value, 2), "score": round(value * len(dates), 2),
                "helps": [c for c in cats if fa["z"][c] >= STRONG_Z],
                "hurts": [c for c in self._counted_cats() if fa["z"][c] <= -STRONG_Z],
            })
        found.sort(key=lambda s: (s["score"], s["games"]), reverse=True)
        return found[:MAX_STREAMERS]

    def _counted_cats(self) -> list[str]:
        return [r["category"] for r in self._counted()]

    def _drop_candidate(self) -> str | None:
        """Who to make room by: an injured-out player first, else whoever helps the least."""
        roster = self.a.players[self.me]
        if not roster:
            return None
        out = [p for p in roster if self.a._injury(p["name"]) == "out"]
        return min(out or roster, key=self._play_value)["name"]

    # --- the plan ------------------------------------------------------------

    def plan(self) -> list[dict]:
        if self.opponent is None:
            return []
        tips = []
        scoreboard = {r["category"]: r for r in self._counted()}
        days, streamers = self.days(), self.streamers()

        out = [r for r in self.a.injuries() if r["status"] == "out"]
        if out:
            names = ", ".join(r["name"] for r in out)
            tips.append({"kind": "injury", "text": f"Out: {names}. Their games this week are lost: bench or "
                                                   "replace them so a slot isn't wasted."})

        for row in days:
            if row["sit"]:
                tips.append({"kind": "bench", "day": row["day"],
                             "text": f"{row['day']}: {row['mine']} of your players play but only "
                                     f"{row['starters']} can start. Sit {', '.join(row['sit'])}, "
                                     "the least help in the categories still in play."})

        open_days = [row for row in days if row["open_slots"]]
        if open_days and streamers:
            best = streamers[0]
            where = ", ".join(row["day"] for row in open_days)
            helps = f" (helps {', '.join(best['helps'])})" if best["helps"] else ""
            drop = self._drop_candidate()
            swap = f" Drop {drop} to make room." if drop else ""
            tips.append({"kind": "stream",
                         "text": f"Open slots {where}. Best stream: {best['name']}, playing "
                                 f"{', '.join(best['days'])}{helps}.{swap}"})

        for c, r in sorted(scoreboard.items(), key=lambda kv: abs(kv[1]["win_prob"] - 0.5)):
            pct = round(r["win_prob"] * 100)
            if r["stance"] == "chase":
                helper = next((s for s in streamers if c in s["helps"]), None)
                extra = f" {helper['name']} helps here." if helper else ""
                tips.append({"kind": "chase", "category": c,
                             "text": f"{c} is close ({pct}% to win). Worth a move.{extra}"})
            elif r["stance"] == "concede":
                tips.append({"kind": "concede", "category": c,
                             "text": f"{c} is out of reach ({pct}% to win). Don't spend moves on it."})
            else:
                tips.append({"kind": "protect", "category": c,
                             "text": f"You should win {c} ({pct}%). Avoid streamers that hurt it."})

        theirs_out = [p["name"] for p in self.a.players[self.opponent] if self.a._injury(p["name"]) == "out"]
        if theirs_out:
            tips.append({"kind": "opponent",
                         "text": f"{self.a._team_name(self.opponent)} is missing {', '.join(theirs_out)}."})

        if not any(r["known"] for r in self.scoreboard()):
            tips.append({"kind": "note",
                         "text": "No scores so far this week from the platform, so the whole week is projected."})
        return tips

    # --- report --------------------------------------------------------------

    def summary(self) -> dict:
        rows = self._counted()
        wins = sum(r["win_prob"] >= LEAN for r in rows)
        losses = sum(r["win_prob"] <= 1 - LEAN for r in rows)
        _, my_games = self._projection(self.me, self.first, self.rest_days)
        _, their_games = self._projection(self.opponent, self.first, self.rest_days)
        return {
            "opponent": {"index": self.opponent, "name": self.a._team_name(self.opponent)},
            "expected_wins": round(sum(r["win_prob"] for r in rows), 2),
            "record": {"wins": wins, "losses": losses, "ties": len(rows) - wins - losses},
            "categories": len(rows),
            "days_left": self.rest_days,
            "player_games_left": {"mine": round(my_games, 1), "theirs": round(their_games, 1)},
            "live": any(r["known"] for r in self.scoreboard()),
            "scheduled": self._scheduled,
        }

    def report(self) -> dict:
        week = {"number": self.week.number, "start": self.week.start.isoformat(), "end": self.week.end.isoformat(),
                "today": self.today.isoformat()}
        if self.opponent is None:
            return {"available": False, "week": week, "summary": None, "scoreboard": [], "days": [],
                    "streamers": [], "plan": []}
        return {
            "available": True,
            "week": week,
            "summary": self.summary(),
            "scoreboard": self.scoreboard(),
            "days": self.days(),
            "streamers": self.streamers(),
            "plan": self.plan(),
        }
