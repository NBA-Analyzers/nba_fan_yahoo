import logging
from functools import wraps

from flask import (
    Blueprint,
    current_app,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
)

from ..draft import jev_chooser
from ..draft.api_tokens import ApiTokenStore
from ..draft.manual_league import (
    ManualDraftTracker,
    ManualLeagueError,
    ManualLeagueStore,
    match_import_teams,
)
from ..draft.espn_draft import EspnDraftTracker
from ..draft.service import DraftService, StateOptions
from ..fantasy_integrations.espn.espn_service import EspnError, EspnService
from ..draft.yahoo_draft import YahooDraftTracker
from ..fantasy_integrations.yahoo.sync_league.yahoo_service import get_yahoo_sdk
from ..middleware.auth_decorators import require_login
from ..identity.session import current_user_id
from ..season.service import manual_chat_id

logger = logging.getLogger(__name__)

class BadRequest(ValueError):
    """The request body or query had the wrong shape; shown to the caller as a 400."""


def _name_list(value, field: str) -> list[str]:
    """A list of player names, or empty when the field is missing."""
    if value in (None, ""):
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise BadRequest(f"{field} must be a list of player names")
    return value


def _parse_punts(raw) -> list[str]:
    """Punts as a list, from a list or a comma separated string."""
    if isinstance(raw, list):
        return _name_list(raw, "punts")
    if isinstance(raw, str):
        return [p for p in raw.split(",") if p]
    raise BadRequest("punts must be a list or a comma separated string")


class DraftRouter:
    def __init__(self, store: ManualLeagueStore, tokens: ApiTokenStore, espn: EspnService,
                 drafts: DraftService | None = None, indexer=None):
        self._indexer = indexer  # re-indexes a manual league for the chat after its notes change
        self._store = store
        self._tokens = tokens
        self._espn = espn
        self._drafts = drafts or DraftService()
        self._blueprint = self._create_blueprint()
        self._manual_blueprint = self._create_manual_blueprint()

    def _get_tracker(self, league_id: str) -> YahooDraftTracker | None:
        user_guid = session.get("user")
        token_store = session.get("token_store", {})
        if not user_guid or user_guid not in token_store:
            return None
        yahoo_game = get_yahoo_sdk(token_store, {"user": user_guid})
        return YahooDraftTracker(yahoo_game.to_league(league_id), user=user_guid)

    def _state_response(self, league_id: str, get_tracker):
        """Draft state + recommendations for whichever tracker `get_tracker` returns."""
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return jsonify({"error": "JSON body must be an object"}), 400
        try:
            punts = _parse_punts(body.get("punts", request.args.get("punts", "")))
            mock_taken = _name_list(body.get("mock_taken"), "mock_taken")
            mock_mine = _name_list(body.get("mock_mine"), "mock_mine")
            mock_costs = body.get("mock_costs")
            if mock_costs is not None and not isinstance(mock_costs, dict):
                raise BadRequest("mock_costs must be an object of player name to price")
        except BadRequest as e:
            return jsonify({"error": str(e)}), 400
        mock = bool(body.get("mock")) or request.args.get("mock") == "1"
        auto_punts = body.get("auto_punts") in (True, "1", 1) or request.args.get("auto_punts") == "1"
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

        options = StateOptions(
            punts=punts, mock=mock, auto_punts=auto_punts, mode=mode, preference=preference,
            nominee=nominee, draft_position=draft_position,
            mock_taken=mock_taken, mock_mine=mock_mine, mock_costs=mock_costs,
        )

        try:
            tracker = get_tracker(league_id)
            if tracker is None:
                return jsonify({"error": "User not authenticated"}), 401
            return jsonify(self._drafts.state(league_id, tracker, options))
        except Exception as e:
            logger.error(f"League {league_id}: draft state failed: {e}", exc_info=True)
            return jsonify({"error": "Could not build the draft state"}), 500

    def _create_blueprint(self):
        draft_bp = Blueprint("draft", __name__, url_prefix="/draft")

        @draft_bp.route("/<league_id>")
        @require_login
        def draft_page(league_id):
            return render_template("draft.html", league_id=league_id)

        @draft_bp.route("/<league_id>/state", methods=["GET", "POST"])
        @require_login
        def draft_state(league_id):
            """Draft state + recommendations.

            GET reads the live Yahoo draft. POST with {"mock": true,
            "mock_taken": [...], "mock_mine": [...]} runs the same engine on a
            hand-managed pick list so the manager can practice.
            """
            return self._state_response(league_id, self._get_tracker)

        @draft_bp.route("/<league_id>/players")
        @require_login
        def draft_players(league_id):
            """Every rankable player's name, for the nominee search box."""
            try:
                tracker = self._get_tracker(league_id)
                if tracker is None:
                    return jsonify({"error": "User not authenticated"}), 401
                ranker = self._drafts.ranker_for(league_id, tracker)
                return jsonify({"players": sorted(p["name"] for p in ranker.players)})
            except Exception as e:
                logger.error(f"League {league_id}: player list failed: {e}", exc_info=True)
                return jsonify({"error": "Could not load the player list"}), 500

        # --- ESPN leagues: the same page and engine, an ESPN tracker ---

        def espn_tracker(league_id: str) -> EspnDraftTracker:
            user = current_user_id()
            league, swid = self._espn.load_league(user, league_id)
            return EspnDraftTracker(league, league_id, swid=swid, user=user)

        def espn_guard(league_id: str, action):
            try:
                return action()
            except KeyError:
                return jsonify({"error": "League not found"}), 404
            except Exception as e:
                logger.error(f"ESPN league {league_id}: draft call failed: {e}", exc_info=True)
                return jsonify({"error": str(e) if isinstance(e, EspnError) else "Could not read the league from ESPN"}), 500

        @draft_bp.route("/espn/<league_id>")
        @require_login
        def espn_draft_page(league_id):
            if not self._espn.league_repo.league_exist_for_user(league_id, current_user_id()):
                return redirect("/dashboard")
            return render_template("draft.html", league_id=league_id)

        @draft_bp.route("/espn/<league_id>/state", methods=["GET", "POST"])
        @require_login
        def espn_draft_state(league_id):
            return espn_guard(league_id, lambda: (
                self._espn.load_league(current_user_id(), league_id),  # 404 unless it's yours
                self._state_response(league_id, espn_tracker))[1])

        @draft_bp.route("/espn/<league_id>/players")
        @require_login
        def espn_draft_players(league_id):
            def run():
                ranker = self._drafts.ranker_for(league_id, espn_tracker(league_id))
                return jsonify({"players": sorted(p["name"] for p in ranker.players)})

            return espn_guard(league_id, run)

        return draft_bp

    def _create_manual_blueprint(self):
        """Leagues typed in by hand: no Yahoo login, state stored on the server."""
        bp = Blueprint("manual_draft", __name__, url_prefix="/manual")
        store = self._store

        def user() -> str:
            return g.get("api_user") or current_user_id()

        def token_or_google(view):
            """Accept a personal access token (`Authorization: Bearer fbh_...`) as
            well as the browser login, for the endpoints tools like Claude Code call."""
            @wraps(view)
            def wrapper(*args, **kwargs):
                header = request.headers.get("Authorization", "")
                if header:
                    scheme, _, token = header.partition(" ")
                    found = self._tokens.user_for(token.strip()) if scheme.lower() == "bearer" else None
                    if not found:
                        return jsonify({"error": "Invalid or revoked access token"}), 401
                    g.api_user = found
                    return view(*args, **kwargs)
                return require_login(view)(*args, **kwargs)

            return wrapper

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
        @require_login
        def manual_home():
            return send_from_directory(current_app.static_folder, "manual.html")

        @bp.route("/api/leagues", methods=["GET", "POST"])
        @token_or_google
        def leagues():
            if request.method == "GET":
                return jsonify({"leagues": store.list(user())})
            try:
                league = store.create(user(), request.get_json(silent=True) or {})
            except ManualLeagueError as e:
                return jsonify({"error": str(e)}), 400
            return jsonify({"id": league["id"]}), 201

        @bp.route("/api/import", methods=["POST"])
        @token_or_google
        def import_league():
            """Create a league from finished rosters. Names are matched to the stats
            list first; unknown ones come back with suggestions and nothing is saved
            unless `force` is set. `dry_run` only reports the matching."""
            raw = request.get_json(silent=True) or {}
            teams = raw.get("teams")
            if not isinstance(teams, list):
                return jsonify({"error": "Send the rosters as `teams`: [{name, players}]"}), 400
            ranker = self._drafts.names_ranker()

            matched, unknown = match_import_teams(ranker, teams)

            report = {"teams": matched, "unknown": unknown}
            if raw.get("dry_run"):
                return jsonify(report)
            if unknown and not raw.get("force"):
                return jsonify({**report, "error": f"{len(unknown)} player(s) not in the stats list: "
                                + ", ".join(unknown) + ". Fix them or send force: true."}), 400
            body = dict(raw, teams=[{"name": t["name"], "players": [p["name"] for p in t["players"]]}
                                    for t in matched])
            try:
                league = store.import_league(user(), body)
            except ManualLeagueError as e:
                return jsonify({**report, "error": str(e)}), 400
            return jsonify({**report, "id": league["id"], "name": league["name"],
                            "links": {"draft": f"/manual/{league['id']}",
                                      "season": f"/season/manual/{league['id']}",
                                      "ask": f"/ai-chat/manual/{league['id']}"}}), 201

        # --- access tokens (browser login only: a token can't mint more tokens) ---

        @bp.route("/api/tokens", methods=["GET", "POST"])
        @require_login
        def tokens():
            if request.method == "GET":
                return jsonify({"tokens": self._tokens.list(user())})
            raw = request.get_json(silent=True) or {}
            try:
                token = self._tokens.create(user(), raw.get("label", ""))
            except ValueError as e:
                return jsonify({"error": str(e)}), 400
            return jsonify({"token": token}), 201

        @bp.route("/api/tokens/<token_id>", methods=["DELETE"])
        @require_login
        def revoke_token(token_id):
            if not self._tokens.revoke(user(), token_id):
                return jsonify({"error": "Token not found"}), 404
            return jsonify({"ok": True})

        @bp.route("/<league_id>")
        @require_login
        def league_page(league_id):
            try:
                store.get(user(), league_id)
            except KeyError:
                return redirect("/manual")
            return render_template("draft.html", league_id=manual_chat_id(league_id))

        @bp.route("/<league_id>/state")
        @require_login
        def league_state(league_id):
            try:
                tracker_for(league_id)
            except KeyError:
                return jsonify({"error": "League not found"}), 404
            return state_json(league_id)

        @bp.route("/<league_id>/players")
        @require_login
        def league_players(league_id):
            try:
                tracker = tracker_for(league_id)
            except KeyError:
                return jsonify({"error": "League not found"}), 404
            ranker = self._drafts.ranker_for(league_id, tracker)
            return jsonify({"players": sorted(p["name"] for p in ranker.players)})

        @bp.route("/<league_id>/settings", methods=["PUT"])
        @require_login
        def settings(league_id):
            raw = request.get_json(silent=True) or {}
            return guarded(lambda: store.update_settings(user(), league_id, raw))

        @bp.route("/<league_id>/status", methods=["PUT"])
        @require_login
        def status(league_id):
            raw = request.get_json(silent=True) or {}
            return guarded(lambda: store.set_status(user(), league_id, raw.get("status")))

        def save_pick(league_id, save):
            """Shared by add and edit: settle the player's name, then call `save(name, raw)`."""
            raw = request.get_json(silent=True) or {}
            name = str(raw.get("player_name") or "").strip()
            try:
                ranker = self._drafts.ranker_for(league_id, tracker_for(league_id))
            except KeyError:
                return jsonify({"error": "League not found"}), 404
            # Store the pool's spelling so the same player is never logged twice
            key = ranker.resolve_key(name) if name else None
            if key:
                name = ranker._by_key[key]["name"]
            elif name and not raw.get("force"):
                # A typo would silently use up a turn, so ask first; "force" logs
                # players with no stats (e.g. rookies) as typed
                return jsonify({
                    "error": f'No player called "{name}" in the stats list.',
                    "unknown_player": True,
                    "suggestions": ranker.suggest_names(name),
                }), 400

            return guarded(lambda: save(name, raw))

        @bp.route("/<league_id>/picks", methods=["POST"])
        @require_login
        def add_pick(league_id):
            return save_pick(league_id, lambda name, raw: store.add_pick(
                user(), league_id, name, raw.get("team"), raw.get("cost")))

        @bp.route("/<league_id>/picks/last", methods=["DELETE"])
        @require_login
        def undo_pick(league_id):
            return guarded(lambda: store.undo_pick(user(), league_id))

        @bp.route("/<league_id>/picks/<int:number>", methods=["PUT"])
        @require_login
        def edit_pick(league_id, number):
            return save_pick(league_id, lambda name, raw: store.edit_pick(
                user(), league_id, number, name, raw.get("team"), raw.get("cost")))

        @bp.route("/<league_id>/picks/<int:number>", methods=["DELETE"])
        @require_login
        def delete_pick(league_id, number):
            return guarded(lambda: store.delete_pick(user(), league_id, number))

        @bp.route("/<league_id>/notes", methods=["POST"])
        @require_login
        def add_note(league_id):
            raw = request.get_json(silent=True) or {}
            return guarded(lambda: (store.add_note(user(), league_id, raw.get("text")),
                                    self._reindex(user(), league_id)))

        @bp.route("/<league_id>/notes/<note_id>", methods=["DELETE"])
        @require_login
        def delete_note(league_id, note_id):
            return guarded(lambda: (store.delete_note(user(), league_id, note_id),
                                    self._reindex(user(), league_id)))

        @bp.route("/<league_id>", methods=["DELETE"])
        @require_login
        def delete_league(league_id):
            return guarded(lambda: store.delete(user(), league_id))

        return bp

    def _reindex(self, user_id: str, league_id: str) -> None:
        if self._indexer is None:
            return
        # In the request, not a background thread: Cloud Run starves those of CPU
        try:
            from ..season.service import reindex_manual_league

            reindex_manual_league(self._indexer, self._store.get(user_id, league_id))
        except Exception as e:
            logger.warning(f"Could not re-index manual league {league_id}: {e}")

    def get_manual_bp(self):
        return self._manual_blueprint

    def get_bp(self):
        return self._blueprint
