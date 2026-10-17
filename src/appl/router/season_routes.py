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
from ..season import jev_advisor, player_status, report_writer, service, snapshot as snapshots
from ..season.analyzer import SeasonAnalyzer
from ..season.league_analysis import LeagueAnalysis
from ..season.matchup_planner import MatchupPlanner
from ..season.schedule import Schedule
from ..season.team_profile import TeamProfile

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
                 espn: EspnService | None = None, indexer=None, player_data=None):
        self._indexer = indexer  # re-indexes a manual league for the chat after its moves change
        self._store = store or default_store()
        self._espn = espn or EspnService(None)
        self._briefs = briefs or report_writer.BriefStore()
        self._llm_factory = llm_factory or LiteLLMClient.from_env
        self._schedule = schedule if schedule is not None else Schedule.load()
        self._player_data = player_data or player_status.load  # the nightly injury and form feeds
        self._blueprint = self._create_blueprint()

    # --- building blocks ----------------------------------------------------

    def _reindex(self, user_id: str, league_id: str) -> None:
        """Refresh the chat's copy of a manual league (it skips the work when nothing changed).
        Runs in the request, since Cloud Run starves background threads of CPU. Never fails
        the request that changed the league."""
        if self._indexer is None:
            return
        try:
            service.reindex_manual_league(self._indexer, self._store.get(user_id, league_id))
        except Exception as e:
            logger.warning(f"Could not re-index manual league {league_id}: {e}")

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

    # --- matchup prep -------------------------------------------------------

    def _data(self):
        try:
            return self._player_data()
        except Exception as e:
            logger.warning(f"Player data unavailable for the matchup page: {e}")
            return player_status.PlayerData.empty()

    def _analyzer(self, snap):
        """The analyzer for a league page, with the nightly datasets it reads."""
        data = self._data()
        if snap.key.startswith("manual:"):  # Yahoo and ESPN list every injured player themselves
            snap = snap.with_injuries(data.injury_levels())
        analyzer = SeasonAnalyzer(self._ranker(snap), snap, _punts(), schedule=self._schedule, opponent=_opponent())
        return analyzer, data

    @staticmethod
    def _header(analyzer) -> dict:
        snap = analyzer.snapshot
        names = [n or f"Team {i + 1}" for i, n in enumerate(snap.team_names)]
        return {
            "league_name": snap.name,
            "scoring": snap.scoring,
            "my_team": {"index": analyzer.me, "name": names[analyzer.me]},
            "teams": [{"index": i, "name": names[i], "is_mine": i == analyzer.me} for i in range(len(names))],
            "categories": analyzer.categories,
            "punts": analyzer.punts,
        }

    def _matchup_report(self, snap) -> dict:
        analyzer, data = self._analyzer(snap)
        return {
            **self._header(analyzer),
            **MatchupPlanner(analyzer).report(),
            **TeamProfile(analyzer, data).report(),
            "warnings": analyzer.warnings(),
        }

    def _analysis_report(self, snap) -> dict:
        analyzer, data = self._analyzer(snap)
        return {
            **self._header(analyzer),
            **LeagueAnalysis(analyzer, data).report(),
            "warnings": analyzer.warnings(),
        }

    def _matchup_brief_response(self, user: str, snap):
        report = self._matchup_report(snap)
        if not report["available"]:
            return jsonify({"error": "Pick this week's opponent first"}), 400
        digest = report_writer.matchup_hash(report)
        key = f"{snap.key}:matchup"
        cached = self._briefs.get(user, key)
        if cached and cached.get("hash") == digest and not _flag("refresh"):
            return jsonify({**cached, "cached": True})
        text = report_writer.write_matchup_brief(self._llm_factory(), report)
        return jsonify({**self._briefs.put(user, key, digest, text), "cached": False})

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
                return jsonify({"error": "The season analysis failed, please try again"}), 500

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
                self._reindex(user(), league_id)
                return jsonify({"ok": True})

            return errors(run)

        @bp.route("/manual/<league_id>/moves/<move_id>", methods=["DELETE"])
        @require_login
        def delete_move(league_id, move_id):
            def run():
                store.delete_move(user(), league_id, move_id)
                self._reindex(user(), league_id)
                return jsonify({"ok": True})

            return errors(run)

        # --- Yahoo leagues (read live, nothing stored but the cached brief) ---

        @bp.route("/yahoo/<league_id>")
        @require_login
        def yahoo_page(league_id):
            return render_template("season.html", league_id=league_id, active_tab="season", league_kind="yahoo")

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
            return render_template("season.html", league_id=league_id, active_tab="season", league_kind="espn")

        @bp.route("/espn/<league_id>/report", methods=["GET", "POST"])
        @require_login
        def espn_report(league_id):
            return espn(league_id, self._report_response)

        @bp.route("/espn/<league_id>/brief", methods=["POST"])
        @require_login
        def espn_brief(league_id):
            return espn(league_id, lambda snap: self._brief_response(user(), snap))

        # --- matchup prep (the same page and data for every kind of league) ---

        def with_snapshot(kind, league_id, action):
            if kind == "manual":
                return errors(lambda: action(snapshots.from_manual(manual_league(league_id))))
            if kind == "yahoo":
                return yahoo(league_id, action)
            if kind == "espn":
                return espn(league_id, action)
            return jsonify({"error": "League not found"}), 404

        def league_page(kind, league_id, template):
            """A page shared by every kind of league, or a redirect when it isn't the user's."""
            chat_id = league_id
            if kind == "manual":
                try:
                    manual_league(league_id)
                except KeyError:
                    return redirect("/manual")
                chat_id = service.manual_chat_id(league_id)
            elif kind == "espn":
                if not self._espn.league_repo.league_exist_for_user(league_id, user()):
                    return redirect("/dashboard")
            elif kind != "yahoo":
                return redirect("/dashboard")
            return render_template(template, league_id=chat_id, league_kind=kind)

        @bp.route("/<kind>/<league_id>/matchup")
        @require_login
        def matchup_page(kind, league_id):
            return league_page(kind, league_id, "matchup.html")

        @bp.route("/<kind>/<league_id>/matchup/report", methods=["GET", "POST"])
        @require_login
        def matchup_report(kind, league_id):
            return with_snapshot(kind, league_id, lambda snap: jsonify(self._matchup_report(snap)))

        @bp.route("/<kind>/<league_id>/matchup/brief", methods=["POST"])
        @require_login
        def matchup_brief(kind, league_id):
            return with_snapshot(kind, league_id, lambda snap: self._matchup_brief_response(user(), snap))

        # --- league analysis: buy low / sell high, power rankings, playoffs ---

        @bp.route("/<kind>/<league_id>/analysis")
        @require_login
        def analysis_page(kind, league_id):
            return league_page(kind, league_id, "analysis.html")

        @bp.route("/<kind>/<league_id>/analysis/report", methods=["GET", "POST"])
        @require_login
        def analysis_report(kind, league_id):
            return with_snapshot(kind, league_id, lambda snap: jsonify(self._analysis_report(snap)))

        return bp

    def get_bp(self):
        return self._blueprint
