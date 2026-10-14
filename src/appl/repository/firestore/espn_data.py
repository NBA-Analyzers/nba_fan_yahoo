"""ESPN leagues and the ESPN cookies of a signed-in user, in Firestore.

Layout (server-side only, like the rest of repository/firestore):
  espn_auth/<user_hash>                 the user's espn_s2 / SWID cookies, ENCRYPTED
                                        (see fantasy_integrations/espn/espn_credentials), never logged
  espn_leagues/<user_hash>_<league id>  leagues connected by a user

Document ids are deterministic and every write is set(merge=True), so reconnecting is idempotent.
`league_exist_for_user` is the league-access check for the "espn-<id>" chat ids.
"""
from typing import Any, Dict, List, Optional

from ...draft.manual_league import user_hash
from .user_data import FirestoreClient, ValidationError, _check_id, _created, _now


class EspnAuthRepository:
    def __init__(self, client=None):
        self.fs = client if isinstance(client, FirestoreClient) else FirestoreClient(client)

    def _ref(self, user_id: str):
        return self.fs.col("espn_auth").document(user_hash(_check_id(user_id, "User ID")))

    def get_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        snap = self._ref(user_id).get()
        return snap.to_dict() if snap.exists else None

    def save(self, user_id: str, espn_s2_enc: str, swid_enc: str) -> None:
        self._ref(user_id).set({"user_id": user_id, "espn_s2_enc": espn_s2_enc,
                                "swid_enc": swid_enc, "last_updated": _now()}, merge=True)

    def delete_by_user_id(self, user_id: str) -> None:
        self._ref(user_id).delete()


class EspnLeagueRepository:
    def __init__(self, client=None):
        self.fs = client if isinstance(client, FirestoreClient) else FirestoreClient(client)

    def _col(self):
        return self.fs.col("espn_leagues")

    @staticmethod
    def _id(league_id: str, user_id: str) -> str:
        if not str(league_id).isdigit():
            raise ValidationError("An ESPN league id is a number")
        return f"{user_hash(_check_id(user_id, 'User ID'))}_{league_id}"

    def get_by_user_id(self, user_id: str) -> List[Dict[str, Any]]:
        return [s.to_dict() | {"created_at": _created(s, s.to_dict())}
                for s in self._col().where("user_id", "==", user_id).stream()]

    def league_exist_for_user(self, league_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """True only for a league connected under THIS user id."""
        if not league_id or not user_id or not str(league_id).isdigit():
            return None
        snap = self._col().document(self._id(league_id, user_id)).get()
        return snap.to_dict() if snap.exists else None

    def save(self, user_id: str, league_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        data = {**data, "user_id": user_id, "league_id": str(league_id)}
        self._col().document(self._id(league_id, user_id)).set(data, merge=True)
        return data

    def delete_by_user_id(self, user_id: str) -> None:
        for snap in self._col().where("user_id", "==", user_id).stream():
            snap.reference.delete()
