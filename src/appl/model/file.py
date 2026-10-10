from enum import Enum


class FilePurpose(Enum):
    GENERAL = "general"  # legacy single shared collection; replaced by GeneralCollection
    LEAGUE = "league"


class GeneralCollection(Enum):
    """The shared (non-league) AI index, one collection per source so refreshing one
    never wipes another."""

    RULES = "general_rules"
    STATS = "general_stats"
    SCHEDULE = "general_schedule"


GENERAL_COLLECTIONS = [c.value for c in GeneralCollection]
