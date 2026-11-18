# Project conventions (for humans and AI assistants)

- Goal and design: docs/TARGET_ARCHITECTURE.md. Work order: docs/IMPLEMENTATION_PLAN.md. Findings log: docs/AUDIT.md.
- Python 3.12, `src/crag/` layout. Layering `apps -> pipelines -> adapters -> core -> domain`; never import upward (import-linter enforces it).
- `legacy/server/` is the frozen baseline (B0) for evals. Only security fixes go there.
- Quality gate before every PR: `make check` (ruff, mypy, import-linter, pytest).
- No `except: pass`; degraded behaviour must be explicit. No document text in logs.
- Prompts are versioned files under `prompts/`; changing one requires an eval run.
- Commits: imperative subject, conventional prefix (feat/fix/chore/docs/test). No co-author or generated-by trailers; the repo owner is the sole author.
