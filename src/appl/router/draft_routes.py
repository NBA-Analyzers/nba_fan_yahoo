import logging

from flask import (
    Blueprint,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
)

from ..draft import jev_chooser, positions
from ..draft.manual_league import (
    ManualDraftTracker,
    ManualLeagueError,
    ManualLeagueStore,
    user_key,
)
from ..draft.player_pool import load_player_pool
from ..draft.ranker import DraftRanker, categories_from_yahoo
from ..draft.yahoo_draft import (
    DEFAULT_AUCTION_BUDGET,
    YahooDraftTracker,
)
from ..fantasy_integrations.yahoo.sync_league.yahoo_service import get_yahoo_sdk
from ..middleware.auth_decorators import require_google_auth

logger = logging.getLogger(__name__)

# league_id -> DraftRanker; the ranking baseline only depends on league settings
_rankers: dict[str, DraftRanker] = {}


def _mock_auction_state(info: dict, taken: list, mine: list, costs) -> dict:
    """Budgets for a hand-run mock auction: everyone starts with the default budget
    and only the prices the manager typed in are spent."""
    costs = {k: int(v) for k, v in (costs or {}).items() if str(v).lstrip("-").isdigit()}
    total = info["num_teams"] * DEFAULT_AUCTION_BUDGET
    return {
        "league_budget_total": total,
        "league_budget_left": total - sum(costs.get(n, 0) for n in taken),
        "my_budget_left": DEFAULT_AUCTION_BUDGET - sum(costs.get(n, 0) for n in mine),
        "my_open_spots": max(info["roster_size"] - len(mine), 0),
        "league_spots_left": max(info["num_teams"] * info["roster_size"] - len(taken), 0),
        "teams": [],
    }


def _position_report(tracker, info: dict, mine: list) -> dict | None:
    """Which starting slots the roster can't fill yet (warn-only). None if the
    league's slots or the players' eligibility aren't available."""
    slots = info.get("slots")
    if not slots or not hasattr(tracker, "eligible_positions"):
        return None
    eligible = [tracker.eligible_positions(name) for name in mine]
    report = positions.roster_report([e or {positions.FLEX_SLOT} for e in eligible], slots)
    report["incomplete"] = any(e is None for e in eligible)
    return report


def _nominee_card(nominee, tracker, ranker, info, state, plan, punts, taken, mine) -> dict | None:
    """Everything the manager needs while a player is on the block."""
    if not nominee or not state["is_auction"]:
        return None
    player = ranker.find(nominee)
    if player is None:
        return {"query": nominee, "found": False}

    name = player["name"]
    card = {"query": nominee, "found": True, "name": name, "team": player["team"]}

    sale = next((p for p in state.get("picks", []) if ranker.resolve_key(p["player_name"]) == player["key"]), None)
    if sale or ranker.resolve_key(name) in {ranker.resolve_key(t) for t in taken}:
        card.update(sold=True, sold_to=sale["team_name"] if sale else None,
                    cost=sale["cost"] if sale else None)
        return card

    ranked = ranker.rank(punts=punts, taken_names=taken, my_roster_names=mine, limit=len(ranker.players))
    rec = next((r for r in ranked if r["name"] == name), None)
    my_value, market = plan["mine"].get(name, 1), plan["market"].get(name, 1)
    max_bid = plan["max_bid"]
    avg_cost = ranker.yahoo_ranks.get(player["key"], {}).get("avg_cost")

    if my_value >= market:
        verdict = "target"      # worth at least what the room will pay
    elif my_value >= 0.8 * market:
        verdict = "fair"
    else:
        verdict = "overpriced"  # the room will likely pay more than he's worth to you

    teams = [t for t in state.get("teams", []) if not t["is_mine"]]
    card.update(
        sold=False,
        my_value=my_value,
        market=market,
        yahoo_avg_cost=avg_cost,
        max_bid=max_bid,
        bid_up_to=min(my_value, max_bid),
        verdict=verdict,
        my_rank=ranked.index(rec) + 1 if rec else None,
        z=rec["z"] if rec else player["z"],
        strengths=rec["strengths"] if rec else [],
        weaknesses=rec["weaknesses"] if rec else [],
        rivals_who_can_pay_market=sum(t["max_bid"] >= market for t in teams) if teams else None,
        richest_rivals=[
            {"name": t["name"], "max_bid": t["max_bid"]}
            for t in sorted(teams, key=lambda t: t["max_bid"], reverse=True)[:3]
        ],
    )

    slots = info.get("slots")
    if slots and hasattr(tracker, "eligible_positions"):
        roster = [tracker.eligible_positions(n) or {positions.FLEX_SLOT} for n in mine]
        nominee_slots = tracker.eligible_positions(name)
        if nominee_slots:
            report = positions.roster_report(roster, slots, nominee_slots)
            card["fills_open_slot"] = report["fills_open_slot"]
            card["eligible"] = sorted(nominee_slots - {positions.FLEX_SLOT})
    return card


class DraftRouter:
    def __init__(self, store: ManualLeagueStore | None = None):
        self._store = store or ManualLeagueStore()
        self._blueprint = self._create_blueprint()
        self._manual_blueprint = self._create_manual_blueprint()

    def _get_tracker(self, league_id: str) -> YahooDraftTracker | None:
        user_guid = session.get("user")
        token_store = session.get("token_store", {})
        if not user_guid or user_guid not in token_store:
            return None
        yahoo_game = get_yahoo_sdk(token_store, {"user": user_guid})
        return YahooDraftTracker(yahoo_game.to_league(league_id))

    def _get_ranker(self, league_id: str, tracker: YahooDraftTracker) -> DraftRanker:
        key = getattr(tracker, "cache_key", league_id)
        if key not in _rankers:
            info = tracker.league_info()
            _rankers[key] = DraftRanker(
                load_player_pool(),
                categories=categories_from_yahoo(info["stat_categories"]),
                num_teams=info["num_teams"],
                roster_size=info["roster_size"],
                yahoo_ranks=tracker.yahoo_ranks(),
            )
        return _rankers[key]

    def _state_response(self, league_id: str, get_tracker):
        """Draft state + recommendations for whichever tracker `get_tracker` returns."""
        body = request.get_json(silent=True) or {}
        raw_punts = body.get("punts", request.args.get("punts", ""))
        punts = (
            raw_punts
            if isinstance(raw_punts, list)
            else [p for p in raw_punts.split(",") if p]
        )
        mock = bool(body.get("mock")) or request.args.get("mock") == "1"
        mode = body.get("mode", request.args.get("mode", "manual"))
        if mode not in jev_chooser.MODES:
            mode = "manual"
        preference = str(body.get("preference", request.args.get("preference", "")))
        nominee = str(body.get("nominee", request.args.get("nominee", "")) or "").strip()
        try:
            draft_position = int(
                body.get("draft_position", request.args.get("draft_position", ""))
            )
        except (TypeError, ValueError):
            draft_position = None

        try:
            tracker = get_tracker(league_id)
            if tracker is None:
                return jsonify({"error": "User not authenticated"}), 401

            ranker = self._get_ranker(league_id, tracker)
            info = tracker.league_info()

            if mock:
                taken = body.get("mock_taken") or []
                mine = body.get("mock_mine") or []
                state = {
                    "league_name": info["name"],
                    "is_auction": info["is_auction"],
                    "num_teams": info["num_teams"],
                    "roster_size": info["roster_size"],
                    "picks": [],
                    "taken_names": taken,
                    "my_roster": mine,
                    "mock": True,
                }
                if info["is_auction"]:
                    state.update(_mock_auction_state(info, taken, mine, body.get("mock_costs")))
            else:
                state = tracker.state(draft_position)
                taken, mine = state["taken_names"], state["my_roster"]

            recommendations = ranker.rank(
                punts=punts, taken_names=taken, my_roster_names=mine
            )

            plan = None
            if state["is_auction"]:
                plan = ranker.auction_plan(
                    punts, taken, mine,
                    league_budget_left=state["league_budget_left"],
                    league_budget_total=state["league_budget_total"],
                    league_spots_left=state["league_spots_left"],
                    my_budget_left=state["my_budget_left"],
                    my_open_spots=state["my_open_spots"],
                )
                for rec in recommendations:
                    rec["bid"] = plan["mine"].get(rec["name"])
                    rec["market"] = plan["market"].get(rec["name"])
                state["auction"] = {
                    "inflation_pct": plan["inflation_pct"],
                    "max_bid": plan["max_bid"],
                }

            roster_profile = ranker.roster_profile(mine)
            decision = jev_chooser.decide(
                mode,
                recommendations[: jev_chooser.SHORTLIST_SIZE],
                mine,
                punts,
                ranker.categories,
                roster_profile,
                preference,
            )

            return jsonify(
                {
                    **state,
                    "decision": decision,
                    "jev_configured": jev_chooser.is_configured(),
                    "categories": ranker.categories,
                    "punts": punts,
                    "suggested_punts": ranker.suggest_punts(mine),
                    "roster_profile": roster_profile,
                    "roster_unmatched": ranker.unmatched(mine),
                    "taken_unmatched": ranker.unmatched(taken),
                    "has_yahoo_ranks": bool(ranker.yahoo_ranks),
                    "recommendations": recommendations,
                    "positions": _position_report(tracker, info, mine),
                    "nominee_card": _nominee_card(
                        nominee, tracker, ranker, info, state, plan, punts, taken, mine
                    ),
                }
            )
        except Exception as e:
            logger.error(f"League {league_id}: draft state failed: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    def _create_blueprint(self):
        draft_bp = Blueprint("draft", __name__, url_prefix="/draft")

        @draft_bp.route("/<league_id>")
        @require_google_auth
        def draft_page(league_id):
            return render_template("draft.html", league_id=league_id)

        @draft_bp.route("/<league_id>/state", methods=["GET", "POST"])
        @require_google_auth
        def draft_state(league_id):
            """Draft state + recommendations.

            GET reads the live Yahoo draft. POST with {"mock": true,
            "mock_taken": [...], "mock_mine": [...]} runs the same engine on a
            hand-managed pick list so the manager can practice.
            """
            return self._state_response(league_id, self._get_tracker)

        @draft_bp.route("/<league_id>/players")
        @require_google_auth
        def draft_players(league_id):
            """Every rankable player's name, for the nominee search box."""
            try:
                tracker = self._get_tracker(league_id)
                if tracker is None:
                    return jsonify({"error": "User not authenticated"}), 401
                ranker = self._get_ranker(league_id, tracker)
                return jsonify({"players": sorted(p["name"] for p in ranker.players)})
            except Exception as e:
                logger.error(f"League {league_id}: player list failed: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        return draft_bp

    def _create_manual_blueprint(self):
        """Leagues typed in by hand: no Yahoo login, state stored on the server."""
        bp = Blueprint("manual_draft", __name__, url_prefix="/manual")
        store = self._store

        def user() -> str:
            return user_key(session.get("google_user"))

        def tracker_for(league_id: str) -> ManualDraftTracker:
            return ManualDraftTracker(store.get(user(), league_id))

        def state_json(league_id: str):
            return self._state_response(league_id, tracker_for)

        def guarded(action):
            """Run a change, answering 404 for an unknown league and 400 for bad input."""
            try:
                action()
            except KeyError:
                return jsonify({"error": "League not found"}), 404
            except ManualLeagueError as e:
                return jsonify({"error": str(e)}), 400
            return jsonify({"ok": True})

        @bp.route("")
        @require_google_auth
        def manual_home():
            return send_from_directory(current_app.static_folder, "manual.html")

        @bp.route("/api/leagues", methods=["GET", "POST"])
        @require_google_auth
        def leagues():
            if request.method == "GET":
                return jsonify({"leagues": store.list(user())})
            try:
                league = store.create(user(), request.get_json(silent=True) or {})
            except ManualLeagueError as e:
                return jsonify({"error": str(e)}), 400
            return jsonify({"id": league["id"]}), 201

        @bp.route("/<league_id>")
        @require_google_auth
        def league_page(league_id):
            try:
                store.get(user(), league_id)
            except KeyError:
                return redirect("/manual")
            return render_template("draft.html")

        @bp.route("/<league_id>/state")
        @require_google_auth
        def league_state(league_id):
            try:
                tracker_for(league_id)
            except KeyError:
                return jsonify({"error": "League not found"}), 404
            return state_json(league_id)

        @bp.route("/<league_id>/players")
        @require_google_auth
        def league_players(league_id):
            try:
                tracker = tracker_for(league_id)
            except KeyError:
                return jsonify({"error": "League not found"}), 404
            ranker = self._get_ranker(league_id, tracker)
            return jsonify({"players": sorted(p["name"] for p in ranker.players)})

        @bp.route("/<league_id>/settings", methods=["PUT"])
        @require_google_auth
        def settings(league_id):
            raw = request.get_json(silent=True) or {}
            return guarded(lambda: store.update_settings(user(), league_id, raw))

        @bp.route("/<league_id>/status", methods=["PUT"])
        @require_google_auth
        def status(league_id):
            raw = request.get_json(silent=True) or {}
            return guarded(lambda: store.set_status(user(), league_id, raw.get("status")))

        @bp.route("/<league_id>/picks", methods=["POST"])
        @require_google_auth
        def add_pick(league_id):
            raw = request.get_json(silent=True) or {}

            def action():
                name = str(raw.get("player_name") or "").strip()
                # Store the pool's spelling so the same player is never logged twice
                ranker = self._get_ranker(league_id, tracker_for(league_id))
                key = ranker.resolve_key(name) if name else None
                if key:
                    name = ranker._by_key[key]["name"]
                store.add_pick(user(), league_id, name, raw.get("team"), raw.get("cost"))

            return guarded(action)

        @bp.route("/<league_id>/picks/last", methods=["DELETE"])
        @require_google_auth
        def undo_pick(league_id):
            return guarded(lambda: store.undo_pick(user(), league_id))

        @bp.route("/<league_id>/notes", methods=["POST"])
        @require_google_auth
        def add_note(league_id):
            raw = request.get_json(silent=True) or {}
            return guarded(lambda: store.add_note(user(), league_id, raw.get("text")))

        @bp.route("/<league_id>/notes/<note_id>", methods=["DELETE"])
        @require_google_auth
        def delete_note(league_id, note_id):
            return guarded(lambda: store.delete_note(user(), league_id, note_id))

        @bp.route("/<league_id>", methods=["DELETE"])
        @require_google_auth
        def delete_league(league_id):
            return guarded(lambda: store.delete(user(), league_id))

        return bp

    def get_manual_bp(self):
        return self._manual_blueprint

    def get_bp(self):
        return self._blueprint
