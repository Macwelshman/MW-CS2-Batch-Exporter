# Blender compatibility checks

On macOS, run the full suite through Flue:

```sh
python3 tests/run_flue.py
```

Pass `--blender /path/to/Blender` for another Blender 4.2+ installation.
The runner starts a fresh window with a temporary profile, connects only to
its private Flue bridge, and closes that process when done. It prints the log
directory and the suite success marker. The open Blender session is untouched. The installed Flue adapter limits the
suite request to 30 seconds.

Coverage comes from `test_blender.py`: registration, the fixed FBX preset,
preflight, selected-object and collection exports, selection restoration,
overwrite protection, and report UI through `FakeLayout`. A passing run does
not validate the native UI or CS2 Editor import. Validate a representative FBX
in the current CS2 Editor separately.

The September/October weekly reviews recommend repeatable compatibility tests.
Their Geometry Nodes, material/image export, and procedural regeneration
recommendations do not apply to this add-on's implementation. Avoid changing
the fixed FBX preset merely to accommodate a new Blender release.

`cs2_mesh_names.json` is a versioned, language-neutral fixture for the exporter
and CS2 Settings Generator. Each case gives an input FBX basename, whether the
name has a supported mesh classification, its case-preserved parent asset, LOD (0 for the main tier),
shader (null for a regular mesh), and canonical FBX basename. For rejected
inputs, classification fields are null and `canonical` is a suggested rename
when one can be inferred. Settings Generator can feed the canonical stems of
valid cases into its current classifier and compare the parent and mesh role.
The invalid cases describe exporter preflight; the existing downstream
classifier does not reject malformed names.


## Reference asset

Open [Reference Corner.blend](fixtures/Reference%20Corner.blend) or rebuild it
from `reference_scene.py` with Flue:

```sh
python3 tests/run_flue.py --save-reference /path/to/new/ReferenceCorner.blend
```

The suite generates the same scene from source and uses the actual collection
export operator and fixed preset. It checks all eight filenames and their
common asset folder, then imports each file separately and checks the single
mesh name, vertex and triangle counts, world-space dimensions and coordinates
(within 0.0001 m), triangle winding, active per-corner UVs (within 0.00001),
material slots, and face assignments. It also checks summary counts,
selection restoration, overwrite protection, staged verification failure, and
publication rollback.

To additionally verify the actual Settings Generator scan, build its
`cs2-settings-cli` package from the current checkout and pass the resulting
`cs2-settings` binary to the runner:

```sh
python3 tests/run_flue.py --settings-scanner /path/to/cs2-settings
```

That scan checks one asset with eight expected roles, exact FBX mesh names,
material names, and no mesh grouping or parsing issues. Without the flag, the
Blender suite still checks the fixture's expected file and mesh layout.
### Automated Blender results — 10 November 2026

Runs used official Apple silicon builds on macOS, a disposable Blender process
with a private Flue 1.0.31 bridge, and Settings Generator CLI 0.1.6 (source
revision `7e65350`).

| Blender | Reference asset and Settings Generator | Broader Blender suite |
| --- | --- | --- |
| 5.2.3 LTS | Pass: all eight FBXs round-tripped; scanner accepted one asset with all eight roles. | Pass: `MW_CS2_BATCH_EXPORTER_TEST_OK` and `MW_CS2_SETTINGS_REFERENCE_SCAN_OK`. |
| 4.2.0 (declared minimum) | Pass with Edge smoothing. All eight FBXs round-tripped and the scanner recognized all eight roles. | Pass with compatible report icons. Both success markers were present. |
| 5.3.0 Release Candidate | Pass in the earlier reference validation. | Pass in the earlier Flue run, including the scanner. |

Use `--reference-only` with `--blender` and `--settings-scanner` to reproduce
the reference checks independently of the broader suite. Blender 5.2.3 LTS used the full Smoothing Groups preset. Blender 4.2.0 used
Edge smoothing and fell back to built-in report icons when the newer status
icons were unavailable. The saved
fixture was generated with Blender 5.3; the tests generate the scene from
Python on the version under test.

Textures are intentionally absent from this fixture. Use the
[native CS2 import checklist](../docs/CS2_IMPORT_ACCEPTANCE.md) to test shader,
LOD and texture behavior in the current game editor.
