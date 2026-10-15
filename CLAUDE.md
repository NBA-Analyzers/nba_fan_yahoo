# Fantasy Basketball Helper

Flask app: AI chat, draft assistant and in-season analysis for Yahoo, ESPN and manual
fantasy basketball leagues. Python 3.10 locally (Dockerfile uses 3.12). Deploys to Cloud Run.

## Commands
- Unit tests (offline, no keys): `python -m pytest -q`. The full suite takes about 2 minutes,
  so while iterating run just the relevant file: `python -m pytest -q src/appl/tests/unit/test_season.py`
- Integration tests (real Firestore): `FIRESTORE_TEST_PROJECT=<id> python -m pytest -m integration -q`
- Run the app locally: `cd src && python -m appl.app` (port 8000, `curl localhost:8000/health`)
- Data ingest jobs: `cd src && python -m appl.ingest run <general_index|player_pool|player_status|all>`
- CI (`.github/workflows/build-on-push.yml`) runs `py_compile` on all of `src` and then the unit tests.

## Layout
- `src/appl/` is the package root (`pytest.ini` sets `pythonpath = src`). Import as `appl.…`.
- `ai/` is the LLM + RAG layer, built as ports and adapters: interfaces live in `ai/ports.py`, LiteLLM
  adapters in `ai/litellm_adapters.py`, and chat tools in `ai/tools.py`. Design notes: `docs/AI_DESIGN.md`.
- `config/dependencies.py` is the single composition root: wire new services there, not in routes.
- `router/` holds the Flask blueprints. `season/`, `draft/` and `ingest/` hold the domain logic.
  `fantasy_integrations/` holds the Yahoo and ESPN clients.
- `static/` holds a plain HTML/JS frontend with no build step.
- `docs/` has the design, deploy and setup docs. Read the matching one before changing a subsystem.

## Conventions
- Never import provider SDKs (openai, litellm) outside `ai/litellm_adapters.py`. Services depend on ports.
- Errors leaving the AI layer must pass through `ai/redact.py` (`scrub_secrets`) so no keys leak.
- Unit tests must stay offline: use the fakes in `tests/unit/conftest.py` (`FakeLLMClient`,
  `FakeEmbedder`) and `tests/unit/fake_firestore.py`. Mark anything that needs real services
  `@pytest.mark.integration`.
- Every behavior change gets a unit test. For bugs, write the failing test first.
- Models and keys come from env vars (see `docs/SETUP_CHECKLIST.md`). Never hardcode them.
- IMPORTANT: Never read or print `.env*` files, and never commit secrets. `.claude/settings.local.json` is personal.

## Workflow
- For multi-file changes, explore and plan first. Small, obvious fixes can go straight to code.
- Before saying a task is done, run the relevant tests and show the output.
- Commit messages: a short sentence in plain English describing the user-visible change
  (see `git log`). Work on a branch; `main` deploys.
