# MW CS2 Batch Exporter

A small Blender add-on that exports every selected mesh object as an individual FBX file. Each file uses the object's exact name and is grouped into a folder named after the main asset.

For example, selecting `Object`, `Object_LOD1`, `Object_LOD2`, and `Object_Win` produces:

```text
Object/
├── Object.fbx
├── Object_LOD1.fbx
├── Object_LOD2.fbx
└── Object_Win.fbx
```

Existing matching asset folders are reused.

## Install

1. In Blender, open **Edit > Preferences > Add-ons** (or **Extensions > Install from Disk**).
2. Choose the release ZIP from `dist/`.
3. Enable **MW CS2 Batch Exporter** if Blender does not enable it automatically.
4. Open the 3D Viewport sidebar with **N**, then select **MW CS2 Export**.

## Workflow

1. Set the scene to **Metric** with **Unit Scale 1.0**.
2. Select the mesh objects to export in Object Mode.
3. Choose an **Export Folder**.
4. Click **Check Selected** and resolve errors.
5. Click **Export Selected Objects**.

The add-on does not apply transforms, rename objects, alter geometry, or change materials. Selection and active-object state are restored after exporting. Existing files are protected unless **Overwrite Existing** is explicitly enabled.

## CS2 preset

- One selected mesh per FBX, grouped by main asset name
- Exact object-name filenames
- Metric scene preflight: 1 Blender unit = 1 metre
- Forward `-Z`, Up `Y`
- Evaluated modifiers included
- Triangulated on export (source mesh is unchanged)
- Normals and tangent space exported
- Textures are not embedded; paths are stripped
- Animation disabled

The official CS2 Asset Creation Guide asks for FBX 2018. Blender 5.2's built-in FBX exporter does not expose a version selector and writes its own fixed binary FBX dialect. This add-on cannot claim to generate Autodesk FBX 2018 specifically; validate a representative result in the current CS2 Editor. If the Editor rejects Blender's FBX, convert the exported files with an Autodesk-compatible FBX 2018 tool as a separate step.

## Preflight checks

Errors stop export:

- no mesh selection or export folder
- scene is not Metric / Unit Scale 1.0
- non-portable, reserved, or colliding object filenames
- an existing destination when overwrite is disabled
- unapplied scale or rotation, including negative scale
- mesh has no exportable faces

Warnings are reported but export is allowed by default:

- object is away from the world origin
- missing/ inactive UV map
- empty, missing, multiple, or unexpectedly named materials
- a known CS2 special submesh (`_Win`, `_Wim`, `_Gls`, `_Gra`, `_Wat`) has a material
- n-gons that may triangulate differently on import
- selected non-mesh objects, which are skipped

Enable **Stop on Warnings** for a strict workflow.

## Naming and materials

CS2 naming conventions affect importer behavior. Main and LOD meshes normally use one material named like the object/FBX or `<ObjectName>_Mtl`. Known special submeshes normally contain no material. The add-on reports these rules but does not silently repair the scene.

## Compatibility

Developed and validated with Blender 5.2 LTS. The extension manifest supports Blender 4.2 and later.
