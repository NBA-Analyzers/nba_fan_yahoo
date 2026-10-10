import logging

from flask import Blueprint, jsonify, redirect, render_template, request, session

from ..ai.litellm_adapters import LiteLLMClient
from ..draft.manual_league import (
    ManualLeagueError,
    ManualLeagueStore,
    default_store,
)
from ..fantasy_integrations.espn.espn_service import EspnError, EspnService
from ..fantasy_integrations.yahoo.sync_league.yahoo_service import get_yahoo_sdk
from ..middleware.auth_decorators import require_login
from ..identity.session import current_user_id
from ..season import jev_advisor, report_writer, service, snapshot as snapshots
from ..season.analyzer import SeasonAnalyzer
from ..season.schedule import Schedule

logger = logging.getLogger(__name__)

def _punts() -> list[str]:
    body = request.get_json(silent=True) or {}
    raw = body.get("punts", request.args.get("punts", ""))
    return raw if isinstance(raw, list) else [p for p in str(raw).split(",") if p]


def _opponent() -> int | None:
    """The opponent team number (1-based) picked on the page, as a 0-based index."""
    try:
        return int(request.args.get("opponent", "")) - 1
    except ValueError:
        return None


def _flag(name: str) -> bool:
    body = request.get_json(silent=True) or {}
    return str(body.get(name, request.args.get(name, ""))).lower() in ("1", "true")


class SeasonRouter:
    def __init__(self, store: ManualLeagueStore | None = None, briefs=None, llm_factory=None, schedule=None,
                 espn: EspnService | None = None):
        self._store = store or default_store()
        self._espn = espn or EspnService(None)
        self._briefs = briefs or report_writer.BriefStore()
        self._llm_factory = llm_factory or LiteLLMClient.from_env
        self._schedule = schedule if schedule is not None else Schedule.load()
        self._blueprint = self._create_blueprint()

    # --- building blocks ----------------------------------------------------

    @staticmethod
    def _ranker(snap):
        return service.ranker_for(snap)

    def _yahoo_snapshot(self, league_id: str):
        user_guid = session.get("user")
        token_store = session.get("token_store", {})
        if not user_guid or user_guid not in token_store:
            return None
        game = get_yahoo_sdk(token_store, {"user": user_guid})
        return snapshots.from_yahoo(game.to_league(league_id), league_id, user=user_guid)

    def _report(self, snap) -> tuple[dict, dict | None]:
        ranker = self._ranker(snap)
        report = SeasonAnalyzer(ranker, snap, _punts(), schedule=self._schedule, opponent=_opponent()).report()
        recommendation = None
        if _flag("jev"):
            body = request.get_json(silent=True) or {}
            preference = str(body.get("preference", request.args.get("preference", "")))
            recommendation = jev_advisor.recommend(report, preference)
        return report, recommendation

    def _report_response(self, snap, extra: dict | None = None):
        report, recommendation = self._report(snap)
        return jsonify({
            **report,
            **(extra or {}),
            "recommendation": recommendation,
            "jev_configured": jev_advisor.jev_chooser.is_configured(),
            "players_tracked": len(self._ranker(snap).players),
        })

    def _brief_response(self, user: str, snap):
        report, recommendation = self._report(snap)
        digest = report_writer.report_hash(report, recommendation)
        cached = self._briefs.get(user, snap.key)
        if cached and cached.get("hash") == digest and not _flag("refresh"):
            return jsonify({**cached, "cached": True})
        text = report_writer.write_brief(self._llm_factory(), report, recommendation)
        return jsonify({**self._briefs.put(user, snap.key, digest, text), "cached": False})

    # --- routes -------------------------------------------------------------

    def _create_blueprint(self):
        bp = Blueprint("season", __name__, url_prefix="/season")
        store = self._store

        def user() -> str:
            return current_user_id()

        def manual_league(league_id: str) -> dict:
            return store.get(user(), league_id)

        def errors(action):
            """404 for an unknown league, 400 for bad input, 500 (as JSON) otherwise."""
            try:
                return action()
            except KeyError:
                return jsonify({"error": "League not found"}), 404
            except ManualLeagueError as e:
                return jsonify({"error": str(e)}), 400
            except Exception as e:
                logger.error(f"Season analysis failed: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        # --- manual leagues ---

        @bp.route("/manual/<league_id>")
        @require_login
        def manual_page(league_id):
            try:
                manual_league(league_id)
            except KeyError:
                return redirect("/manual")
            return render_template("season.html", league_id=service.manual_chat_id(league_id))

        def manual_extra(league: dict) -> dict:
            snap = snapshots.from_manual(league)
            return {
                "manual": {
                    "moves": league.get("moves", []),
                    "status": league["status"],
                    "rosters": [
                        {"index": i, "name": snap.team_names[i], "is_mine": i == snap.my_team, "players": r}
                        for i, r in enumerate(snap.rosters)
                    ],
                }
            }

        @bp.route("/manual/<league_id>/report", methods=["GET", "POST"])
        @require_login
        def manual_report(league_id):
            def run():
                league = manual_league(league_id)
                return self._report_response(snapshots.from_manual(league), manual_extra(league))

            return errors(run)

        @bp.route("/manual/<league_id>/brief", methods=["POST"])
        @require_login
        def manual_brief(league_id):
            return errors(lambda: self._brief_response(user(), snapshots.from_manual(manual_league(league_id))))

        @bp.route("/manual/<league_id>/players")
        @require_login
        def manual_players(league_id):
            def run():
                ranker = self._ranker(snapshots.from_manual(manual_league(league_id)))
                return jsonify({"players": sorted(p["name"] for p in ranker.players)})

            return errors(run)

        @bp.route("/manual/<league_id>/moves", methods=["POST"])
        @require_login
        def add_move(league_id):
            def run():
                raw = request.get_json(silent=True) or {}
                ranker = self._ranker(snapshots.from_manual(manual_league(league_id)))
                # Pool spelling, so the move matches the roster; unknown pickups need a confirm
                clean = dict(raw)
                for side in ("add", "drop"):
                    names = raw.get(side) or []
                    names = names.split(",") if isinstance(names, str) else names
                    fixed = []
                    for name in (str(n).strip() for n in names):
                        if not name:
                            continue
                        key = ranker.resolve_key(name)
                        if key:
                            fixed.append(ranker._by_key[key]["name"])
                        elif side == "add" and raw.get("kind") == "add" and not raw.get("force"):
                            return jsonify({
                                "error": f'No player called "{name}" in the stats list.',
                                "unknown_player": True,
                                "suggestions": ranker.suggest_names(name),
                            }), 400
                        else:
                            fixed.append(name)
                    clean[side] = fixed
                store.add_move(user(), league_id, clean)
                return jsonify({"ok": True})

            return errors(run)

        @bp.route("/manual/<league_id>/moves/<move_id>", methods=["DELETE"])
        @require_login
        def delete_move(league_id, move_id):
            def run():
                store.delete_move(user(), league_id, move_id)
                return jsonify({"ok": True})

            return errors(run)

        # --- Yahoo leagues (read live, nothing stored but the cached brief) ---

        @bp.route("/yahoo/<league_id>")
        @require_login
        def yahoo_page(league_id):
            return render_template("season.html", league_id=league_id, active_tab="season")

        def yahoo(league_id, action):
            def run():
                snap = self._yahoo_snapshot(league_id)
                if snap is None:
                    return jsonify({"error": "Connect your Yahoo account first"}), 401
                return action(snap)

            return errors(run)

        @bp.route("/yahoo/<league_id>/report", methods=["GET", "POST"])
        @require_login
        def yahoo_report(league_id):
            return yahoo(league_id, self._report_response)

        @bp.route("/yahoo/<league_id>/brief", methods=["POST"])
        @require_login
        def yahoo_brief(league_id):
            return yahoo(league_id, lambda snap: self._brief_response(user(), snap))

        # --- ESPN leagues (read live like Yahoo; only the user's own leagues) ---

        def espn(league_id, action):
            def run():
                try:
                    league, swid = self._espn.load_league(user(), league_id)
                except EspnError as e:
                    return jsonify({"error": str(e)}), 502
                snap = snapshots.from_espn(league, league_id, swid=swid, user=user())
                return action(snap)

            return errors(run)  # an unknown or foreign league is a KeyError: 404

        @bp.route("/espn/<league_id>")
        @require_login
        def espn_page(league_id):
            if not self._espn.league_repo.league_exist_for_user(league_id, user()):
                return redirect("/dashboard")
            return render_template("season.html", league_id=league_id, active_tab="season")

        @bp.route("/espn/<league_id>/report", methods=["GET", "POST"])
        @require_login
        def espn_report(league_id):
            return espn(league_id, self._report_response)

        @bp.route("/espn/<league_id>/brief", methods=["POST"])
        @require_login
        def espn_brief(league_id):
            return espn(league_id, lambda snap: self._brief_response(user(), snap))

        return bp

    def get_bp(self):
        return self._blueprint
