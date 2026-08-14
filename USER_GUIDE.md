# MW CS2 Batch Exporter — User Guide

MW CS2 Batch Exporter is a Blender add-on for exporting Cities: Skylines II mesh sets. It exports every mesh in the chosen source as a separate FBX file, preserves each Blender object name as the filename, and groups related objects into an asset folder.

This guide covers version **0.1.24**.

## Contents

- [Requirements](#requirements)
- [Install the add-on](#install-the-add-on)
- [Prepare a scene](#prepare-a-scene)
- [Understand names and output folders](#understand-names-and-output-folders)
- [Export selected objects](#export-selected-objects)
- [Export collections](#export-collections)
- [Panel controls](#panel-controls)
- [Read the preflight report](#read-the-preflight-report)
- [Resolve errors](#resolve-errors)
- [Review warnings](#review-warnings)
- [FBX export settings](#fbx-export-settings)
- [File and scene safety](#file-and-scene-safety)
- [Troubleshooting](#troubleshooting)

## Requirements

- Blender **4.2 or later**
- Blender **5.2 LTS** is the currently validated version
- A scene prepared for the Cities: Skylines II scale and naming workflow

The add-on uses Blender's built-in FBX exporter. No separate exporter or external dependency is required.

## Install the add-on

For automatic updates, add this repository under **Edit > Preferences > Get Extensions > Repositories**:

`https://raw.githubusercontent.com/Macwelshman/MW-Blender-Extensions/main/index.json`

Sync it, search for **MW CS2 Batch Exporter**, and click **Install**. Future
published versions are then available through **Check for Updates**. If the
add-on was previously installed from disk, remove that copy once and reinstall
it from the MW repository.

For a manual installation:

1. Download `mw_cs2_batch_exporter-0.1.24.zip` from the repository's latest release or `dist` folder.
2. In Blender, open **Edit > Preferences**.
3. Open **Add-ons**, or **Get Extensions** on Blender versions that use the Extensions interface.
4. Choose **Install from Disk** and select the ZIP file. Do not extract it first.
5. Enable **MW CS2 Batch Exporter** if Blender does not enable it automatically.
6. Return to the 3D Viewport and press **N** to open the sidebar.
7. Select the **MW CS2 Export** tab.

Manual installations must be replaced with a newer release ZIP. Repository
installations use Blender's normal update controls.

## Prepare a scene

Before checking or exporting:

1. Open **Scene Properties > Units**.
2. Set **Unit System** to **Metric**.
3. Set **Unit Scale** to **1.0**. One Blender unit then represents one metre.
4. Give every export mesh its final, portable object name.
5. Apply object rotation and scale with **Object > Apply > Rotation & Scale**. The resulting rotation must be `0, 0, 0` and scale must be `1, 1, 1`.
6. Confirm that every mesh contains faces.
7. Add and activate the intended UV map.
8. Review material slots for the object's CS2 role.

The add-on checks the scene but does not repair it. It does not apply transforms, move origins, rename objects, edit geometry, change materials, or modify UV maps.

## Understand names and output folders

Each mesh is written as `<ObjectName>.fbx`. Related CS2 suffixes are removed from the end of the name to determine the shared asset folder.

For example, exporting these objects:

```text
Station
Station_LOD1
Station_LOD2
Station_Win
```

creates:

```text
<Export Folder>/
└── Station/
    ├── Station.fbx
    ├── Station_LOD1.fbx
    ├── Station_LOD2.fbx
    └── Station_Win.fbx
```

The recognised grouping suffixes are:

- `_LOD<number>`
- `_Win`
- `_Wim`
- `_Gls`
- `_Gra`
- `_Wat`

Suffix matching is case-insensitive and repeated suffixes are removed from the end. For example, `Station_Win_LOD1` is grouped in the `Station` folder while keeping the filename `Station_Win_LOD1.fbx`.

Collection names do not determine output folders. Folder grouping always comes from each object's name. Existing matching asset folders are reused.

## Export selected objects

Use this mode for an explicit selection in the active view layer.

1. Switch to **Object Mode**.
2. Select the mesh objects to export. Cameras, lights, empties, and other non-mesh objects are ignored.
3. In **MW CS2 Export**, choose an **Export Folder**.
4. Under **Export Source**, select **Selected Objects**.
5. Set the required [options](#panel-controls).
6. Click **Check Export Source**.
7. Resolve all errors and review any warnings.
8. Click **Export FBX Files**.

The original selection and active object are restored after the export attempt.

## Export collections

Collection mode can use one collection or a list of collections. Meshes in child collections are included recursively.

### One collection

1. Under **Export Source**, select **Collections**.
2. Choose a collection in the collection picker.
3. Leave the collection list empty.
4. Click **Check Export Source**, then **Export FBX Files** when ready.

With an empty list, the picker acts as a quick single-collection source.

### Multiple collections

1. Choose the first collection in the picker and click **Add**.
2. Repeat for each additional collection.
3. To remove one, highlight it in the list and click **Remove**.
4. Click **Check Export Source**, then **Export FBX Files** when ready.

When the list contains entries, the list becomes the source and the current picker value is not added until **Add** is clicked. An object belonging to more than one chosen collection is exported only once. Non-mesh objects are ignored.

Objects must be available in the active view layer. A mesh found in a chosen collection but excluded from that view layer is reported as an error.

## Panel controls

| Section | Control | Purpose |
|---|---|---|
| Destination | **Export Folder** | Chooses the parent folder in which asset folders will be created or reused. |
| Options | **Overwrite Existing** | Allows same-named FBX files to be replaced. Off by default. |
| Options | **Stop on Warnings** | Treats remaining warnings as export blockers. |
| Options | **Ignore N-gons** | Omits intentional n-gons from the report. **Triangulate Faces** remains disabled. |
| Export Source | **Selected Objects** | Uses selected meshes in the active view layer. |
| Export Source | **Collections** | Uses the quick collection picker or the visible collection list. |
| Export Source | **Check Export Source** | Runs preflight without exporting or changing the scene. |
| Export Source | **Export FBX Files** | Runs preflight again, then exports when no blocking issue remains. |
| — | **Clear Export Selection** | Deselects scene objects and clears collection choices. It preserves the destination, options, report, and exported files. |
| Report | disclosure arrow | Expands or collapses the report without clearing it. |
| Report | **Clear Report** | Removes only the generated report and preserves all exporter choices. |

The **Export FBX Files** button is disabled until **Export Folder** contains a usable path. Destination validity is intentionally separate from the source preflight report.

## Read the preflight report

The report contains a **General** section for scene or source problems and a separate header for every checked mesh.

- **Error** — export is blocked.
- **Warning** — export is allowed unless **Stop on Warnings** is enabled.
- **Ready** — no issue was found for that mesh.

The collapsed report shows a summary such as `4 objects checked · 0 errors · 1 warning`. Expand it to see the affected objects and individual issues.

Hover over an issue's information icon for its explanation. A material warning is a clickable **Material** button: clicking it selects the affected object and, when a Properties editor is open, switches that editor to **Material Properties**.

Checking is optional because **Export FBX Files** always runs the same preflight again. Checking first is recommended because it lets you correct the entire source before any files are written.

## Resolve errors

Errors always stop export.

| Error | Cause | Resolution |
|---|---|---|
| **No mesh objects** | The selected-object source contains no selected meshes, or a collection source contains no meshes. | Select at least one mesh or choose a collection containing meshes. |
| **No collection** | Collection mode has neither a collection-list entry nor a quick collection choice. | Choose a collection, or add one or more collections to the list. |
| **Metric units required** | The scene is not Metric with Unit Scale 1.0. | Set **Scene Properties > Units > Metric**, **Unit Scale 1.0**. |
| **Invalid filename** | An object name is empty, reserved on Windows, ends in a space or dot, or contains a non-portable character. | Rename the object using a portable filename. Avoid `< > : " / \\ | ? *` and Windows device names such as `CON`, `NUL`, `COM1`, or `LPT1`. |
| **Filename conflict** | Two names become the same filename on a case-insensitive filesystem. | Rename one object so the names differ by more than letter case. |
| **Existing FBX** | The destination file already exists and overwrite protection is active. | Choose another folder, rename the object, remove the old file manually, or deliberately enable **Overwrite Existing**. |
| **Scale not applied** | Object scale is not `1, 1, 1`. | Apply scale in Object Mode. |
| **Negative scale** | One or more scale axes are negative. | Correct the mirrored transform and apply scale; then verify normals. |
| **Rotation not applied** | Object rotation is not `0, 0, 0`. | Apply rotation in Object Mode. |
| **Empty mesh** | The mesh has no vertices or no polygon faces. | Add exportable geometry or remove the object from the source. |
| **Unavailable object** | A chosen collection contains a mesh excluded from the active view layer. | Include it in the active view layer or remove that collection/object from the source. |

An invalid or missing **Export Folder** disables the export button rather than adding an error to the report. If export is invoked by another method, it is cancelled without replacing the existing report.

## Review warnings

Warnings allow export by default. Enable **Stop on Warnings** when every warning must be resolved.

| Warning | Meaning |
|---|---|
| **No UV map** | The mesh has no UV layer. Add one before texturing or CS2 import. |
| **No active UV map** | UV layers exist, but none is active for export. Activate the intended layer. |
| **Empty material slots** | A main or LOD1 mesh has an unassigned material slot. Remove or fill empty slots. |
| **No material** | A main or LOD1 mesh has no material. These meshes normally use one material. |
| **Multiple materials** | A main or LOD1 mesh has more than one assigned material. Confirm that this matches the intended CS2 material layout. |
| **LOD2 has materials** | A name containing `_LOD2` has material slots. LOD2 meshes should normally have zero material slots. |
| **Submesh has materials** | A `_Win`, `_Wim`, `_Gls`, `_Gra`, or `_Wat` mesh has material slots. These special meshes should normally have zero slots. |
| **N-gons used** | The mesh contains faces with more than four vertices, which may be triangulated differently by downstream tools or CS2 import. |

Material names do not need to match object names. Main and LOD1 meshes can share one material and texture set. The add-on checks slot layout, not a required material-name pattern.

Use **Ignore N-gons** only after deciding the faces are intentional. The option hides the warning; it does not alter the mesh. **Triangulate Faces** remains disabled in the FBX preset.

## FBX export settings

The add-on applies one fixed preset to every mesh:

- path mode **Auto**; batch mode **Off**
- **Selected Objects** enabled; other source-limit toggles disabled
- all object-type filters enabled (the add-on selects one mesh for each individual export)
- custom properties disabled
- scale `1.0`; **Apply Scalings: All Local**
- forward axis `-Z`; up axis `Y`
- **Apply Unit**, **Use Space Transform**, and **Apply Transform** enabled
- **Smoothing Groups** with evaluated modifiers enabled
- subdivision surfaces, loose edges, triangulate faces, and tangent space disabled
- vertex colours exported as **sRGB** without prioritising the active colour
- primary bone axis `Y`; secondary bone axis `X`; armature FBX node type **Null**
- only-deform-bones disabled; add-leaf-bones enabled
- animation, key-all-bones, NLA strips, all actions, and force-start/end-keying enabled
- sampling rate `1.0`; simplify `1.0`
- textures not embedded

Blender controls the FBX dialect written by its built-in exporter. Validate a representative export in the current Cities: Skylines II Editor before relying on the workflow for a full asset batch.

## File and scene safety

The add-on is designed to leave Blender source data unchanged:

- source meshes, materials, transforms, origins, UVs, and names are not edited
- evaluated modifiers and transform conversion affect exported FBX data only
- selected-object mode restores the original selection and active object after export
- collection mode does not require the objects to remain selected
- existing FBX files are protected unless **Overwrite Existing** is enabled
- clearing the export selection or report never deletes exported files

The add-on creates the chosen destination and required asset subfolders when necessary. If an unexpected FBX exporter error occurs partway through a batch, files already completed remain in the destination and the report states how many were exported before the failure. Review those files before retrying, especially before enabling overwrite.

## Troubleshooting

### Export FBX Files is disabled

Choose an **Export Folder**. The field must be empty only while checking; export requires a path that either does not yet exist or already exists as a folder. A path that points to a file is invalid.

### Check Export Source reports zero meshes

- Switch to **Object Mode**.
- In **Selected Objects** mode, select mesh objects in the active view layer.
- In **Collections** mode, choose a quick collection or add collections to the list.
- Remember that cameras, lights, empties, and other helper objects are ignored.

### The wrong collection is exported

If the collection list contains entries, that list is the source. Selecting a different collection in the picker does not change the list until you click **Add**. Remove unwanted list entries, or remove every entry to return to quick single-collection behavior.

### Export stops even though the report contains only warnings

Disable **Stop on Warnings**, or resolve the warnings before exporting.

### An existing file blocks export

This is overwrite protection. Confirm the destination and object name, then either keep the existing file, move it elsewhere, or explicitly enable **Overwrite Existing**.

### Material warning does not open Material Properties

The object is still selected, but Blender can switch only an existing Properties editor. Change any area to **Properties**, then click the material warning again.

### A warning disappeared after enabling Ignore N-gons

This is expected for **N-gons used** only. The mesh is unchanged and **Triangulate Faces** remains disabled during export.

### Exported files are in an unexpected folder

Asset folders are derived from object names, not collection names. Review the recognised suffixes under [Understand names and output folders](#understand-names-and-output-folders).

### Blender appears to use an older add-on version

Check the installed version in Blender Preferences. Remove the older installation, restart Blender, install the current ZIP, and verify the version again before exporting.

## Quick checklist

Before a final batch export, confirm:

- [ ] Blender is in Object Mode.
- [ ] Scene units are Metric with Unit Scale 1.0.
- [ ] Object names and CS2 suffixes are final.
- [ ] Rotation and scale are applied.
- [ ] Every mesh contains faces and has the intended UV map.
- [ ] Main and LOD1 material slots are intentional.
- [ ] LOD2 and special submeshes have no material slots.
- [ ] The correct selected objects or collections are shown as the source.
- [ ] The export folder is correct.
- [ ] Overwrite and warning options are set deliberately.
- [ ] **Check Export Source** shows no errors.
- [ ] A representative FBX has been validated in the current CS2 Editor.
