"""
Try the draft page with no Google/Yahoo login.

Uses the real player pool and (if JEV_API_KEY is set) the real Jev, with a fake
Yahoo league that has already drafted a few players. Mock mode works as in the app.

Run from src/:
    python -m appl.draft.demo_server
then open http://localhost:5055/demo        (or /demo?auction=1 for an auction league)
"""

import os

# The routes import the Supabase config, which only checks these are set
os.environ.setdefault("SUPABASE_URL", "demo")
os.environ.setdefault("SUPABASE_KEY", "demo")

from pathlib import Path  # noqa: E402

from flask import Flask, redirect, request, session  # noqa: E402

from ..router import draft_routes  # noqa: E402
from .player_pool import load_player_pool  # noqa: E402
from .ranker import DraftRanker  # noqa: E402

STAT_CATEGORIES = ["FG%", "FT%", "3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"]
SLOTS = {"PG": 1, "SG": 1, "G": 1, "SF": 1, "PF": 1, "F": 1, "C": 1, "Util": 3}
# (player rank among the best, team index, price): team 0 is you
SALES = [(0, 3, 62), (1, 5, 55), (2, 0, 48), (3, 7, 41)]


class FakeYahooTracker:
    """A made-up Yahoo league: 12 teams with $200 each and four players already sold."""

    def __init__(self, auction: bool):
        self.auction = auction
        self.ranker = DraftRanker(load_player_pool())
        best = [r["name"] for r in self.ranker.rank(limit=len(SALES))]
        self.sales = [(best[i], team, price) for i, team, price in SALES]

    def league_info(self):
        return {
            "name": "Demo League", "num_teams": 12, "roster_size": 13,
            "is_auction": self.auction, "slots": SLOTS,
            "stat_categories": [{"display_name": c} for c in STAT_CATEGORIES],
        }

    def yahoo_ranks(self):
        return {}

    def eligible_positions(self, name):
        """Guess positions from the stat line (real leagues get them from Yahoo)."""
        player = self.ranker.find(name)
        if player is None:
            return None
        if player["REB"] >= 8:
            return {"C", "PF", "F", "Util"}
        if player["REB"] >= 5:
            return {"SF", "PF", "F", "Util"}
        if player["AST"] >= 5:
            return {"PG", "G", "Util"}
        return {"SG", "SF", "G", "F", "Util"}

    def state(self, draft_position=None):
        picks = [
            {"pick": i + 1, "round": 1, "team_key": f"t{team}", "team_name": "You" if team == 0 else f"Team {team + 1}",
             "player_name": name, "cost": price if self.auction else None, "is_mine": team == 0}
            for i, (name, team, price) in enumerate(self.sales)
        ]
        state = {
            "league_name": "Demo League", "draft_status": "draft", "is_auction": self.auction,
            "num_teams": 12, "roster_size": 13, "picks": picks,
            "taken_names": [p["player_name"] for p in picks],
            "my_roster": [p["player_name"] for p in picks if p["is_mine"]],
        }
        if self.auction:
            teams = []
            for team in range(12):
                bought = [price for _, t, price in self.sales if t == team]
                left, open_spots = 200 - sum(bought), 13 - len(bought)
                teams.append({"team_key": f"t{team}", "name": "You" if team == 0 else f"Team {team + 1}",
                              "budget_left": left, "spots_left": open_spots,
                              "max_bid": max(left - open_spots, 0), "is_mine": team == 0})
            state.update(
                teams=teams, my_budget_left=teams[0]["budget_left"], my_open_spots=teams[0]["spots_left"],
                league_budget_left=sum(t["budget_left"] for t in teams), league_budget_total=2400,
                league_spots_left=sum(t["spots_left"] for t in teams),
            )
        else:
            position = draft_position or 5
            state.update(my_next_pick=position + 12, picks_until_my_turn=position + 12 - len(picks) - 1,
                         needs_draft_position=draft_position is None)
        return state


def create_app() -> Flask:
    app = Flask(__name__, static_folder=str(Path(draft_routes.__file__).parents[1] / "static"))
    app.secret_key = "demo"

    def get_tracker(self, league_id):
        return FakeYahooTracker(auction=request.args.get("auction") == "1" or session.get("auction", False))

    draft_routes.DraftRouter._get_tracker = get_tracker
    app.register_blueprint(draft_routes.DraftRouter().get_bp())

    @app.route("/demo")
    def demo():
        session["google_user"] = {"name": "Demo"}
        session["auction"] = request.args.get("auction") == "1"
        return redirect("/draft/demo")

    return app


if __name__ == "__main__":
    create_app().run(port=5055)
