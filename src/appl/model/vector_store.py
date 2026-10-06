from ..model.file import FilePurpose


def generate_league_vector_store_id(league_id: str) -> str:
    return f"{FilePurpose.LEAGUE.value}_{league_id}"