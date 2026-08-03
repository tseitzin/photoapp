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

## Phase 7 — Organize ✅ (2026-07-12)

- [x] **PR 7.1** — Organize flow (move/rename + destination picker). Physical
      moves through the audited `files/` layer: modes keep-structure / by-date
      (`YYYY/MM/`, `Undated/` fallback) / by-camera; rename to capture timestamp
      with `_01` collision suffixes; skip-duplicates (keeper only). Shared plan
      builder powers both `POST /api/organize/preview` (dry-run, zero disk I/O)
      and the background execute job (`organize_runs` + 1s polling, chunked
      commits, `op="organize"` audit rows). Organize screen per the handoff
      (working set ← Library folder checkboxes, destination picker modal,
      toggles, preview rail, success banner); Tags card deferred. 20 pytest +
      13 vitest tests.
- [x] **PR 7.2** — GPS groundwork: scanner reads the EXIF GPS IFD into
      `photos.latitude/longitude` (migration 0012);
      `POST /api/maintenance/backfill-gps` cursor-sweeps photos indexed before
      the change. No location UI yet.

## Phase 8 — Library usability ✅ (2026-08-02)

- [x] Destination picker accepts typed absolute paths and nested subpaths; folder
      names with colons or edge whitespace rejected; outside destinations
      auto-registered as scan roots; destination and mode remembered across
      sessions. Clicking a folder name filters the grid (the checkbox stays the
      separate "selected for organizing" gesture).
- [x] Grid multi-selection: click selects, **Shift+click** adds the run from the
      anchor (additive, so a scattered ⌘-click set survives), **⌘/Ctrl+click**
      toggles one. Selection bar marks/unmarks the whole set in 500-id batches.
      Page-scoped — cleared on every refetch so a bulk action cannot reach photos
      that are no longer visible.
- [x] Source folders are never pruned after an organize move — codified in
      `CLAUDE.md` and pinned by a regression test.

## Phase 9 — Scale, rendering and safety ✅ (2026-08-02)

- [x] **Query indexes** (migration 0013) — composites matching the real
      filter+sort pairs, `text_pattern_ops` for the folder prefix, `pg_trgm` GIN
      for filename search. Default page 11.7ms → 0.09ms; deep page 19.6ms with a
      disk-spilled sort → 2.1ms with none. Declared on the model too, with a test
      that model and migration agree.
- [x] **`exif` deferred on list queries** — ~1.3 KB inline per row that no list
      schema exposes.
- [x] **Near-duplicate grouping made memory-linear** — dropped the pair memo
      (418 MB at n=18k, projecting past 3 GB at 50k) for a union-find check:
      4.4 MB and 2.4× faster, results verified identical against a brute-force
      all-pairs reference.
- [x] **Duplicate rebuild skipped when a scan changed nothing.**
- [x] **`PhotoTile` extracted** so selection re-renders one tile instead of
      re-diffing ~23,000 vnodes; tile-size slider taken off the grid's render
      path; scan/organize polling stopped on navigation.
- [x] **Bulk-action safety** — real busy state, visible errors on a loaded grid
      (previously silent), Library refreshed after quarantine/restore/delete
      (facets had no refresh path at all), stale page responses ignored.
- [x] **Location UI** — coordinates + map link in the details panel and lightbox;
      "Find locations" on the Scan screen runs the GPS backfill.
- [x] **"More like this"** strip in the lightbox, and a **scan-errors drill-down**
      — both endpoints existed and had no caller.

## Phase 10 — Place names ✅ (2026-08-02)

- [x] Offline reverse geocoding (`app/geo/places.py`): a k-d tree over ~150k
      bundled GeoNames cities via `reverse_geocoder`. No web geocoding service —
      photo coordinates never leave the machine. Nearest-place semantics are
      explicit: `distance_km` is part of the result, the UI reads "near X" past
      5 km, and beyond `PLACE_MAX_KM` no place is recorded.
- [x] `photos.city/region/country/place_distance_km` (migration 0014), filled
      during scans (in the parent process — the tree is ~100 MB and must not be
      built per worker) and by the GPS backfill, batched one call per chunk.
- [x] Place shown in the Library details panel and the lightbox, above the
      coordinates and the map link.

## Deferred / future

- [ ] Tags (non-destructive subset of Organize; card exists in the design)
- [ ] Group-by-location UI and a map view (coordinates and place names now
      exist; grouping, filtering and a map do not)
- [ ] pgvector embeddings for semantic similarity
- [ ] RAW support (rawpy), SSE progress
- [ ] Grid virtualization (the handoff asks for it; the Phase 9 render fixes
      removed the measured jank without it)
- [ ] Incremental similar-grouping (compare only new hashes against existing
      bands) if the per-scan cost bites before embeddings land
