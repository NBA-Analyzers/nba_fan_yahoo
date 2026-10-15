import json
from datetime import date

import pytest

from appl.ai.chat_service import MAX_TOOL_ROUNDS, ChatService
from appl.ai.ports import LLMReply, ToolCall
from appl.ai.retrieval import RetrievalService
from appl.ai.tools import TOOL_SPECS, Toolkit, league_toolkit_factory
from appl.draft.manual_league import ManualLeagueStore
from appl.season.player_status import PlayerData
from appl.service.chat_session_manager import ChatSessionManager
from appl.tests.unit.test_season import USER, _drafted_league, _snapshot_league

TODAY = date(2026, 11, 2)


@pytest.fixture
def toolkit():
    ranker, snap = _snapshot_league(teams=6, size=5)
    return Toolkit(ranker, snap, schedule=None, today=TODAY)


def result(toolkit, tool, **args):
    return json.loads(toolkit.call(tool, args))


def make_service(llm, embedder, memory_store, factory):
    return ChatService(
        llm=llm,
        retrieval=RetrievalService(embedder, memory_store, top_k=3),
        sessions=ChatSessionManager(),
        system_prompt="You are a fantasy expert.",
        tools_factory=factory,
    )


# ---------- the tools ----------
def test_every_spec_has_a_handler(toolkit):
    for spec in TOOL_SPECS:
        assert hasattr(toolkit, f"tool_{spec['function']['name']}")


def test_overview_reports_my_categories_and_date(toolkit):
    out = result(toolkit, "get_team_overview")
    assert out["as_of"] == "2026-11-02"
    assert {c["category"] for c in out["categories"]} == set(toolkit.ranker.categories)
    assert out["my_team"]["name"] == toolkit.snapshot.team_names[toolkit.snapshot.my_team]


def test_standings_are_ordered_by_place(toolkit):
    places = [t["place"] for t in result(toolkit, "get_standings")["teams"]]
    assert places == sorted(places) == list(range(1, 7))


def test_pickups_trades_drops_and_streamers_run(toolkit):
    assert "pickups" in result(toolkit, "suggest_pickups")
    assert "trades" in result(toolkit, "suggest_trades", punts=["TOV"])
    assert len(result(toolkit, "suggest_drops")["drops"]) <= 3
    assert result(toolkit, "suggest_streamers")["available"] is False  # no schedule given


def test_matchup_without_an_opponent_says_so(toolkit):
    assert result(toolkit, "get_matchup")["available"] is False


def test_matchup_by_team_name(toolkit):
    other = toolkit.snapshot.team_names[1]
    out = result(toolkit, "get_matchup", opponent=other)
    assert out["available"] and out["opponent"]["name"] == other


def test_unknown_team_lists_the_real_ones(toolkit):
    out = result(toolkit, "get_team_roster", team="Nobody")
    assert "error" in out and out["teams"] == toolkit.snapshot.team_names


def test_roster_defaults_to_my_team(toolkit):
    out = result(toolkit, "get_team_roster")
    assert out["is_my_team"] and len(out["players"]) == 5


def test_lookup_player_names_the_owner(toolkit):
    name = toolkit.snapshot.rosters[toolkit.snapshot.my_team][0]
    out = result(toolkit, "lookup_player", name=name)
    assert out["name"] == name
    assert out["rostered_by"] == toolkit.snapshot.team_names[toolkit.snapshot.my_team]
    assert out["per_game"]["PTS"] >= 0


def test_lookup_unknown_player_suggests_names(toolkit):
    out = result(toolkit, "lookup_player", name="Zzzzz Qqqqq")
    assert "error" in out and "did_you_mean" in out


def test_bad_tool_calls_return_errors_not_exceptions(toolkit):
    assert "error" in result(toolkit, "no_such_tool")
    assert "error" in result(toolkit, "lookup_player")  # missing required name
    assert "error" in result(toolkit, "get_standings", surprise=1)


def test_huge_results_are_truncated(toolkit, monkeypatch):
    monkeypatch.setattr("appl.ai.tools.MAX_RESULT_CHARS", 50)
    assert toolkit.call("get_standings", {}).endswith('"[truncated]"')


# ---------- the loop ----------
def test_loop_runs_tools_then_returns_the_final_answer(llm, embedder, memory_store, toolkit):
    llm.turns = [
        LLMReply(tool_calls=(ToolCall("c1", "get_standings", {}),)),
        LLMReply(content="You are 3rd."),
    ]
    service = make_service(llm, embedder, memory_store, lambda req: toolkit)
    assert service.chat({"session_id": "s", "user_message": "where am I?"}) == "You are 3rd."

    second_call = llm.calls[1]
    assert second_call[-2]["role"] == "assistant" and second_call[-2]["tool_calls"][0]["id"] == "c1"
    assert second_call[-1]["role"] == "tool" and second_call[-1]["tool_call_id"] == "c1"
    assert "teams" in json.loads(second_call[-1]["content"])
    assert llm.tools_offered == TOOL_SPECS


def test_tool_messages_are_not_saved_in_history(llm, embedder, memory_store, toolkit):
    llm.turns = [LLMReply(tool_calls=(ToolCall("c1", "get_standings", {}),)), LLMReply(content="done")]
    service = make_service(llm, embedder, memory_store, lambda req: toolkit)
    service.chat({"session_id": "s", "user_message": "hi"})
    assert [m["role"] for m in service.sessions.history("s")] == ["user", "assistant"]


def test_loop_stops_after_the_round_limit(llm, embedder, memory_store, toolkit):
    llm.turns = [LLMReply(tool_calls=(ToolCall(f"c{i}", "get_standings", {}),)) for i in range(20)]
    llm.reply = "final"
    service = make_service(llm, embedder, memory_store, lambda req: toolkit)
    assert service.chat({"session_id": "s", "user_message": "loop"}) == "final"
    assert len(llm.calls) == MAX_TOOL_ROUNDS + 1  # the rounds plus the forced answer


def test_system_prompt_gets_todays_date_when_tools_are_on(llm, embedder, memory_store, toolkit):
    service = make_service(llm, embedder, memory_store, lambda req: toolkit)
    service.chat({"session_id": "s", "user_message": "hi"})
    assert date.today().isoformat() in llm.calls[0][0]["content"]


def test_without_a_toolkit_the_plain_path_is_used(llm, embedder, memory_store):
    service = make_service(llm, embedder, memory_store, lambda req: None)
    llm.reply = "plain"
    assert service.chat({"session_id": "s", "user_message": "hi"}) == "plain"
    assert llm.tools_offered == []


# ---------- the manual-league factory ----------
def test_factory_builds_a_toolkit_for_the_owner_only(tmp_path, monkeypatch, toolkit):
    monkeypatch.setattr("appl.ai.tools.ranker_for", lambda snap: toolkit.ranker)  # the real one fetches stats
    store = ManualLeagueStore(tmp_path)
    league = _drafted_league(store)
    build = league_toolkit_factory(store, load_data=PlayerData.empty)

    mine = build({"league_id": f"manual-{league['id']}", "user_id": USER})
    assert mine is not None and mine.snapshot.name == "Friends"
    assert build({"league_id": f"manual-{league['id']}", "user_id": "someone-else"}) is None
    assert build({"league_id": "12345", "user_id": USER}) is None  # a Yahoo id, and Yahoo isn't connected
    assert build({"league_id": f"manual-{league['id']}"}) is None  # no user
