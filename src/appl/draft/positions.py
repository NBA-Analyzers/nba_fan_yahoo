"""
Roster slot checks for position leagues (PG, SG, G, SF, PF, F, C, Util ...).

Warn-only: prices ignore positions, but the page tells the manager which slots
their roster can't yet fill and whether a nominated player would fill one.
Eligibility comes from Yahoo (each player's eligible_positions), and the
required slots from the league's own roster settings.
"""

NOT_STARTING_SLOTS = {"BN", "IL", "IL+", "IR", "NA"}
FLEX_SLOT = "Util"


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
