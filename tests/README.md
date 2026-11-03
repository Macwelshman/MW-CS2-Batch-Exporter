# Blender compatibility checks

On macOS, run the full suite on Blender 5.2.3 LTS through Flue:

```sh
python3 tests/run_flue.py
```

Pass `--blender /path/to/Blender` for a different installation of 5.2.3 LTS.
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
