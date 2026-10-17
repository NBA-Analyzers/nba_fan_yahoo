"""
The whole league, for trades and the long run. Pure, no I/O.

  power_rankings   - every team by the categories it would win in a typical week against
                     each of the others (all-play), with its strong and weak spots, its
                     injured players and whether its roster is running hot or cold
  buy_sell         - players whose last two weeks are far from their season. The reason
                     decides the call: more minutes while a teammate is out, or a shooting
                     streak on the same minutes, won't last (sell high); a shooting slump on
                     the same minutes should end (buy low); more minutes with nobody out is
                     a bigger role (a breakout); fewer minutes is a shrinking role (fading)
  trade_ideas      - one of your sell-high players for a rival's buy-low player, where the
                     deal looks fair on recent form and helps you on season form
  playoff_schedule - games per player in the fantasy playoff weeks, taken to be the last
                     full Monday-to-Sunday weeks of the NBA regular season
  luck             - head-to-head only: each finished week, every team's stats against
                     every other team's (all-play). The share it would have beaten is its
                     expected win that week; luck is actual wins minus expected wins
"""

import logging
from datetime import date, timedelta
from statistics import mean, median

from ..draft.player_pool import normalize_name
from ..draft.ranker import PERCENT_STATS
from .analyzer import EPS, FAIR_MARGIN, FREE_AGENT_POOL, _better, _ranks, category_value
from .matchup_planner import _needed, _tuple
from .schedule import team_code

logger = logging.getLogger(__name__)

WINDOWS = (("last_14_days", "last 14 days"), ("last_30_days", "last 30 days"))
MIN_RECENT_GAMES = 4  # fewer games than this in a window is noise
BIG_MOVE = 1.5  # recent value (summed z) this far from the season value is a real swing
MINUTES_SHIFT = 4.0  # minutes a game up or down that signal a changed role
HOT_SHOOTING = {"FG%": 0.04, "FT%": 0.07}  # a swing this big on the same volume is luck
HOT_THREES = 1.0  # made threes a game above the season
HOT_TEAM = 1.0  # a roster whose players average this much above their season is hot
MIN_TEAM_FORMS = 3  # players with recent form needed to call a roster hot or cold
MAX_ROWS = 8
MAX_TRADE_IDEAS = 5
MOVED_CATEGORIES = 3
PLAYOFF_WEEKS = 3
LUCKY = 1.0  # wins above (or below) expected that make a team lucky (or unlucky)
_TALLY = {"win": "wins", "loss": "losses", "tie": "ties"}
MAX_PLAYOFF_FREE_AGENTS = 8

_COUNTING_KEYS = {"PTS": "pts", "REB": "reb", "AST": "ast", "STL": "stl", "BLK": "blk",
                  "TOV": "tov", "FG3M": "3pm"}
_SHOOTING_KEYS = {"FG%": ("fgm", "fga", "fg_pct"), "FT%": ("ftm", "fta", "ft_pct")}
_SHOOTING_WORDS = {"FG%": "from the field", "FT%": "from the line"}


def _pct(line: dict, category: str) -> float | None:
    made, attempts = PERCENT_STATS[category]
    return line[made] / line[attempts] if line.get(attempts) else None


def recent_line(player: dict, window: dict) -> dict:
    """A player's season line with the window's numbers in it. When the window has no
    attempts, its percentage is applied to the season's volume."""
    line = dict(player)
    for stat, key in _COUNTING_KEYS.items():
        if window.get(key) is not None:
            line[stat] = window[key]
    for category, (made_key, att_key, pct_key) in _SHOOTING_KEYS.items():
        made, attempts = PERCENT_STATS[category]
        if window.get(made_key) is not None and window.get(att_key):
            line[made], line[attempts] = window[made_key], window[att_key]
        elif window.get(pct_key) is not None:
            line[made] = player.get(attempts, 0) * window[pct_key]
    return line


def _owner(analyzer, team: int | None) -> dict | None:
    return None if team is None else {"index": team, "name": analyzer._team_name(team)}


def _listing(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


class LeagueAnalysis:
    def __init__(self, analyzer, player_data=None):
        self.a = analyzer
        self.data = player_data  # a season.player_status.PlayerData, or None
        self.n = len(analyzer.totals)
        self._reads: dict[str, dict | None] = {}
        self._owners = {p["key"]: t for t, team in enumerate(analyzer.players) for p in team}
        self._out_by_team = self._injured_by_team()

    # --- helpers ------------------------------------------------------------

    def _injured_by_team(self) -> dict[str, list[str]]:
        """NBA team -> its players who are out, from the league and the injury feed."""
        levels = dict(self.a._inj)
        if self.data is not None:
            for name, level in self.data.injury_levels().items():
                levels.setdefault(normalize_name(name), level)
        out: dict[str, list[str]] = {}
        for key, level in levels.items():
            player = self.a.ranker.find(key) if level == "out" else None
            code = team_code(player.get("team")) if player else None
            if code:
                out.setdefault(code, []).append(player["name"])
        return out

    def _value(self, z: dict) -> float:
        return sum(z[c] for c in self.a.counted)

    def _window(self, form: dict) -> tuple[dict, str] | None:
        for key, label in WINDOWS:
            window = form.get(key)
            if window and (window.get("games") or 0) >= MIN_RECENT_GAMES:
                return window, label
        return None

    def read(self, player: dict) -> dict | None:
        """How a player's recent games compare with his season, and what to make of it.
        None when there is no usable recent window or nothing much has changed."""
        if player["key"] in self._reads:
            return self._reads[player["key"]]
        self._reads[player["key"]] = row = self._read(player)
        return row

    def _read(self, player: dict) -> dict | None:
        form = self.data.form(player["name"]) if self.data is not None else None
        found = self._window(form) if form else None
        if not found:
            return None
        window, label = found
        line = recent_line(player, window)
        recent_z = self.a.ranker.z_for(line)
        season_value, recent_value = self._value(player["z"]), self._value(recent_z)
        change = recent_value - season_value
        season_min = form.get("season_min")
        minutes = (round(window["min"] - season_min, 1)
                   if window.get("min") is not None and season_min is not None else None)
        moved = sorted(((c, round(recent_z[c] - player["z"][c], 2)) for c in self.a.counted),
                       key=lambda cz: abs(cz[1]), reverse=True)
        verdict, reason = self._verdict(player, line, change, minutes)
        team = self._owners.get(player["key"])
        return {
            "name": player["name"],
            "nba_team": player.get("team"),
            "owner": _owner(self.a, team),
            "verdict": verdict,
            "reason": reason,
            "season_value": round(season_value, 2),
            "recent_value": round(recent_value, 2),
            "change": round(change, 2),
            "minutes_change": minutes,
            "games": window.get("games"),
            "window": label,
            "moved": [list(cz) for cz in moved[:MOVED_CATEGORIES] if cz[1]],
            "injury": self.a._injury(player["name"]),
        }

    def _shooting(self, player: dict, line: dict, hot: bool) -> str | None:
        """A sentence about the shooting swing behind a hot (or cold) stretch, if there is one."""
        for category, swing in HOT_SHOOTING.items():
            if category not in self.a.counted:
                continue
            now, usual = _pct(line, category), _pct(player, category)
            if now is None or usual is None:
                continue
            if (now - usual >= swing) if hot else (usual - now >= swing):
                return (f"Shooting {round(now * 100)}% {_SHOOTING_WORDS[category]} "
                        f"against {round(usual * 100)}% for the season")
        threes = line.get("FG3M", 0) - player.get("FG3M", 0)
        if hot and threes >= HOT_THREES and "3PTM" in self.a.counted:
            return f"Making {line['FG3M']:.1f} threes a game against {player['FG3M']:.1f} for the season"
        return None

    def _verdict(self, player: dict, line: dict, change: float, minutes: float | None):
        if abs(change) < BIG_MOVE:
            return None, None
        same_minutes = "on the same minutes" if minutes is not None else "(minutes unknown)"
        if change > 0:
            if minutes is not None and minutes >= MINUTES_SHIFT:
                code = team_code(player.get("team"))
                out = [n for n in self._out_by_team.get(code, []) if n != player["name"]]
                if out:
                    verb = "is" if len(out) == 1 else "are"
                    return "sell_high", f"Playing {minutes:+.1f} minutes a game while {_listing(out[:2])} {verb} out"
                return "breakout", f"Playing {minutes:+.1f} minutes a game with nobody out: a bigger role"
            shooting = self._shooting(player, line, hot=True)
            if shooting:
                return "sell_high", f"{shooting}, {same_minutes}: a streak"
            return "sell_high", f"A hot stretch {same_minutes}"
        if minutes is not None and minutes <= -MINUTES_SHIFT:
            return "fading", f"Playing {-minutes:.1f} fewer minutes a game: the role has shrunk"
        shooting = self._shooting(player, line, hot=False)
        if shooting:
            return "buy_low", f"{shooting}, {same_minutes}: a slump"
        return "buy_low", f"A cold stretch {same_minutes}: a slump"

    # --- buy low / sell high --------------------------------------------------

    def buy_sell(self) -> dict:
        a = self.a
        mine, rivals = [], []
        for team, players in enumerate(a.players):
            rows = [r for r in (self.read(p) for p in players) if r and r["verdict"]]
            (mine if team == a.me else rivals).extend(rows)
        rostered = set(self._owners)
        free = [r for r in (self.read(p) for p in a.ranker.players if p["key"] not in rostered)
                if r and r["verdict"] == "breakout" and r["recent_value"] > 0]

        def top(rows, key):
            return sorted(rows, key=key, reverse=True)[:MAX_ROWS]

        by_change = lambda r: abs(r["change"])  # noqa: E731
        return {
            "available": any(self._has_form(p) for team in a.players for p in team),
            "sell_high": top([r for r in mine if r["verdict"] == "sell_high"], by_change),
            # Yours that are hot for real, or cold for no lasting reason: keep them
            "hold": top([r for r in mine if r["verdict"] in ("breakout", "buy_low")], by_change),
            "fading": top([r for r in mine if r["verdict"] == "fading"], by_change),
                # Worth trading for: at least a typical rostered player on the season. A
            # slumping star is the best buy, so season value first
            "buy_low": top([r for r in rivals if r["verdict"] == "buy_low" and r["season_value"] >= self._typical()],
                           lambda r: r["season_value"]),
            "breakouts": top([r for r in rivals + free if r["verdict"] == "breakout"],
                             lambda r: r["recent_value"]),
        }

    def _typical(self) -> float:
        """The median rostered player's season value. Z-scores are measured against the
        players worth drafting, so a typical rostered player sits near zero, not above it."""
        values = [self._value(p["z"]) for team in self.a.players for p in team]
        return median(values) if values else 0.0

    def _has_form(self, player: dict) -> bool:
        return self.data is not None and self.data.form(player["name"]) is not None

    # --- trade ideas ----------------------------------------------------------

    def trade_ideas(self) -> list[dict]:
        """Your sell-high player for a rival's buy-low one: fair on recent form (what the
        other manager sees) and a gain for you on season form (what should come next)."""
        a = self.a
        rows = self.buy_sell()
        players = {p["name"]: p for team in a.players for p in team}
        before = a._score(a.me)
        ideas = []
        for get_row in rows["buy_low"]:
            partner = get_row["owner"]["index"]
            get = players[get_row["name"]]
            best = None
            for give_row in rows["sell_high"]:
                give = players[give_row["name"]]
                their_view = give_row["recent_value"] - get_row["recent_value"]
                if their_view < -FAIR_MARGIN or not a._keeps_lineup([give], [get]):
                    continue
                changes = {
                    a.me: tuple(m - g + t for m, g, t in zip(a.totals[a.me], a._aline(give), a._aline(get))),
                    partner: tuple(m - t + g for m, g, t in zip(a.totals[partner], a._aline(give), a._aline(get))),
                }
                gain = a._score(a.me, changes) - before
                if gain > EPS and (best is None or gain > best["gain"]):
                    best = {
                        "give": give["name"],
                        "get": get["name"],
                        "partner": get_row["owner"],
                        "gain": a._gain(gain),
                        "unit": "expected categories a week" if a.h2h else "roto points",
                        "their_view": round(their_view, 2),
                        "why": f"{give['name']}: {give_row['reason']}. {get['name']}: {get_row['reason']}.",
                    }
            if best:
                ideas.append(best)
        ideas.sort(key=lambda i: i["gain"], reverse=True)
        return ideas[:MAX_TRADE_IDEAS]

    # --- power rankings -------------------------------------------------------

    def _team_form(self, team: int) -> tuple[float | None, str | None]:
        changes = [r["change"] for r in (self.read(p) for p in self.a.players[team]) if r]
        if len(changes) < MIN_TEAM_FORMS:
            return None, None
        avg = mean(changes)
        return round(avg, 2), "hot" if avg >= HOT_TEAM else "cold" if avg <= -HOT_TEAM else "steady"

    def power_rankings(self) -> list[dict]:
        """Each team's expected categories won per week against every other team, from
        season totals with injured players discounted. Every category counts here, since
        rivals' punts are unknown."""
        a = self.a
        cats = a.categories
        ranks = {c: _ranks(a._values[c], c) for c in cats}
        rows = []
        for t in range(self.n):
            expected = sum(
                a._beat_prob(c, a._values[c][t], a._values[c][o]) for c in cats for o in range(self.n) if o != t
            ) / max(1, self.n - 1)
            by_rank = sorted(cats, key=lambda c: ranks[c][t])
            heat, label = self._team_form(t)
            rows.append({
                "index": t,
                "name": a._team_name(t),
                "is_mine": t == a.me,
                "expected_wins": round(expected, 2),
                "categories": len(cats),
                "ranks": {c: ranks[c][t] for c in cats},
                "strengths": by_rank[:2],
                "weaknesses": by_rank[-2:][::-1],
                "injured": sum(1 for p in a.players[t] if a._injury(p["name"]) == "out"),
                "form_change": heat,
                "form": label,
            })
        rows.sort(key=lambda r: r["expected_wins"], reverse=True)
        for place, row in enumerate(rows, 1):
            row["place"] = place
        return rows

    # --- the playoff schedule -------------------------------------------------

    def _playoff_weeks(self) -> list[tuple[date, date]]:
        """The last full Monday-to-Sunday weeks of the schedule that are not over yet."""
        s = self.a.schedule
        last = s.last_day() if s is not None else None
        if last is None:
            return []
        end = last - timedelta(days=(last.weekday() + 1) % 7)  # the last Sunday
        weeks = [(end - timedelta(days=6 + 7 * k), end - timedelta(days=7 * k)) for k in range(PLAYOFF_WEEKS)]
        return [(start, stop) for start, stop in reversed(weeks) if stop >= self.a.today]

    def _playoff_games(self, player: dict, weeks) -> list[int]:
        s = self.a.schedule
        games = []
        for start, end in weeks:
            first = max(start, self.a.today)
            games.append(s.games(player.get("team"), first, (end - first).days + 1))
        return games

    def playoff_schedule(self) -> dict:
        a = self.a
        weeks = self._playoff_weeks()
        if not weeks:
            return {"available": False, "weeks": [], "mine": [], "teams": [], "free_agents": []}

        def row(p):
            games = self._playoff_games(p, weeks)
            return {"name": p["name"], "nba_team": p.get("team"), "games": games, "total": sum(games),
                    "value": round(self._value(p["z"]), 2)}

        mine = sorted((row(p) for p in a.players[a.me]), key=lambda r: (r["total"], r["value"]), reverse=True)
        teams = sorted(
            ({"index": t, "name": a._team_name(t), "is_mine": t == a.me,
              "player_games": sum(sum(self._playoff_games(p, weeks)) for p in a.players[t])}
             for t in range(self.n)),
            key=lambda r: r["player_games"], reverse=True)
        # Of the best free agents, the ones who play most in the playoffs
        free = [r for r in (row(p) for p in a._free_agents(FREE_AGENT_POOL)) if r["total"]]
        free.sort(key=lambda r: (r["total"], r["value"]), reverse=True)
        return {
            "available": True,
            "weeks": [{"start": s.isoformat(), "end": e.isoformat()} for s, e in weeks],
            "mine": mine,
            "teams": teams,
            "free_agents": free[:MAX_PLAYOFF_FREE_AGENTS],
            "assumption": f"Playoffs taken to be the last {PLAYOFF_WEEKS} full weeks of the NBA regular season.",
        }

    # --- the luck index -------------------------------------------------------

    @staticmethod
    def _duel(categories: list[str], mine: dict, theirs: dict) -> tuple[int, int, int]:
        """Categories won, lost and tied by `mine` against `theirs` in one week, over the
        categories both teams have stats for."""
        a, b = _tuple(mine), _tuple(theirs)
        won = lost = tied = 0
        for c in categories:
            if not all(s in mine and s in theirs for s in _needed(c)):
                continue
            x, y = category_value(a, c), category_value(b, c)
            if _better(c, x, y):
                won += 1
            elif _better(c, y, x):
                lost += 1
            else:
                tied += 1
        return won, lost, tied

    @staticmethod
    def _outcome(won: int, lost: int) -> str:
        return "win" if won > lost else "loss" if lost > won else "tie"

    def luck(self) -> dict:
        a = self.a
        loader = getattr(a.snapshot, "history", None)
        if not a.h2h:
            return {"available": False, "reason": "The luck index is for head-to-head leagues."}
        if loader is None:
            return {"available": False, "reason": "Weekly results come from Yahoo or ESPN, so there are none for this league."}
        try:
            weeks = loader()
        except Exception as e:
            logger.warning(f"{a.snapshot.key}: weekly results unavailable: {e}")
            return {"available": False, "reason": "Couldn't read the weekly results, please try again later."}
        weeks = [w for w in weeks if w.pairs]
        if not weeks:
            return {"available": False, "reason": "The luck index starts after the first week is over."}

        cats = a.categories  # every category counts in a real matchup, whatever you punt
        empty = {"wins": 0, "losses": 0, "ties": 0}
        teams = [{"record": dict(empty), "all_play": dict(empty), "expected": 0.0, "weeks": 0} for _ in range(self.n)]
        mine = []
        for week in weeks:
            played = {t for t, line in week.lines.items() if line and 0 <= t < self.n}
            outcomes = {}  # (team, other) -> (won, lost, tied)
            for t in played:
                for o in played - {t}:
                    outcomes[(t, o)] = self._duel(cats, week.lines[t], week.lines[o])
            for t in played:
                rivals = [self._outcome(*outcomes[(t, o)][:2]) for o in played - {t}]
                if not rivals:
                    continue
                for r in rivals:
                    teams[t]["all_play"][_TALLY[r]] += 1
                teams[t]["expected"] += (rivals.count("win") + 0.5 * rivals.count("tie")) / len(rivals)
                teams[t]["weeks"] += 1
            for x, y in week.pairs:
                if x not in played or y not in played:
                    continue
                for t, o in ((x, y), (y, x)):
                    won, lost, tied = outcomes[(t, o)]
                    result = self._outcome(won, lost)
                    teams[t]["record"][_TALLY[result]] += 1
                    if t == a.me:
                        beaten = sum(self._outcome(*outcomes[(t, r)][:2]) == "win" for r in played - {t})
                        mine.append({"week": week.number, "opponent": a._team_name(o), "result": result,
                                     "categories": {"wins": won, "losses": lost, "ties": tied},
                                     "would_beat": beaten, "teams": len(played) - 1})

        rows = []
        for t, team in enumerate(teams):
            record = team["record"]
            actual = record["wins"] + 0.5 * record["ties"]
            luck = round(actual - team["expected"], 2)
            rows.append({
                "index": t,
                "name": a._team_name(t),
                "is_mine": t == a.me,
                "record": record,
                "all_play": team["all_play"],
                "expected_wins": round(team["expected"], 2),
                "luck": luck,
                "label": "lucky" if luck >= LUCKY else "unlucky" if luck <= -LUCKY else "fair",
            })
        rows.sort(key=lambda r: r["luck"], reverse=True)
        return {"available": True, "weeks": len(weeks), "teams": rows,
                "my_weeks": sorted(mine, key=lambda w: w["week"])}

    def report(self) -> dict:
        return {
            "power_rankings": self.power_rankings(),
            "buy_sell": self.buy_sell(),
            "trade_ideas": self.trade_ideas(),
            "playoffs": self.playoff_schedule(),
            "luck": self.luck(),
        }
