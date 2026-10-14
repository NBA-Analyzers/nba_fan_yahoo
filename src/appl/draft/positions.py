"""
Roster slot checks for position leagues (PG, SG, G, SF, PF, F, C, Util ...).

Warn-only: prices ignore positions, but the page tells the manager which slots
their roster can't yet fill and whether a nominated player would fill one.
Eligibility comes from Yahoo (each player's eligible_positions), and the
required slots from the league's own roster settings.
"""

import re

NOT_STARTING_SLOTS = {"BN", "IL", "IL+", "IR", "NA"}
FLEX_SLOT = "Util"

# The roster spots a league can have, in the order they are shown
SLOT_ORDER = ["PG", "SG", "G", "SF", "PF", "F", "C", "Util", "BN", "IL"]
DEFAULT_SLOTS = {"PG": 1, "SG": 1, "G": 1, "SF": 1, "PF": 1, "F": 1, "C": 1, "Util": 3, "BN": 3, "IL": 1}
MAX_PER_SLOT = 15

# Which roster spots a player listed at a position can fill (Yahoo's own rules)
_FILLS = {
    "PG": {"PG", "G"}, "SG": {"SG", "G"}, "G": {"PG", "SG", "G"},
    "SF": {"SF", "F"}, "PF": {"PF", "F"}, "F": {"SF", "PF", "F"}, "C": {"C"},
}


def required_slots(positions: dict) -> dict[str, int]:
    """Starting slots from Yahoo's league positions, e.g. {"PG": 1, "C": 1, "Util": 3}."""
    slots = {}
    for name, info in (positions or {}).items():
        if name in NOT_STARTING_SLOTS:
            continue
        try:
            count = int(info.get("count", 0))
        except (TypeError, ValueError):
            continue
        if count > 0:
            slots[name] = count
    return slots


def parse_eligible(raw) -> set[str]:
    """Yahoo gives eligible_positions as ['PG', 'G'] or [{'position': 'PG'}, ...]."""
    eligible = set()
    for item in raw or []:
        name = item.get("position") if isinstance(item, dict) else item
        if name:
            eligible.add(str(name))
    return eligible


def _can_fill(slot: str, eligible: set[str]) -> bool:
    return slot == FLEX_SLOT or slot in eligible


def assign(players: list[set[str]], slots: dict[str, int]) -> tuple[int, list[str]]:
    """Best possible way to start these players.

    Returns (how many can start, the slots left empty). Uses bipartite matching,
    so a PG/SG player is placed wherever it lets the most players start.
    """
    instances = [slot for slot, count in slots.items() for _ in range(count)]
    match: dict[int, int] = {}  # slot instance index -> player index

    def place(player: int, seen: set[int]) -> bool:
        for i, slot in enumerate(instances):
            if i in seen or not _can_fill(slot, players[player]):
                continue
            seen.add(i)
            if i not in match or place(match[i], seen):
                match[i] = player
                return True
        return False

    started = sum(place(p, set()) for p in range(len(players)))
    empty = [slot for i, slot in enumerate(instances) if i not in match]
    # Specific positions first, the flex slot last
    empty.sort(key=lambda s: (s == FLEX_SLOT, s))
    return started, empty


def roster_report(roster: list[set[str]], slots: dict[str, int], nominee: set[str] | None = None) -> dict:
    """Which slots are still empty, and whether the nominee would fill one."""
    started, empty = assign(roster, slots)
    report = {"unfilled": empty, "fills_open_slot": None, "still_empty_after": None}
    if nominee is not None:
        with_nominee, empty_after = assign(roster + [nominee], slots)
        report["fills_open_slot"] = with_nominee > started
        report["still_empty_after"] = empty_after
    return report


def clean_slots(raw, fallback: dict | None = None) -> dict[str, int]:
    """Validated roster spots, one whole number per position. Anything missing keeps
    its value from `fallback` (or 0). Raises ValueError with a message for the manager."""
    base = fallback or {}
    if not isinstance(raw, dict):
        raise ValueError("Roster spots must be a number for each position")
    slots = {}
    for name in SLOT_ORDER:
        value = raw.get(name, base.get(name, 0))
        if value in (None, ""):
            value = 0
        if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
            raise ValueError(f"{name} spots must be a whole number")
        try:
            count = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{name} spots must be a whole number") from None
        if not 0 <= count <= MAX_PER_SLOT:
            raise ValueError(f"{name} spots must be between 0 and {MAX_PER_SLOT}")
        slots[name] = count
    return slots


def roster_size(slots: dict[str, int]) -> int:
    """Players a team drafts: starters and bench. The injured list isn't drafted into."""
    return sum(count for name, count in slots.items() if name not in ("IL", "IL+"))


def starting_slots(slots: dict[str, int]) -> dict[str, int]:
    """Only the spots that start (no bench, no injured list), zero counts removed."""
    return {n: c for n, c in slots.items() if n not in NOT_STARTING_SLOTS and c > 0}


def eligible_from_listed_position(listed) -> set[str] | None:
    """Spots a player can fill from a listed position like 'G', 'SF' or 'G-F'.
    None when the position is missing or unknown. Looser than Yahoo, which can list
    several positions per player, so a 'G' counts for PG, SG and G alike."""
    eligible = set()
    for part in re.split(r"[-/,\s]+", str(listed or "").upper()):
        eligible |= _FILLS.get(part, set())
    return (eligible | {FLEX_SLOT}) if eligible else None
