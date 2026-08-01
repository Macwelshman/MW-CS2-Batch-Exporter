"""MW CS2 Batch Exporter.

Exports each selected mesh as a separate FBX without modifying source objects.
"""

from __future__ import annotations

import math
import os
import re
from collections import namedtuple
from pathlib import Path

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup


bl_info = {
    "name": "MW CS2 Batch Exporter",
    "author": "MW",
    "version": (0, 1, 1),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Sidebar > MW CS2 Export",
    "description": "Export selected meshes as individual CS2-ready FBX files",
    "category": "Import-Export",
}


Issue = namedtuple("Issue", "severity object_name message")
EPSILON = 1.0e-5
INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
NO_MATERIAL_SUFFIXES = ("_win", "_wim", "_gls", "_gra", "_wat")
GROUP_SUFFIX = re.compile(r"_(?:LOD\d+|Win|Wim|Gls|Gra|Wat)$", re.IGNORECASE)


def _is_close_sequence(values, expected):
    return all(abs(a - b) <= EPSILON for a, b in zip(values, expected))


def _portable_filename_error(name):
    if not name or name in {".", ".."}:
        return "Object name cannot be used as a filename."
    if INVALID_FILENAME.search(name):
        return "Object name contains a character that is invalid in a portable filename."
    if name.endswith((" ", ".")):
        return "Object name ends in a space or dot, which is not portable to Windows."
    if name.split(".", 1)[0].upper() in WINDOWS_RESERVED:
        return "Object name is a reserved Windows filename."
    return None


def _is_special_submesh(name):
    lower = name.casefold()
    # Allow a LOD suffix after the material suffix, e.g. Asset_Win_LOD1.
    return any(lower.endswith(suffix) or re.search(re.escape(suffix) + r"_lod\d+$", lower)
               for suffix in NO_MATERIAL_SUFFIXES)


def main_asset_name(name):
    """Return the shared CS2 asset name after removing variant suffixes."""
    base = name
    while True:
        stripped = GROUP_SUFFIX.sub("", base)
        if stripped == base or not stripped:
            return base
        base = stripped


def export_path(directory, object_name):
    return Path(directory) / main_asset_name(object_name) / f"{object_name}.fbx"


def collect_issues(context, objects, export_directory, check_existing=True):
    issues = []

    if not objects:
        return [Issue("ERROR", "Selection", "Select at least one mesh object.")]

    scene = context.scene
    unit = scene.unit_settings
    if unit.system != "METRIC" or abs(unit.scale_length - 1.0) > EPSILON:
        issues.append(Issue(
            "ERROR", "Scene",
            "Use Metric units with Unit Scale 1.0 (CS2 uses 1 Blender unit = 1 metre).",
        ))

    directory = Path(bpy.path.abspath(export_directory)) if export_directory else None
    if directory is None:
        issues.append(Issue("ERROR", "Export", "Choose an export folder."))
    elif directory.exists() and not directory.is_dir():
        issues.append(Issue("ERROR", "Export", "The export path is not a folder."))

    seen_names = {}
    for obj in objects:
        name = obj.name
        filename_error = _portable_filename_error(name)
        if filename_error:
            issues.append(Issue("ERROR", name, filename_error))

        portable_key = f"{name}.fbx".casefold()
        if portable_key in seen_names:
            issues.append(Issue(
                "ERROR", name,
                f"Filename conflicts with '{seen_names[portable_key]}' on a case-insensitive filesystem.",
            ))
        else:
            seen_names[portable_key] = name

        if directory and directory.is_dir() and check_existing:
            destination = export_path(directory, name)
            if destination.exists():
                issues.append(Issue("ERROR", name, "Destination FBX already exists (overwrite is disabled)."))

        if not _is_close_sequence(obj.scale, (1.0, 1.0, 1.0)):
            issues.append(Issue("ERROR", name, "Scale is not applied; expected (1, 1, 1)."))
        if any(value < 0.0 for value in obj.scale):
            issues.append(Issue("ERROR", name, "Negative scale can invert handedness and normals."))
        if not _is_close_sequence(obj.rotation_euler, (0.0, 0.0, 0.0)):
            degrees = tuple(round(math.degrees(value), 3) for value in obj.rotation_euler)
            issues.append(Issue("ERROR", name, f"Rotation is not applied; current Euler rotation is {degrees} degrees."))
        if not _is_close_sequence(obj.location, (0.0, 0.0, 0.0)):
            issues.append(Issue("WARNING", name, "Object location is not at the world origin."))

        mesh = obj.data
        if not mesh.vertices or not mesh.polygons:
            issues.append(Issue("ERROR", name, "Mesh has no exportable faces."))
        if not mesh.uv_layers:
            issues.append(Issue("WARNING", name, "Mesh has no UV map."))
        elif mesh.uv_layers.active is None:
            issues.append(Issue("WARNING", name, "Mesh has no active UV map."))

        material_slots = list(obj.material_slots)
        assigned_materials = [slot.material for slot in material_slots if slot.material]
        if len(assigned_materials) != len(material_slots):
            issues.append(Issue("WARNING", name, "One or more material slots are empty."))

        if _is_special_submesh(name):
            if assigned_materials:
                issues.append(Issue("WARNING", name, "Known CS2 special submeshes normally contain no material."))
        elif not assigned_materials:
            issues.append(Issue("WARNING", name, "Main/LOD meshes normally use one material."))
        elif len(assigned_materials) > 1:
            issues.append(Issue("WARNING", name, "Main/LOD meshes normally use one material."))
        elif assigned_materials[0].name.casefold() not in {name.casefold(), f"{name}_mtl".casefold()}:
            issues.append(Issue(
                "WARNING", name,
                f"Material '{assigned_materials[0].name}' does not match the object name or '{name}_Mtl'.",
            ))

        if any(len(poly.vertices) > 4 for poly in mesh.polygons):
            issues.append(Issue("WARNING", name, "Mesh contains n-gons; triangulation may differ on import."))

    return issues


def selected_meshes(context):
    return sorted((obj for obj in context.selected_objects if obj.type == "MESH"), key=lambda obj: obj.name.casefold())


def _store_report(scene, issues, heading):
    lines = [heading]
    if not issues:
        lines.append("PASS: No preflight issues found.")
    else:
        for issue in issues:
            lines.append(f"{issue.severity}: {issue.object_name} — {issue.message}")
    scene.cs2_batch_export_report = "\n".join(lines)


class CS2BatchExportSettings(PropertyGroup):
    export_directory: StringProperty(
        name="Export Folder",
        description="Folder for individual FBX files",
        subtype="DIR_PATH",
    )
    stop_on_warnings: BoolProperty(
        name="Stop on Warnings",
        description="Do not export while any preflight warning remains",
        default=False,
    )
    overwrite_existing: BoolProperty(
        name="Overwrite Existing",
        description="Allow an existing same-named FBX to be replaced",
        default=False,
    )


class CS2BATCH_OT_check(Operator):
    bl_idname = "cs2_batch.check_selected"
    bl_label = "Check Selected"
    bl_description = "Run CS2 preflight checks without changing the scene"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def execute(self, context):
        settings = context.scene.cs2_batch_export_settings
        objects = selected_meshes(context)
        issues = collect_issues(
            context, objects, settings.export_directory,
            check_existing=not settings.overwrite_existing,
        )
        unsupported = [obj for obj in context.selected_objects if obj.type != "MESH"]
        issues.extend(Issue("WARNING", obj.name, f"Selected {obj.type} object will not be exported.") for obj in unsupported)
        _store_report(context.scene, issues, f"Checked {len(objects)} mesh object(s).")
        error_count = sum(issue.severity == "ERROR" for issue in issues)
        warning_count = sum(issue.severity == "WARNING" for issue in issues)
        self.report({"ERROR" if error_count else "INFO"}, f"Preflight: {error_count} error(s), {warning_count} warning(s)")
        return {"FINISHED"}


class CS2BATCH_OT_export(Operator):
    bl_idname = "cs2_batch.export_selected"
    bl_label = "Export Selected Objects"
    bl_description = "Export each selected mesh as an individual FBX using its exact object name"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and any(obj.type == "MESH" for obj in context.selected_objects)

    def execute(self, context):
        scene = context.scene
        settings = scene.cs2_batch_export_settings
        objects = selected_meshes(context)
        issues = collect_issues(
            context, objects, settings.export_directory,
            check_existing=not settings.overwrite_existing,
        )
        unsupported = [obj for obj in context.selected_objects if obj.type != "MESH"]
        issues.extend(Issue("WARNING", obj.name, f"Selected {obj.type} object will not be exported.") for obj in unsupported)

        errors = [issue for issue in issues if issue.severity == "ERROR"]
        warnings = [issue for issue in issues if issue.severity == "WARNING"]
        if errors or (settings.stop_on_warnings and warnings):
            _store_report(scene, issues, "Export stopped by preflight.")
            self.report({"ERROR"}, "Export stopped. Review the preflight report.")
            return {"CANCELLED"}

        directory = Path(bpy.path.abspath(settings.export_directory))
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            issues.append(Issue("ERROR", "Export", f"Could not create export folder: {exc}"))
            _store_report(scene, issues, "Export failed.")
            self.report({"ERROR"}, "Could not create the export folder.")
            return {"CANCELLED"}

        original_selection = list(context.selected_objects)
        original_active = context.view_layer.objects.active
        exported = []
        try:
            for obj in objects:
                bpy.ops.object.select_all(action="DESELECT")
                obj.select_set(True)
                context.view_layer.objects.active = obj
                destination = export_path(directory, obj.name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                result = bpy.ops.export_scene.fbx(
                    filepath=os.fspath(destination),
                    check_existing=False,
                    use_selection=True,
                    object_types={"MESH"},
                    global_scale=1.0,
                    apply_unit_scale=True,
                    apply_scale_options="FBX_SCALE_UNITS",
                    axis_forward="-Z",
                    axis_up="Y",
                    use_space_transform=True,
                    bake_space_transform=False,
                    use_mesh_modifiers=True,
                    mesh_smooth_type="OFF",
                    use_tspace=True,
                    use_triangles=True,
                    use_custom_props=False,
                    path_mode="STRIP",
                    embed_textures=False,
                    bake_anim=False,
                    add_leaf_bones=False,
                )
                if result != {"FINISHED"}:
                    raise RuntimeError(f"Blender FBX exporter returned {result!r}")
                exported.append(os.fspath(destination.relative_to(directory)))
        except Exception as exc:  # Blender operators can raise several runtime exception types.
            issues.append(Issue("ERROR", "Export", str(exc)))
            _store_report(scene, issues, f"Export failed after {len(exported)} file(s).")
            self.report({"ERROR"}, f"Export failed after {len(exported)} file(s).")
            return {"CANCELLED"}
        finally:
            bpy.ops.object.select_all(action="DESELECT")
            for obj in original_selection:
                if obj.name in context.view_layer.objects:
                    obj.select_set(True)
            if original_active and original_active.name in context.view_layer.objects:
                context.view_layer.objects.active = original_active

        _store_report(scene, warnings, f"Exported {len(exported)} file(s) to {directory}.")
        self.report({"INFO"}, f"Exported {len(exported)} individual FBX file(s).")
        return {"FINISHED"}


class CS2BATCH_PT_panel(Panel):
    bl_label = "MW CS2 Batch Exporter"
    bl_idname = "CS2BATCH_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MW CS2 Export"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.cs2_batch_export_settings

        layout.prop(settings, "export_directory")
        options = layout.box()
        options.label(text="Export Safety")
        options.prop(settings, "overwrite_existing")
        options.prop(settings, "stop_on_warnings")

        row = layout.row(align=True)
        row.operator("cs2_batch.check_selected", icon="CHECKMARK")
        row.operator("cs2_batch.export_selected", icon="EXPORT")

        info = layout.box()
        info.label(text="CS2 Preset")
        info.label(text="Metric, 1 unit = 1 metre")
        info.label(text="Forward -Z, Up Y, triangulated")
        info.label(text="Blender has no FBX 2018 selector", icon="INFO")

        if scene.cs2_batch_export_report:
            report = layout.box()
            report.label(text="Last Report")
            for line in scene.cs2_batch_export_report.splitlines():
                icon = "ERROR" if line.startswith("ERROR:") else "INFO"
                if line.startswith("WARNING:"):
                    icon = "ERROR"  # Most legible warning icon available across supported versions.
                report.label(text=line, icon=icon)


CLASSES = (
    CS2BatchExportSettings,
    CS2BATCH_OT_check,
    CS2BATCH_OT_export,
    CS2BATCH_PT_panel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.cs2_batch_export_settings = bpy.props.PointerProperty(type=CS2BatchExportSettings)
    bpy.types.Scene.cs2_batch_export_report = StringProperty(options={"SKIP_SAVE"})


def unregister():
    del bpy.types.Scene.cs2_batch_export_report
    del bpy.types.Scene.cs2_batch_export_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
