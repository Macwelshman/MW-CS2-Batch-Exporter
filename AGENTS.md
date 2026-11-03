# MW CS2 Batch Exporter — Agent Instructions

## Project purpose

Blender add-on for exporting Cities: Skylines II (CS2) mesh sets. Every selected
mesh (or every mesh in chosen collections) is exported as an individual
`<ObjectName>.fbx`, grouped into asset folders derived from object-name suffixes.
It uses Blender's built-in FBX exporter with one fixed preset. It checks and
reports scene issues; it never edits source data.

Author: Macwelshman. License: GPL-3.0-or-later.

## Basic architecture

- `mw_cs2_batch_exporter/__init__.py` — the entire add-on in one module (~1200 lines):
  - `bl_info` metadata plus `blender_manifest.toml` (Blender Extensions platform)
  - `FBX_EXPORT_SETTINGS` — fixed FBX preset dict applied to every export; keep in
    sync with the README "FBX export settings" section and the tests
  - Preflight checks producing `Issue(severity, object_name, message, detail)`
    entries; errors block export, warnings only with Stop on Warnings
  - Operators: Check Export Source, Export FBX Files, collection list add/remove,
    clear selection/report
  - N-panel (Sidebar > MW CS2 Export): destination, options, source selection,
    collapsible report with generated status icons and clickable material issues
- `tests/test_blender.py` — script-style test (no pytest/unittest); imports `bpy`
  and the addon, registers it, asserts, and prints `MW_CS2_BATCH_EXPORTER_TEST_OK`
  on success. Must run inside Blender's Python via Flue. UI is
  exercised through a `FakeLayout` fake.
- `dist/` — release ZIPs; build artifacts, not tracked in git

## Blender compatibility

- Minimum: Blender 4.2.0 (`blender_manifest.toml` and `bl_info`)
- Documented validated version: Blender 5.2 LTS
- Uses `bpy.ops.export_scene.fbx` and standard `bpy` API only; no external
  dependencies

## Important implementation constraints

- Never modify source scene data: no changes to transforms, parenting, collection
  membership, modifiers, materials, UVs, names, or geometry; restore selection and
  active object after export
- The fixed FBX preset (`FBX_EXPORT_SETTINGS`) is intentional — do not alter
  exporter settings without an explicit request; README and tests document it
- Asset folders come from object names, independent of collection names. Use
  `<Asset>[<LOD>][<Shader>].fbx`, with at most one LOD (`_LOD1`, `_LOD2`)
  before at most one shader (`_Win`, `_Wif`, `_Wio`, `_Wim`, `_Gls`,
  `_Gra`, `_Wat`). Preserve the asset name and match suffixes
  case-insensitively, writing them in the canonical casing shown here.
- Preflight blocks reversed, repeated, or conflicting suffixes and unsupported
  LOD numbers. Show the current filename and suggest a canonical rename when
  the intended role is clear. Block export when suffix casing differs so the user can
  make the Blender mesh name match the exported filename.
- Filename rules: portable characters only, Windows reserved names rejected,
  case-insensitive conflict detection, overwrite protection unless
  Overwrite Existing is enabled
- Preflight always runs again at export time; the Export button stays disabled
  until the Export Folder path is usable
- Scene must be Metric with Unit Scale 1.0 — checked and reported, not repaired
- Wif/Wio submeshes follow the Win rule: zero material slots expected, UV checks
  still apply

## Running Blender

- Always use Flue to launch or operate Blender, including for automated tests,
  background runs, and runtime inspection. Read
  `/Users/ian/.codex/skills/flue/SKILL.md` and its Blender adapter instructions
  first.
- Do not run Blender directly, use Blender MCP, or invoke test runners that
  launch Blender directly. The sole exception is `tests/run_flue.py`, which
  may start a fresh Blender process with factory settings and a private Flue
  bootstrap. It must execute the suite through that private bridge. If Flue
  is unavailable, report that Blender validation is blocked.

## Validation

- Run `tests/test_blender.py` inside Blender's Python via Flue and check
  for `MW_CS2_BATCH_EXPORTER_TEST_OK`
- Never claim tests passed unless they were actually run
- Final FBX dialect correctness is validated in the current CS2 Editor (see README)

## Rules

- Read relevant documentation (README, USER_GUIDE, PROJECT_STATUS) and the
  relevant source before editing.
- Prefer small, targeted changes.
- Preserve unrelated behaviour.
- Do not change versions, metadata, packaging, or git history unless explicitly
  requested.
- In DEBUG mode, establish the cause before editing.
- Never claim tests passed unless actually run.
- Report files changed, tests actually run, and remaining uncertainties.
- `docs/AI_WORKFLOW.md` defines the operating modes.
