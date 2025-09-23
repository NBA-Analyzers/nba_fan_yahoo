from typing import Optional, Dict, Any
from ..database.base_repository import BaseRepository


class VectorMetadataRepository(BaseRepository):
    def __init__(self):
        super().__init__("Vector_Metadata")

    def upsert(self, data: Dict[str, Any]) -> Dict[str, Any]:
        clean = {k: v for k, v in data.items() if v is not None}
        resp = self.db.table(self.table_name).upsert(clean).execute()
        return resp.data[0] if resp.data else {}

    def get_by_vector_store_id(self, vector_store_id: str) -> Optional[Dict[str, Any]]:
        return self.get_by_field("vector_store_id", vector_store_id)


