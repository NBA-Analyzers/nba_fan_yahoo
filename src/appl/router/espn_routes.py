import logging

from flask import Blueprint, redirect, render_template, request, session, url_for

from ..ai.document_indexer import DocumentIndexer
from ..fantasy_integrations.espn import espn_credentials
from ..fantasy_integrations.espn.espn_service import EspnError, EspnService, espn_year
from ..middleware.auth_decorators import require_login

logger = logging.getLogger(__name__)


def _problem(title, text, status=400):
    return render_template("pages/message.html", title=title, text=text), status


class EspnRouter:
    """Connect ESPN leagues. ESPN has no OAuth: private leagues need the user's espn_s2 and
    SWID cookies, which are only ever stored encrypted (see espn_credentials)."""

    def __init__(self, document_indexer: DocumentIndexer, service: EspnService | None = None):
        self.service = service or EspnService(document_indexer)
        self._blueprint = self._create_blueprint()

    def _create_blueprint(self):
        bp = Blueprint("espn", __name__, url_prefix="/espn")

        @bp.route("/connect", methods=["POST"])
        @require_login
        def connect():
            user_id = session["user_id"]
            try:
                season_year = int(request.form.get("season_year") or espn_year())
                result = self.service.connect(
                    user_id,
                    request.form.get("league_id", "").strip(),
                    season_year,
                    request.form.get("espn_s2"),
                    request.form.get("swid"),
                )
            except ValueError:
                return _problem("We couldn't connect that league", "The season must be a year, such as 2026.")
            except EspnError as e:
                return _problem("We couldn't connect that league", str(e))
            except espn_credentials.CredentialsError:
                logger.error("ESPN cookie encryption is not configured")
                return _problem("ESPN isn't available right now",
                                "Connecting private ESPN leagues is not set up on this server.", 503)
            except Exception:
                logger.error("ESPN connect failed", exc_info=True)
                return _problem("We couldn't connect that league",
                                "Something went wrong. Please try again in a moment.", 500)
            return redirect(url_for("main.ai_chat_espn", league_id=result["league_id"]))

        @bp.route("/disconnect", methods=["POST"])
        @require_login
        def disconnect():
            try:
                self.service.disconnect(session["user_id"])
            except Exception:
                logger.error("ESPN disconnect failed", exc_info=True)
                return _problem("We couldn't disconnect ESPN", "Please try again in a moment.", 500)
            return redirect(url_for("main.dashboard"))

        return bp

    def get_bp(self):
        return self._blueprint
