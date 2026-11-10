# Native Cities: Skylines II import acceptance

Use [Reference Corner.blend](../tests/fixtures/Reference%20Corner.blend) in a
disposable project. Record the CS2 Editor build, Blender build, exporter
revision, Settings Generator build, test date, and screenshots of the front
and each LOD. Mark each item Pass, Fail, or Not tested.

## Prepare

- [ ] Export the **Reference Corner Source** collection into an empty folder
  with the normal exporter preset. Check the summary reports eight exported
  and eight verified, with no skipped or failed files.
- [ ] Confirm one `Reference Corner` folder holds eight matching FBX
  files: the base building, `_LOD1`, `_LOD2`, `_Win`, `_Wif`, `_Wio`,
  `_LOD1_Win`, and `_LOD2_Win`. Main and LOD1 share `ReferenceMasonry`;
  the other meshes have no material slots.
- [ ] Supply external CS2 texture maps with conspicuous orientation marks for
  the main/LOD1 texture set and a distinguishable LOD2 texture set. The
  fixture contains UVs and a named material but does not ship texture maps.
  Scan the folder in Settings Generator and generate the settings JSON with
  the intended texture sets. Record filenames and settings alongside the test.

## In the current CS2 Editor

- [ ] Import as a building. Confirm it is upright, on the ground plane, and
  at the expected scale. The main footprint spans 8 × 5 m, the off-center
  roof peak is 8 m high, and the three window panels sit on the straight
  facade (negative Y in Blender). Inspect the angled rear wall and roof
  from both sides to catch mirroring, axis swaps, and reversed faces.
- [ ] Inspect the regular, frosted, and opaque window submeshes up close.
  Check they attach to the right facade, face outward, render with their
  intended window behavior, and do not float, disappear, or flicker.
  Verify the regular window remains aligned on LOD1 and LOD2.
- [ ] Preview or force each LOD; also move the camera through both transitions.
  Confirm the building stays in place and reduces detail: LOD1 retains the
  peak, and LOD2 replaces it with a flat roof. Check for missing faces or
  windows and unexpected scale, position, or orientation changes.
- [ ] Check texture references in the generated settings and on the imported
  asset. Verify main/LOD1 share the intended textures and LOD2 uses its own
  set. Check orientation marks, UV placement, and the intended normal and
  packed map channels. Save and reopen the asset to check that references
  still resolve without missing-texture fallbacks.
- [ ] Log any failure with the FBX filename, Blender source object, expected
  behavior, actual behavior, and editor build. Keep the generated settings and
  export folder with the evidence.

Blender reimport checks geometry, winding, UVs and materials. Settings
Generator scanning checks the mesh roles and file relationships. Neither
check establishes how the native editor interprets the FBX, renders window
shaders, switches LODs, or resolves texture references. Native acceptance is
pending until this checklist is executed.
