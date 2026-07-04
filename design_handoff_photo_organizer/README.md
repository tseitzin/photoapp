# Handoff: Aperture — Photo Organizer (Vue front end)

## Overview
Aperture is a desktop web app for managing very large personal photo collections (tens of thousands of files spread across drives). It talks to a backend API that exposes a database of every image's location on disk. The front end lets the user:

- See all folders where photos live, as a tree with counts.
- Browse a fast, virtualized thumbnail grid, grouped by folder / date / camera / location, with filtering.
- View any image full-screen (lightbox) with metadata and keyboard navigation.
- Find and remove duplicates by comparing matches side-by-side.
- Organize (move/tag/rename) a selected set of folders into a destination.
- Run a first-time drive scan that indexes the library.

Target stack: **Vue 3** (the user is building in Vue). No component library is assumed — pick one that fits, or hand-roll. These files are the visual + behavioral source of truth.

## Start here (for Claude Code)
You are implementing this design as a real Vue 3 web app.
1. Read this README end-to-end, then open each file in `screens/` in a browser and click through it — the HTML prototypes are the source of truth for look and behavior.
2. Look at `screenshots/` for a quick visual index (light + dark).
3. Scaffold a Vue 3 project (Vite). Build each screen as a route/view + components, using the state model and design tokens below.
4. Replace all mocked data with calls to the backend API (see “Data the front end expects”). Every folder, count, thumbnail, duplicate, and scan number in the prototype is fake.
5. Do **not** port `support.js` or the `.dc.html` format — they are prototype scaffolding only.

## About the Design Files
The files in `screens/` are **design references built as HTML prototypes** — they show the intended look and behavior. They are **not production code to copy**. Recreate them as Vue components using your project's conventions (SFCs, your state approach, your data layer). All data in the prototypes is **mocked in-file**; every number, folder, thumbnail, and duplicate is fake and must be replaced by real API data.

> The prototypes are authored in a small streaming-component runtime (`support.js`). You do **not** need that runtime or its `.dc.html` format in the real app — read them as reference. To preview a file, open it in a browser (it loads `support.js` from the same folder). Logic lives in the `<script data-dc-script>` block at the bottom of each file; markup is the template above it. Inline `style="…"` is used throughout, and colors are CSS custom properties defined on each screen's root element (see Design Tokens).

## Fidelity
**High-fidelity.** Colors, typography, spacing, radii, and interactions are final. Recreate pixel-close. The one liberty: thumbnails are muted gradient placeholders standing in for real photos — wire real `<img>` thumbnails in their place (same tile size/radius).

---

## Global system

**Shell.** Every primary screen is a full-viewport (`100vh`) flex column: a **top bar** (height 52–58px) + a body. The top bar holds: logo (links Home), a text nav (Home · Library · Duplicates · Organize) with the active item filled, and right-aligned controls ending in a **light/dark toggle** (sun/moon segmented) and a JD avatar.

**Theme.** Light and dark are full palettes swapped by toggling CSS custom properties on the root element. The choice is **persisted in `localStorage` under key `aperture-theme`** (`'light'`|`'dark'`) and read on load, so it carries across screens. Implement as a shared store/composable.

**Navigation map.**
- Home → Library, Duplicates, Organize (cards + nav)
- Library sidebar → Organize ("Organize" button), Duplicates ("Find dupes" button); thumbnails → lightbox (in-screen overlay, not a route)
- Empty state → Scan; Scan "done" → Home / Duplicates
- Organize "Browse" → destination-picker modal (in-screen)

---

## Screens / Views

### 1. Home (`screens/Home.dc.html`)
**Purpose:** landing dashboard; jump into the main tasks.
**Layout:** top bar; scrollable content centered at `max-width:1180px`, padding `36px 40px`.
- Greeting (`13px` muted + `28px/700` title).
- **Stats row:** 4 cards (`grid` 4×), each = uppercase label (`11px` muted) + big mono value (`26px/700`) + sub caption. Values: Photos 48,210 / Storage 214 GB / Duplicates 1,284 (sub "6.8 GB reclaimable") / Untagged 9,120.
- **Entry cards:** 3-up grid. (a) *Browse library* — 3×2 mini mosaic + title + "48,210 photos · 1,043 folders". (b) *Review duplicates* — **emphasized** with `1.5px` accent border + accent shadow, a stacked-photos glyph on a tinted header, "6.8 GB free" badge, "1,284 duplicates · 412 groups". (c) *Organize folders* — two working-set rows + "2 folders selected · 5,994 photos". Whole card is the link.
- **Recent imports:** section header + "View all →"; responsive thumbnail grid (`minmax(112px,1fr)`), tiles link to Library.

### 2. Library (`screens/Library.dc.html`) — the core screen
**Purpose:** browse/filter/select folders and photos; open the viewer.
**Layout:** top bar (adds a **group-by segmented** control: Folders · Date · Camera · Location) + 3-pane body:
- **Left sidebar (266px):** "LIBRARY" label + **folder tree**. Each row: disclosure chevron (▸/▾, only if the node has children), a 15px checkbox, a folder marker, name (root is 600 weight), right-aligned mono count. Indent = `12 + depth*18` px. Bottom: **"Selected for organizing"** card showing live count of checked folders + summed photos, and Organize / Find dupes buttons.
- **Center (flex):** subheader (breadcrumb + total count + Sort control + a thumbnail-size slider) then the **grid**, rendered as **sections** per the active group-by. Each section = header (title + mono sub-count + hairline rule) + responsive grid of square tiles (`minmax(112px,1fr)`, gap 9px, radius 4px). Tiles show optional ★ favorite (top-right) and `RAW` badge (bottom-left); the selected tile has a `3px` inset accent ring.
- **Right panel (302px):** "FILTERS" — file-type chips (JPEG/RAW/PNG/HEIC with counts, toggle on/off), camera checkboxes with counts, a minimum-rating stars row; divider; "METADATA" for the selected photo (3:2 preview + filename + key/value rows).
- **Lightbox (overlay, `position:fixed; z-index:60`, dark regardless of theme):** filename + "N / total" counter, favorite/rotate/close controls; big 3:2 image with left/right circular arrows; centered metadata row (Dimensions/Size/Camera/ISO/Captured); bottom **filmstrip** (64px thumbs, current ringed). **Keyboard:** ←/→ navigate, Esc closes.

**Interactions:**
- Chevron click → expand/collapse that node (toggles visibility of descendants); must `stopPropagation` so it doesn't also toggle the checkbox.
- Row click (anywhere but chevron) → toggle that folder's selection; updates the "Selected for organizing" totals live.
- Group-by tab → re-sections the grid (folders → per-folder; date → months; camera → models; location → places).
- File-type chips / camera checkboxes → toggle filter state.
- Thumbnail click → open lightbox at that index; arrows/filmstrip change index; metadata + preview follow the index.

### 3. Duplicate Compare (`screens/Duplicate Compare.dc.html`)
**Purpose:** resolve duplicates one pair at a time.
**Layout:** top bar (adds a thin progress bar + "Pair N / 412" + a "resolved / freed" chip) + body: **two large image panes (A left, B right)** with a center column between them: a **similarity dial** (conic ring filled to the match %, big % in the middle, label: pixel-identical ≥100 / visually similar ≥98 / similar crop) over a **diff table** (rows: Dimensions, File size, Format, Captured, SHA-256, Folder; A and B columns; **rows that differ are highlighted** — tinted bg + red B value; identical rows neutral). Pane A is tagged "Suggested keeper" (green), pane B "Duplicate" (red). Footer: **Keep A / Keep B / Keep both** + "Deleting B reclaims X" + Confirm.

**Interactions:** any decision records it, increments *resolved* and *freed* (by the deleted file's size), and advances to the next pair. Prev/next arrows browse without deciding. Everything (dial, diff highlights) recomputes per pair, in both themes.

### 4. Organize (`screens/Organize.dc.html`)
**Purpose:** configure and preview a move/tag/rename operation on a set of folders.
**Layout:** top bar (+ Discard, + primary "Organize N photos") + optional success banner + 3-pane body:
- **Left (296px) "Working set":** removable folder rows (thumb + name + count + ×) and "+ Add folders".
- **Center (scroll, `max-width:640px`):** cards — **Destination** (path field + **Browse** + a *Keep structure / By date / By camera* segmented + helper text), **Tags** (active removable chips + suggested chips), **Rename files** (toggle + live `old → new` example), **Skip duplicates** (toggle; note "872 exact duplicates … won't be copied").
- **Right (340px) "Preview":** big mono moved-count, example destination paths (rewrite live per destination + rename), applied tags, a summary table (Photos moved / Duplicates skipped / Tags added / Est. space), and a primary Organize button.
- **Destination picker modal** (`position:fixed; z-index:70`, dimmed backdrop, 520px opaque card): a destination **folder tree** (expandable drives, single-select, selected row tinted), "New folder", live selected path, Cancel / Choose. Choose writes the path back into Destination and updates the preview.

**Interactions:** removing a folder, toggling skip-dupes, changing destination mode, adding/removing tags, and toggling rename all recompute the moved count, example paths, and space estimate live. Apply shows the success banner.

### 5. Scan / First run (`screens/Scan.dc.html`)
**Purpose:** index the user's drives on first use (or re-scan).
**Three phases (single screen):**
- **Setup:** intro + **Sources** list (selectable rows: checkbox, icon, path, "Internal SSD / External drive", size) + "+ Add a folder" + "Include subfolders" toggle + "Start scan" + "N of M sources selected".
- **Scanning:** spinner + "Scanning your drives…" + current path; a **progress bar** with "found of ~total" + %; 4 stat tiles (Photos / Folders / Duplicates / Data); a **"Recently indexed"** list that prepends folders as they're found; Cancel.
- **Done:** green check + "Your library is ready" + summary sentence + stat tiles + "Open library →" / "Review 1,284 duplicates".

**Interactions:** Start scan runs the scan (in the prototype it's a simulated timer stepping `found` toward the target and updating stats/paths/log; **replace with real progress from the backend** — SSE/WebSocket/polling). On completion → Done. Cancel → Setup.

### 6. Library States (`screens/Library States.dc.html`) — reference only
Not a route. A dev switcher previews the four Library center states in context:
- **Loading:** shimmer skeleton header + skeleton tile grid (`@keyframes` shimmer).
- **Empty:** striped placeholder + "No photos indexed yet" + "Run a scan" / "Add folders" (→ Scan).
- **No results:** magnifier glyph + "No photos match these filters" + the active filter chips + "Clear all filters".
- **Error/offline:** red "!" + "Can't reach the library service" + mono error detail (`ECONNREFUSED · localhost:8787`) + Retry / Troubleshoot; sidebar dimmed.

---

## Interactions & Behavior (cross-cutting)
- **Theme toggle:** swaps the root's CSS-variable palette; persist to `localStorage['aperture-theme']`; read on mount.
- **Lightbox keyboard:** `ArrowLeft`/`ArrowRight` move, `Escape` closes; only active while open.
- **Toggles/switches:** 44×25 track, 21px knob, knob `translateX(19px)` when on, `transition: transform .15s`, track = accent when on / `--cb-border` when off.
- **Segmented controls:** 2px padding track (`--seg-bg`); active pill = `--seg-active-bg` + `--seg-active-fg` + subtle shadow; inactive = `--sub` text.
- **Scan progress bar / duplicate progress:** width driven by %, `transition: width .12s linear`.
- **Modals:** fixed full-screen dimmed backdrop (`rgba(9,9,11,.5)`), centered opaque card; the card and its contents must read the theme variables (define the palette on the modal root or a shared themed ancestor).
- No route transitions specified; use instant navigation. Selection/scan/organize state is per-screen local state (plus the shared theme).

## State Management
Suggested stores/composables:
- **theme**: `theme`, `toggle()`, persisted.
- **library**: folder tree + `expanded` set + `checkedFolderIds` set (drives the "selected for organizing" totals); `groupBy`; filter state (`fileTypes`, `cameras`, `minRating`, search); `selectedPhotoIndex` + `lightboxOpen`.
- **duplicates**: `pairs` (or lazy fetch), `index`, running `resolved` + `freedBytes`, per-decision advance.
- **organize**: `workingSet` (folders), `destination` (path + mode), `tags`, `rename`, `skipDuplicates`, derived `movedCount`/`example paths`/`estSpace`, `pickerOpen` + picker tree state.
- **scan**: `phase` (`setup`|`scanning`|`done`), `sources`, `includeSubfolders`, live `found/folders/dupes/currentPath/recent[]`.

## Data the front end expects from the API
(Shape suggestions — adapt to your backend.)
- **Folder tree** — `GET /folders` → `[{ id, name, path, photoCount, parentId, hasChildren }]`.
- **Photos (grouped + filtered)** — `GET /photos?groupBy=folder|date|camera|location&type=&camera=&minRating=&q=` → `{ total, sections: [{ title, subCount, photos: [{ id, thumbUrl, favorite, isRaw }] }] }`. Needs to support **virtualization** for tens of thousands of rows.
- **Photo metadata** — `GET /photos/:id` → `{ filename, width, height, sizeBytes, format, camera, lens, iso, aperture, shutter, capturedAt, path, favorite, rating }`.
- **Duplicates** — `GET /duplicates?filter=all|exact|similar` → groups; for the compare view: `{ a, b, similarityPct, reason, fields:{ dimensions, sizeBytes, format, capturedAt, sha256, folder } }` per side. Resolve: `POST /duplicates/:id/resolve { keep: 'a'|'b'|'both' }`.
- **Organize** — `POST /organize { folderIds, destination, mode:'keep'|'date'|'camera', tags[], rename:bool, skipDuplicates:bool }` → job id; ideally a dry-run/preview endpoint returning `{ movedCount, dupSkipped, estBytes, examplePaths[] }`.
- **Destination tree** — `GET /destinations` → same node shape as folders; `POST /destinations/mkdir`.
- **Scan** — `POST /scan { sources[], includeSubfolders }` → stream/poll progress `{ found, folders, dupes, currentPath, done }`.

---

## Design Tokens

**Type.** Primary: `'Helvetica Neue', Helvetica, system-ui, Arial, sans-serif`. Mono (counts, paths, filenames, stats): `ui-monospace, 'SF Mono', Menlo, monospace`. Base body `13px`. Scale: display 34/28, title 22/19/16, body 13–14, label 10.5–11 (uppercase, letter-spacing .05–.08em), mono counts 11–12. Weights 400/500/600/700. Headings letter-spacing ≈ `-0.02em`.

**Radii.** tile 4px · thumb 6px · chips/pills 6–8px · inputs/buttons 8–11px · cards 12–16px · avatar/circle 50%.

**Spacing.** common gaps 8 / 9 / 12 / 16 / 18px; card padding 14–20px; screen padding 26–44px.

**Shadows.** cards `0 1px 3px rgba(0,0,0,.05)`; hovered tile `0 5px 14px rgba(0,0,0,.28)`; modal `0 24px 70px rgba(0,0,0,.4)`; lightbox image `0 24px 70px rgba(0,0,0,.55)`.

**Color — Light**
| token | value |
|---|---|
| app-bg | `#fbfbfc` (Home/States `#f4f4f6`) |
| grid-bg | `#f2f2f4` |
| bar / card | `#ffffff` |
| sidebar | `#f6f6f8` |
| border / divider | `#e6e6e9` / `#ececee` |
| chip | `#f1f1f3` · hover `#ececef` |
| fg / sub / muted | `#26262b` / `#83838a` / `#a0a0a6` |
| accent | `oklch(0.6 0.09 250)` (≈`#4f6f9c`) · text-on-accent `#fff` |
| success (keep) | `oklch(0.56 0.11 150)` |
| danger | `oklch(0.55 0.16 25)` |
| selected chip | bg `oklch(0.94 0.03 250)` / fg `oklch(0.42 0.09 250)` / border `oklch(0.78 0.07 250)` |
| checkbox border | `#cfcfd4` · folder marker `oklch(0.78 0.05 90)` |
| skeleton | base `#e7e7ea` / highlight `#f2f2f4` |
| favorite star | `#ffd24a` |

**Color — Dark**
| token | value |
|---|---|
| app-bg | `#141416` (Home/States `#0f0f11`) · grid-bg `#111113` |
| bar | `#1c1c1f` · card `#202024`/`#222226` · sidebar `#1a1a1d` |
| border / divider | `#29292e` |
| chip | `#26262a` · hover `#26262b` |
| fg / sub / muted | `#e7e7ea` / `#8a8a92` / `#77777f` |
| accent | `oklch(0.68 0.1 250)` · text-on-accent `#0e0e12` |
| success (keep) | `oklch(0.62 0.12 150)` |
| danger | `oklch(0.62 0.16 25)` |
| selected chip | bg `oklch(0.32 0.06 250)` / fg `oklch(0.86 0.06 250)` |
| checkbox border | `#3d3d44` · folder marker `oklch(0.62 0.05 90)` |
| skeleton | base `#242428` / highlight `#2e2e34` |

Segmented active bg — light `#fff` / dark `#3a3a41`. Group/seg track — light `#ececed` / dark `#26262a`.

## Assets
None to ship. Placeholders in the prototype that need real assets:
- **Thumbnails/previews:** muted gradient tiles → real image URLs (`<img>`), same tile geometry.
- **Icons:** currently Unicode glyphs (▸ ▾ ✓ ★ × ⌕ etc.). Swap for your icon set (Lucide/Phosphor/etc.), keeping sizes.
- **Avatar:** "JD" initials circle → real user avatar.

## Files
In `screens/`:
- `Home.dc.html` — dashboard
- `Library.dc.html` — folder tree + grid + filters + lightbox (the core screen)
- `Duplicate Compare.dc.html` — side-by-side duplicate resolver
- `Organize.dc.html` — move/tag/rename flow + destination picker modal
- `Scan.dc.html` — first-run / scanning
- `Library States.dc.html` — loading / empty / no-results / error reference
- `support.js` — prototype runtime (reference only; **not** for the real app)

Open any `.dc.html` in a browser to interact with it. Read the `<script data-dc-script>` block at the bottom of each for the exact state and behavior.

## Screenshots (`screenshots/`)
For screens with both themes, `01-*` is **light**, `02-*` is **dark**.
- `01-1-home.png` / `02-1-home.png` — Home
- `01-2-library.png` / `02-2-library.png` — Library
- `2b-library-lightbox.png` — Library full-screen viewer (lightbox)
- `01-3-duplicates.png` / `02-3-duplicates.png` — Duplicate Compare
- `01-4-organize.png` / `02-4-organize.png` — Organize
- `4b-organize-picker.png` — Organize destination-picker modal
- `01-5-scan-setup.png` / `02-5-scan-setup.png` — Scan, setup phase
- `02-5b-scan-progress.png` — Scan, scanning phase
- `01-6-states.png` / `02-6-states.png` / `03-6-states.png` / `04-6-states.png` — Library states: loading, empty, no-results, error
