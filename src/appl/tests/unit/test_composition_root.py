"""register_routes builds nothing itself: every shared service comes from config/dependencies."""

from types import SimpleNamespace

import pytest
from flask import Flask

import appl.router as router
from appl.draft.manual_league import ManualLeagueStore
from appl.draft.service import DraftService
from appl.season import report_writer
from appl.tests.unit.conftest import FakeLLMClient


class FakeIndexer:
    def update_league_files(self, *args, **kwargs):
        pass


@pytest.fixture
def shared(tmp_path, monkeypatch):
    shared = SimpleNamespace(
        indexer=FakeIndexer(),
        store=ManualLeagueStore(tmp_path),
        espn=SimpleNamespace(league_repo=object()),
        drafts=DraftService(),
        briefs=report_writer.BriefStore(use_firestore=False),
        tokens=object(),
        schedule=object(),
        chat=SimpleNamespace(),
        llm=lambda: FakeLLMClient("x"),
    )
    for name, value in {
        "document_indexer": shared.indexer, "manual_store": shared.store, "espn_service": shared.espn,
        "draft_service": shared.drafts, "brief_store": shared.briefs, "token_store": shared.tokens,
        "schedule": shared.schedule, "chat_service": shared.chat,
    }.items():
        monkeypatch.setattr(router, name, lambda value=value: value)
    monkeypatch.setattr(router, "llm_factory", shared.llm)
    return shared


def test_the_routers_share_the_services_from_the_composition_root(shared, monkeypatch):
    built = {}
    for cls_name in ("DraftRouter", "SeasonRouter"):
        real = getattr(router, cls_name)

        def spy(*args, _real=real, _name=cls_name, **kwargs):
            built[_name] = (args, kwargs)
            return _real(*args, **kwargs)

        monkeypatch.setattr(router, cls_name, spy)

    app = Flask(__name__)
    app.secret_key = "test"
    router.register_routes(app)

    draft_args, draft_kwargs = built["DraftRouter"]
    assert draft_args == (shared.store, shared.tokens, shared.espn)
    assert draft_kwargs["drafts"] is shared.drafts
    season_args, _ = built["SeasonRouter"]
    assert season_args == (shared.store, shared.briefs, shared.llm, shared.schedule, shared.espn)
    assert {"draft", "season", "chat"} <= set(app.blueprints)


def test_set_services_builds_the_shared_services_once(monkeypatch, tmp_path):
    from appl.config import dependencies as deps
    from appl.tests.unit.conftest import FakeEmbedder

    monkeypatch.setattr(deps, "build_retrieval_service", lambda: SimpleNamespace(embedder=FakeEmbedder()))
    monkeypatch.setattr(deps.LiteLLMClient, "from_env", staticmethod(lambda: FakeLLMClient("x")))
    monkeypatch.setattr(deps, "default_store", lambda: None)  # chat sessions stay in memory
    monkeypatch.setattr(deps, "default_manual_store", lambda: ManualLeagueStore(tmp_path))
    monkeypatch.setattr(deps, "default_token_store", lambda: object())
    monkeypatch.setattr(deps, "EspnService", lambda indexer: SimpleNamespace(indexer=indexer))
    monkeypatch.setattr(deps.report_writer, "BriefStore", lambda: object())
    monkeypatch.setattr(deps.Schedule, "load", staticmethod(lambda: object()))

    deps.set_services()

    assert deps.espn_service().indexer is deps.document_indexer()
    assert deps.chat_service().tools_factory is not None  # every league type gets the season tools
    assert deps.draft_service() is deps.draft_service() and deps.schedule() is deps.schedule()
