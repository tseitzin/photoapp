# Aperture — Implementation Tasks

Working rules: small focused PRs (300–600 lines), Conventional Commits, tests and
lint pass before a task is checked, docs updated when behavior changes.
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for design decisions.

## Phase 1 — Discovery & planning ✅ (2026-07-03)

- [x] Inspect project folder; classify design assets (HTML prototypes + spec, not Vue)
- [x] Summarize design, propose architecture, DB model, dedupe strategy, safety model
- [x] Surface near-duplicate candidate-selection decision (LSH banding recommended;
      pgvector path kept open)
- [x] Create README.md, docs/ARCHITECTURE.md, TASKS.md, CLAUDE.md
- [x] **Decision (Tim, 2026-07-03):** LSH banding approved for near-dup candidate
      selection
- [x] **Decision (Tim, 2026-07-03):** RAW skipped entirely in v1

## Phase 2 — Development foundation ✅ (2026-07-03)

- [x] **PR 2.1 — repo + scaffolds**: git init, .gitignore, docker-compose.yml
      (pgvector/pgvector:pg16, host port 5435), create-vue scaffold (Vue 3 + TS +
      Router + Pinia + Vitest + ESLint), backend venv + FastAPI skeleton,
      .env.example files
- [x] **PR 2.2 — backend core**: pydantic-settings config, JSON structured logging,
      SQLAlchemy 2 session setup, Alembic + migration 0001 (enable pgvector ext),
      GET /api/health (200 with database flag even when DB is down), pytest smoke
      tests; verified live on :8003 against Docker PG
- [x] **PR 2.3 — frontend shell**: design tokens as CSS custom properties (light/dark
      from the handoff spec), theme store persisted to localStorage['aperture-theme']
      (system preference as fallback), top bar + nav per design, routed placeholder
      views, typed API client (ApiError with status; 0 = unreachable), health wiring
      with offline banner + retry; CORS verified with real Origin header

## Phase 3 — Photo indexing ✅ (2026-07-03)

- [x] **PR 3.1 — scan roots**: model/migration/repo/service/API; rejects relative,
      nonexistent, duplicate, and nested/containing roots; DB test infra
- [x] **PR 3.2 — discovery walker**: streaming scandir generator, symlinks never
      followed, (dev,ino) cycle guard, hidden entries skipped, per-entry errors
      yielded without aborting
- [x] **PR 3.3 — processing pipeline**: single-pass read → sha256 + decode → EXIF/
      dimensions/camera; corrupt files indexed with last_error; ThreadJobRunner +
      ProcessPoolExecutor (SCAN_WORKERS); batched commits; scans API with progress,
      cancel, paginated errors
- [x] **PR 3.4 — incremental rescan**: skip unchanged (size+mtime), missing
      flagged not purged, moves detected by sha256 (photo id preserved),
      interrupted scans failed on startup; basic photos list/detail API
      (pagination + status filter). Verified live end-to-end incl. move+delete
      rescan with the real process pool.

## Phase 4 — Gallery integration ✅ (2026-07-03)

- [x] **PR 4.1 — thumbnails**: pHash + 512px webp thumbnails in the pipeline,
      sha256-addressed cache (regenerates on content change, wipe-safe), on-demand
      2048px previews, served by photo id only with immutable cache headers
- [x] **PR 4.2 — library core**: /api/folders tree with rolled-up counts, photo
      filters (folder/type/camera/search) + facets + 7 sorts; FolderTree, PhotoGrid
      with sections + IntersectionObserver infinite scroll, Library 3-pane layout
- [x] **PR 4.3 — filters + lightbox**: file-type chips + camera checkboxes from
      real facets, metadata panel, lightbox (keyboard nav, filmstrip, EXIF ISO),
      group-by segmented (Folders/Date/Camera) + debounced search in the top bar.
      *Deferred: min-rating filter — no favorite/rating data model in v1.*
- [x] **PR 4.4 — home + scan UI**: /api/stats (incl. exact-duplicate preview from
      sha256), Home dashboard (stat cards, entry cards, recent imports), Scan screen
      setup → scanning (1s polling, progress bar, stat tiles, cancel) → done,
      library shimmer skeleton + no-results state. Live-verified against a scratch
      library (tree rollup, facets, filters, thumbnails, duplicate stats).
- [x] Frontend tests: 25 vitest tests incl. photo loading, filtering, lightbox
      keyboard nav, scan progress/failure paths

## Phase 5 — Duplicate detection ✅ (2026-07-04)

- [x] **PR 5.1 — exact duplicates**: duplicate_groups/members/decisions tables,
      post-scan rebuild with stable (kind, key) identity (review state survives
      rescans; membership changes reopen groups), decisions API with remove-all
      guard, dismiss, summary, pagination
- [x] **PR 5.2 — similar photos**: 8 generated LSH band columns + indexes,
      in-memory banding + union-find for the rebuild, SQL band lookup +
      bit_count((a#b)::bit(64)) for GET /api/photos/{id}/similar, configurable
      threshold (default 6, complete ≤7), labeled "visually similar" throughout
- [x] **PR 5.3 — review UI**: groups list (kind filter, badges, dismiss), pair
      compare per design (similarity dial, diff table with highlighted rows,
      Keep A/B/both, skip, progress + resolved/freed chip); keeper re-anchors
      when the user keeps B. Single-click decide (design's confirm step dropped —
      decisions are reversible and actual deletion waits for Phase 6).
- [x] Frontend tests: 8 review-flow store tests (queue, decisions, keeper switch,
      error path). Live-verified end to end incl. decision → reviewed → summary.

## Phase 6 — Safe file management ✅ (2026-07-04)

- [x] **PR 6.1 — safety core**: resolved-path containment validation, quarantine
      (mirror absolute path under QUARANTINE_DIR, never overwrite), restore,
      permanent delete (confirm=true, quarantined-only, target revalidated),
      append-only file_operations audit, whole-group-wipe 409 guard with force,
      GET /api/duplicates/marked; 17 safety tests incl. traversal, symlink escape,
      and tampered-audit-row attacks. *Permanent-delete backend landed here
      (originally PR 6.3) — it is the same safety surface and test suite.*
- [x] **PR 6.2 — removal + delete UI**: /quarantine page (marked-for-removal list
      with confirm dialog, force strong-warning dialog on 409, quarantine browser
      with restore, permanent delete behind type-DELETE confirmation, audit
      history), link from Duplicates; ConfirmDialog component. 9 vitest tests
      (force flow, confirm gating, dialog behavior). Live-verified full lifecycle:
      mark → refuse wipe → quarantine → restore → delete → audit.
- [x] **PR 6.3** — merged into 6.1 (backend) and 6.2 (UI); see above.

## Phase 7 — Deferred / future

- [ ] Organize flow (move/tag/rename + destination picker) — conflicts with
      index-in-place; only after Phase 6 safety layer is proven
- [ ] Tags (non-destructive subset of Organize) — could move earlier if wanted
- [ ] pgvector embeddings for semantic similarity
- [ ] RAW support (rawpy), group-by-location, SSE progress
