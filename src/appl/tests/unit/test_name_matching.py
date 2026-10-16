from appl.draft.manual_league import match_import_teams
from appl.season.service import resolve_move_names


class StubRanker:
    """Knows two players; 'lebron' (any case) is LeBron James, 'curry' is Stephen Curry."""

    pool = {"lebron": "LeBron James", "curry": "Stephen Curry"}

    def find(self, name):
        found = next((v for w in name.lower().split() for k, v in self.pool.items() if w.startswith(k)), None)
        return {"name": found} if found else None

    def suggest_names(self, name, limit=4):
        return ["Somebody Close"]


def test_import_matching_uses_pool_spelling_and_reports_unknowns():
    teams = [{"name": "A", "players": ["lebron james", " ", "Zzz Qqq"]}, "not a team", {"players": None}]
    matched, unknown = match_import_teams(StubRanker(), teams)
    assert unknown == ["Zzz Qqq"]
    assert matched[0]["players"][0] == {"typed": "lebron james", "name": "LeBron James", "found": True}
    assert matched[0]["players"][1] == {"typed": "Zzz Qqq", "name": "Zzz Qqq", "found": False,
                                        "suggestions": ["Somebody Close"]}
    assert matched[1] == {"name": "", "players": []} and matched[2]["players"] == []


def test_move_names_are_fixed_to_pool_spelling():
    clean, problem = resolve_move_names(StubRanker(), {"kind": "add", "add": "curry, lebron", "drop": ["lebron j"]})
    assert problem is None
    assert clean["add"] == ["Stephen Curry", "LeBron James"] and clean["drop"] == ["LeBron James"]


def test_an_unknown_pickup_needs_a_confirmation():
    clean, problem = resolve_move_names(StubRanker(), {"kind": "add", "add": ["Zzz Qqq"]})
    assert problem["unknown_player"] and "Zzz Qqq" in problem["error"] and problem["suggestions"] == ["Somebody Close"]


def test_force_keeps_an_unknown_pickup_and_drops_are_never_blocked():
    clean, problem = resolve_move_names(StubRanker(), {"kind": "add", "add": ["Zzz Qqq"], "force": True})
    assert problem is None and clean["add"] == ["Zzz Qqq"]
    clean, problem = resolve_move_names(StubRanker(), {"kind": "drop", "drop": ["Zzz Qqq"]})
    assert problem is None and clean["drop"] == ["Zzz Qqq"]
