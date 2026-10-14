"""
Jev picks the single best move from the analyzer's trade ideas and pickups.

The analyzer does the arithmetic; Jev gets each move already labeled with the
category places it gains or loses. Without Jev the analyzer's top move stands.
"""

from ..draft import jev_chooser

MAX_OPTIONS = 8

INSTRUCTIONS = (
    "Which roster move should this fantasy basketball manager make this week? "
    "Each option lists the roto points it gains and the places it gains (+) or "
    "loses (-) in each counted category. Prefer moves that gain the most points, "
    "fix weak categories without giving up strong ones, and that the other team "
    "would plausibly accept (their_value_change near or above zero). Punted "
    "categories don't matter. Follow the manager's stated preference when there is one."
)


def describe(move: dict) -> str:
    if move["type"] == "trade":
        text = f"Trade with {move['partner_name']}: give {' + '.join(move['give'])} for {' + '.join(move['get'])}"
        if move.get("pickup"):
            text += f", then pick up {move['pickup']}"
        return text
    return f"Pick up {move['add']}, drop {move['drop']}"


def candidate_moves(report: dict) -> list[dict]:
    """The analyzer's moves, best first, tagged with their type."""
    moves = [{"type": "trade", **t} for t in report.get("trades", [])]
    moves += [{"type": "pickup", **p} for p in report.get("pickups", [])]
    moves.sort(key=lambda m: m["points_gain"], reverse=True)
    return moves[:MAX_OPTIONS]


def _criteria(move: dict) -> dict:
    criteria = {
        "points_gain": move["points_gain"],
        "category_places": {c: f"{d:+d}" for c, d in move["category_changes"].items()},
    }
    if move["type"] == "trade":
        criteria["their_value_change"] = f"{move['their_value_change']:+.1f}"
    else:
        criteria["value_gain"] = f"{move['value_gain']:+.1f}"
    return criteria


def recommend(report: dict, preference: str = "", client=None) -> dict | None:
    """{"source": "jev"|"engine", "move", "text", "confidence", "options", "note"}.
    None when there is no move worth making."""
    moves = candidate_moves(report)
    if not moves:
        return None
    by_text = {describe(m): m for m in moves}
    engine_text = describe(moves[0])

    state = {
        "situation": "Fantasy basketball, category league, in season. Choose one move.",
        "my_team": report["my_team"]["name"],
        "standing": f"{report['my_team']['place']} of {report['num_teams']}",
        "punted_categories": report.get("punts", []),
        "my_categories": {
            r["category"]: f"rank {r['rank']} ({r['label']})"
            for r in report.get("my_categories", []) if not r["punted"]
        },
    }
    if preference.strip():
        state["manager_preference"] = preference.strip()[: jev_chooser.MAX_PREFERENCE_CHARS]

    jev = jev_chooser.ask(state, {t: _criteria(m) for t, m in by_text.items()}, INSTRUCTIONS, client)
    if jev is None or jev["pick"] not in by_text:
        return {
            "source": "engine",
            "move": moves[0],
            "text": engine_text,
            "confidence": None,
            "options": [],
            "note": "Jev is unavailable, showing the move that gains the most points."
            if jev_chooser.is_configured() or client is not None
            else "JEV_API_KEY is not set, showing the move that gains the most points.",
        }
    return {
        "source": "jev",
        "move": by_text[jev["pick"]],
        "text": jev["pick"],
        "confidence": jev["confidence"],
        "options": jev["options"],
        "agrees_with_engine": jev["pick"] == engine_text,
        "note": None,
    }
