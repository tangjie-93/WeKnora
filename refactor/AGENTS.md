# Repository Guidelines

Repository: [tangjie-93/WeKnora](https://github.com/tangjie-93/WeKnora). Clone with `git clone https://github.com/tangjie-93/WeKnora.git`.

## Project Structure & Module Organization

This workspace contains the phased Python replacement for WeKnora. Preserve existing database schemas and `/api/v1` contracts.

- `python/backend/app/`: `FastAPI` routes and schemas, services, repositories, domain entities, integrations, and core configuration. Keep business logic in services and persistence in repositories.
- `python/backend/tests/`: unit tests, API end-to-end tests, shared fixtures, and contract reports.
- `python/backend/scripts/`: stage acceptance, model setup, and local fake-model tooling.
- `python/frontend/src/`: standalone `Vue 3` application, pages, API client, and styles.
- `integration-web/src/`: separate integration UI; keep its assets and components within this application.
- `docs/`: architecture, progress, and supporting documentation. `server-deploy/` holds deployment assets.

## Build, Test, and Development Commands

Use Python `3.12+` and a virtual environment. Backend commands run from `python/backend/`:

- `python -m pip install -e ".[dev]"`: install backend and development dependencies.
- `python -m uvicorn app.main:app --port 8080 --reload`: start the API; check `/health`.
- `python -m pytest -q`: run the backend suite.
- `python -m ruff check .`: run configured lint checks.
- `python scripts/stage_check.py --stage phase1`: run phase acceptance; select the applicable phase. Execute stages serially because they share database and log files.

In either frontend directory, run `npm install`, then `npm run dev`. `python/frontend` serves port `5400` and proxies API requests to `8080`; `integration-web` serves port `8300`. Run `npm run build` for TypeScript checking and production output.

## Coding Style & Naming Conventions

Use four-space Python indentation, `snake_case` functions/modules, and `PascalCase` classes. `Ruff` targets Python `3.12` with a `110`-character line limit. Follow surrounding TypeScript indentation and quote style; use `PascalCase.vue` component names. Reuse existing authentication, API, and service helpers.

## Testing Guidelines

Use `pytest` and `pytest-asyncio`; name files `test_*.py`. Put pure logic checks in `tests/unit/` and API workflows in `tests/e2e/`. Reuse `tests/conftest.py` fixtures and fake model services. No numeric coverage threshold is configured; cover changed behavior, permission failures, and persistence. Real-model tests require explicit `RUN_REAL_LLM=1` configuration and credentials.

## Commit & Pull Request Guidelines

History uses scoped conventional messages: `feat(scope): ...`, `fix(scope): ...`, `docs(refactor): ...`, and `chore(refactor): ...`. Keep commits focused. Describe behavior changes, link relevant issues, report validation commands/results, and include screenshots for UI changes.

## Security & Configuration

Copy backend `.env.example` to `.env` when needed. Keep credentials, local databases, and real-model secrets out of commits and test reports.
