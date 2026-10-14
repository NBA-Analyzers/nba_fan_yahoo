"""
A short plain-language brief written by the LLM from the analyzer's report.

The numbers come from the analyzer; the LLM only explains them. Briefs are
cached by a hash of the report, so the same league state is written up once:
in Firestore on Cloud Run (which sets K_SERVICE), in memory elsewhere.
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone

from ..draft.manual_league import user_hash

SYSTEM_PROMPT = (
    "You are a fantasy basketball analyst writing for one manager in a category league. "
    "You are given a JSON analysis of their team computed from per-game stats. Use only "
    "those numbers; never invent stats, injuries or news. Write at most about 200 words "
    "in three short sections with these headings: 'What's working', 'What to fix', "
    "'Do this week'. In 'Do this week' name concrete moves from the analysis (trades, "
    "pickups, drops) and say in a few words why. If a recommended move is given, lead with it. "
    "Plain language, no tables."
)


def report_hash(report: dict, recommendation: dict | None) -> str:
    return hashlib.sha1(
        json.dumps([report, recommendation], sort_keys=True, default=str).encode()
    ).hexdigest()


def _compact(report: dict, recommendation: dict | None) -> dict:
    """What the LLM needs: my team, my categories, advice and the moves. The full
    standings table stays out, it only adds tokens."""
    return {
        "league": report["league_name"],
        "teams_in_league": report["num_teams"],
        "my_team": report["my_team"],
        "punted": report["punts"],
        "my_categories": report["my_categories"],
        "advice": [a["text"] for a in report["advice"]],
        "trade_ideas": report["trades"],
        "pickups": report["pickups"],
        "weakest_players": report["drops"],
        "recommended_move": recommendation and {
            "move": recommendation["text"], "chosen_by": recommendation["source"],
        },
    }


def write_brief(llm, report: dict, recommendation: dict | None = None) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(_compact(report, recommendation), default=str)},
    ]
    return llm.complete(messages).strip()


class BriefStore:
    """Cached briefs per user and league: {"hash", "text", "ts"}."""

    def __init__(self, client=None, root: str = "season_reports", use_firestore: bool | None = None):
        self._client_obj = client
        self.root = root
        if use_firestore is None:
            use_firestore = client is not None or bool(os.environ.get("K_SERVICE"))
        self.use_firestore = use_firestore
        self._memory: dict[tuple, dict] = {}

    def _client(self):
        if self._client_obj is None:
            from google.cloud import firestore

            self._client_obj = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"))
        return self._client_obj

    def _ref(self, user: str, league_key: str):
        doc_id = re.sub(r"[^A-Za-z0-9_.-]", "_", league_key)
        return self._client().collection(self.root).document(user_hash(user)).collection("briefs").document(doc_id)

    def get(self, user: str, league_key: str) -> dict | None:
        if not self.use_firestore:
            return self._memory.get((user, league_key))
        snap = self._ref(user, league_key).get()
        return snap.to_dict() if snap.exists else None

    def put(self, user: str, league_key: str, digest: str, text: str) -> dict:
        brief = {"hash": digest, "text": text, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        if self.use_firestore:
            self._ref(user, league_key).set(brief)
        else:
            self._memory[(user, league_key)] = brief
        return brief
