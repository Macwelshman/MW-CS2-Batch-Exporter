"""MW CS2 Batch Exporter.

Exports each selected mesh as a separate FBX without modifying source objects.
"""

from __future__ import annotations

import math
import os
import re
import struct
import tempfile
import textwrap
import zlib
from dataclasses import dataclass
from pathlib import Path

import bpy
import bpy.utils.previews
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup, UIList


bl_info = {
    "name": "MW CS2 Batch Exporter",
    "author": "MW",
    "version": (0, 1, 24),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Sidebar > MW CS2 Export",
    "description": "Export selected meshes as individual CS2-ready FBX files",
    "category": "Import-Export",
}


@dataclass(frozen=True)
class Issue:
    severity: str
    object_name: str
    message: str
    detail: str = ""
EPSILON = 1.0e-5
INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
NO_MATERIAL_SUFFIXES = ("_win", "_wim", "_gls", "_gra", "_wat")
GROUP_SUFFIX = re.compile(r"_(?:LOD\d+|Win|Wim|Gls|Gra|Wat)$", re.IGNORECASE)
REPORT_ENTRY_SPACING = 0.15
MATERIAL_ISSUE_MESSAGES = {
    "LOD2 has materials",
    "Submesh has materials",
    "Empty material slots",
    "No material",
    "Multiple materials",
}
STATUS_ICON_SIZE = 32
STATUS_ICON_SCALE = 4
WARNING_ICON_FILE = "mw_cs2_amber_warning.png"
READY_ICON_FILE = "mw_cs2_green_ready.png"
_STATUS_PREVIEWS = None
_WARNING_ICON_ID = 0
_READY_ICON_ID = 0

# Fixed Blender FBX preset used for every individual export. Keep this in sync
# with the documented CS2 export settings and tests.
FBX_EXPORT_SETTINGS = {
    "path_mode": "AUTO",
    "batch_mode": "OFF",
    "use_selection": True,
    "use_visible": False,
    "use_active_collection": False,
    "object_types": {"EMPTY", "CAMERA", "LIGHT", "ARMATURE", "MESH", "OTHER"},
    "use_custom_props": False,
    "global_scale": 1.0,
    "apply_scale_options": "FBX_SCALE_NONE",
    "axis_forward": "-Z",
    "axis_up": "Y",
    "apply_unit_scale": True,
    "use_space_transform": True,
    "bake_space_transform": True,
    "mesh_smooth_type": "SMOOTH_GROUP",
    "use_subsurf": False,
    "use_mesh_modifiers": True,
    "use_mesh_edges": False,
    "use_triangles": False,
    "use_tspace": False,
    "colors_type": "SRGB",
    "prioritize_active_color": False,
    "primary_bone_axis": "Y",
    "secondary_bone_axis": "X",
    "armature_nodetype": "NULL",
    "use_armature_deform_only": False,
    "add_leaf_bones": True,
    "bake_anim": True,
    "bake_anim_use_all_bones": True,
    "bake_anim_use_nla_strips": True,
    "bake_anim_use_all_actions": True,
    "bake_anim_force_startend_keying": True,
    "bake_anim_step": 1.0,
    "bake_anim_simplify_factor": 1.0,
    "embed_textures": False,
}


def _distance_to_segment(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    length_squared = dx * dx + dy * dy
    if length_squared == 0.0:
        return math.hypot(px - ax, py - ay)
    factor = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_squared))
    return math.hypot(px - (ax + factor * dx), py - (ay + factor * dy))


def _status_icon_pixels(kind):
    """Create antialiased RGBA pixels whose colours Blender will not theme-tint."""
    size = STATUS_ICON_SIZE
    scale = STATUS_ICON_SCALE
    pixels = [0.0] * (size * size * 4)
    for y in range(size):
        for x in range(size):
            colour_totals = [0.0, 0.0, 0.0, 0.0]
            for sy in range(scale):
                for sx in range(scale):
                    px = (x + (sx + 0.5) / scale) / size
                    py = (y + (sy + 0.5) / scale) / size
                    if kind == "WARNING":
                        # Upright amber triangle with a dark exclamation mark.
                        inside = py >= 0.13 and py <= 0.85 and abs(px - 0.5) <= (0.88 - py) * 0.56
                        if inside:
                            colour = (1.0, 0.55, 0.035, 1.0)
                            if (0.465 <= px <= 0.535 and 0.33 <= py <= 0.62) or (
                                (px - 0.5) ** 2 + (py - 0.24) ** 2 <= 0.042 ** 2
                            ):
                                colour = (0.10, 0.065, 0.025, 1.0)
                        else:
                            colour = (0.0, 0.0, 0.0, 0.0)
                    else:
                        # A genuine green tick; the transparent background keeps Ready text neutral.
                        distance = min(
                            _distance_to_segment(px, py, 0.18, 0.49, 0.41, 0.27),
                            _distance_to_segment(px, py, 0.41, 0.27, 0.83, 0.73),
                        )
                        colour = (0.12, 0.82, 0.25, 1.0) if distance <= 0.075 else (0.0, 0.0, 0.0, 0.0)
                    for channel in range(4):
                        colour_totals[channel] += colour[channel]
            samples = scale * scale
            offset = (y * size + x) * 4
            pixels[offset:offset + 4] = [value / samples for value in colour_totals]
    return pixels


def _png_chunk(chunk_type, data):
    return (
        struct.pack(">I", len(data)) + chunk_type + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def _write_status_icon(path, pixels):
    """Write a small RGBA PNG for Blender's persistent custom-preview API."""
    size = STATUS_ICON_SIZE
    rows = []
    # Blender's float image coordinates are bottom-up; PNG scanlines are top-down.
    for png_y in range(size):
        source_y = size - 1 - png_y
        row = bytearray([0])
        for x in range(size):
            offset = (source_y * size + x) * 4
            row.extend(round(max(0.0, min(1.0, pixels[offset + channel])) * 255) for channel in range(4))
        rows.append(bytes(row))
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(b"".join(rows), level=9))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def _ensure_status_icons():
    global _STATUS_PREVIEWS, _WARNING_ICON_ID, _READY_ICON_ID
    _remove_status_icons()
    icon_directory = Path(bpy.app.tempdir or tempfile.gettempdir()) / "mw_cs2_batch_exporter"
    icon_directory.mkdir(parents=True, exist_ok=True)
    warning_path = icon_directory / WARNING_ICON_FILE
    ready_path = icon_directory / READY_ICON_FILE
    _write_status_icon(warning_path, _status_icon_pixels("WARNING"))
    _write_status_icon(ready_path, _status_icon_pixels("READY"))

    previews = bpy.utils.previews.new()
    warning = previews.load("warning", str(warning_path), "IMAGE", force_reload=True)
    ready = previews.load("ready", str(ready_path), "IMAGE", force_reload=True)
    _STATUS_PREVIEWS = previews
    _WARNING_ICON_ID = warning.icon_id
    _READY_ICON_ID = ready.icon_id


def _remove_status_icons():
    global _STATUS_PREVIEWS, _WARNING_ICON_ID, _READY_ICON_ID
    if _STATUS_PREVIEWS is not None:
        try:
            bpy.utils.previews.remove(_STATUS_PREVIEWS)
        except (ReferenceError, RuntimeError):
            pass
        _STATUS_PREVIEWS = None
    _WARNING_ICON_ID = 0
    _READY_ICON_ID = 0
    icon_directory = Path(bpy.app.tempdir or tempfile.gettempdir()) / "mw_cs2_batch_exporter"
    for filename in (WARNING_ICON_FILE, READY_ICON_FILE):
        try:
            (icon_directory / filename).unlink(missing_ok=True)
        except OSError:
            pass


def _status_icon_options(severity):
    if severity == "WARNING" and _custom_status_icons_ready():
        return {"icon_value": _WARNING_ICON_ID}
    if severity == "PASS" and _custom_status_icons_ready():
        return {"icon_value": _READY_ICON_ID}
    return {
        "icon": {
            "ERROR": "STATUS_ERROR_FILLED",
            "WARNING": "STATUS_WARNING_FILLED",
            "PASS": "CHECKMARK",
        }.get(severity, "INFO")
    }


def _custom_status_icons_ready():
    """Only expose icon handles still owned by the live preview collection."""
    if _STATUS_PREVIEWS is None or _WARNING_ICON_ID <= 0 or _READY_ICON_ID <= 0:
        return False
    try:
        return (
            _STATUS_PREVIEWS["warning"].icon_id == _WARNING_ICON_ID
            and _STATUS_PREVIEWS["ready"].icon_id == _READY_ICON_ID
        )
    except (KeyError, ReferenceError, RuntimeError):
        return False


def _is_close_sequence(values, expected):
    return all(abs(a - b) <= EPSILON for a, b in zip(values, expected))


def _counted(value, singular):
    return f"{value} {singular if value == 1 else singular + 's'}"


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


def _is_lod2(name):
    return re.search(r"(?:^|_)LOD2(?:_|$)", name, re.IGNORECASE) is not None


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


def _has_valid_export_destination(export_directory):
    if not export_directory:
        return False
    directory = Path(bpy.path.abspath(export_directory))
    return not directory.exists() or directory.is_dir()


def collect_issues(context, objects, export_directory, check_existing=True, ignore_ngons=False):
    issues = []

    if not objects:
        issues.append(Issue(
            "ERROR", "Selection", "No mesh objects",
            "Select at least one mesh object to check or export.",
        ))
        return issues

    scene = context.scene
    unit = scene.unit_settings
    if unit.system != "METRIC" or abs(unit.scale_length - 1.0) > EPSILON:
        issues.append(Issue(
            "ERROR", "Scene", "Metric units required",
            "Set the scene to Metric with Unit Scale 1.0. CS2 uses 1 Blender unit as 1 metre.",
        ))

    directory = Path(bpy.path.abspath(export_directory)) if export_directory else None

    seen_names = {}
    for obj in objects:
        name = obj.name
        filename_error = _portable_filename_error(name)
        if filename_error:
            issues.append(Issue("ERROR", name, "Invalid filename", filename_error))

        portable_key = f"{name}.fbx".casefold()
        if portable_key in seen_names:
            issues.append(Issue(
                "ERROR", name, "Filename conflict",
                f"This name conflicts with '{seen_names[portable_key]}' on a case-insensitive filesystem.",
            ))
        else:
            seen_names[portable_key] = name

        if directory and directory.is_dir() and check_existing:
            destination = export_path(directory, name)
            if destination.exists():
                issues.append(Issue("ERROR", name, "Existing FBX", "An FBX with this name already exists. Enable Overwrite Existing to replace it."))

        if not _is_close_sequence(obj.scale, (1.0, 1.0, 1.0)):
            issues.append(Issue("ERROR", name, "Scale not applied", "Apply the object's scale so it reads 1, 1, 1 before export."))
        if any(value < 0.0 for value in obj.scale):
            issues.append(Issue("ERROR", name, "Negative scale", "Negative scale can invert mesh handedness and normals during FBX export."))
        if not _is_close_sequence(obj.rotation_euler, (0.0, 0.0, 0.0)):
            degrees = tuple(round(math.degrees(value), 3) for value in obj.rotation_euler)
            issues.append(Issue("ERROR", name, "Rotation not applied", f"Apply the object's rotation. Current Euler rotation: {degrees} degrees."))
        mesh = obj.data
        if not mesh.vertices or not mesh.polygons:
            issues.append(Issue("ERROR", name, "Empty mesh", "The mesh contains no faces that can be exported."))
        if not mesh.uv_layers:
            issues.append(Issue("WARNING", name, "No UV map", "Add a UV map before texturing or importing this mesh into CS2."))
        elif mesh.uv_layers.active is None:
            issues.append(Issue("WARNING", name, "No active UV map", "Choose which UV map Blender should export as the active UV layer."))

        material_slots = list(obj.material_slots)
        assigned_materials = [slot.material for slot in material_slots if slot.material]
        if _is_lod2(name):
            if material_slots:
                issues.append(Issue("WARNING", name, "LOD2 has materials", "LOD2 meshes should have zero material slots for the CS2 import workflow."))
        elif _is_special_submesh(name):
            if material_slots:
                issues.append(Issue("WARNING", name, "Submesh has materials", "Known CS2 special submeshes such as Win, Wim, Gls, Gra, and Wat should have zero material slots."))
        elif len(assigned_materials) != len(material_slots):
            issues.append(Issue("WARNING", name, "Empty material slots", "Remove empty material slots or assign a material to each slot."))
        elif not assigned_materials:
            issues.append(Issue("WARNING", name, "No material", "Main and LOD1 meshes normally use one material, which may be shared with other meshes."))
        elif len(assigned_materials) > 1:
            issues.append(Issue("WARNING", name, "Multiple materials", "Main and LOD1 meshes normally use one material. Multiple slots may not match the intended CS2 material layout."))

        if not ignore_ngons and any(len(poly.vertices) > 4 for poly in mesh.polygons):
            issues.append(Issue(
                "WARNING", name, "N-gons used",
                "Faces with more than four vertices may be triangulated differently by downstream tools or CS2 import.",
            ))

    return issues


def selected_meshes(context):
    return sorted((obj for obj in context.selected_objects if obj.type == "MESH"), key=lambda obj: obj.name.casefold())


def _resolve_source(context, settings, source):
    if source == "COLLECTION":
        collections = [entry.collection for entry in settings.export_collections if entry.collection]
        if not collections and settings.export_collection:
            collections = [settings.export_collection]
        if not collections:
            return [], [], [Issue("ERROR", "Selection", "No collection", "Choose a collection to check or export.")], "collection"
        unique_objects = {}
        for collection in collections:
            for obj in collection.all_objects:
                unique_objects[obj.as_pointer()] = obj
        source_objects = sorted(unique_objects.values(), key=lambda obj: (obj.name.casefold(), obj.name))
        objects = [obj for obj in source_objects if obj.type == "MESH"]
        source_label = (
            f"collection '{collections[0].name}'" if len(collections) == 1
            else f"{len(collections)} collections"
        )
        if not objects:
            return [], [], [Issue(
                "ERROR", "Selection", "No mesh objects", "The chosen collection source contains no mesh objects.",
            )], source_label
        unavailable = [obj for obj in objects if obj.name not in context.view_layer.objects]
        issues = [Issue(
            "ERROR", obj.name, "Unavailable object", "This object is not available in the active view layer and cannot be selected for FBX export.",
        ) for obj in unavailable]
        return objects, objects, issues, source_label

    objects = selected_meshes(context)
    return objects, objects, [], "the selection"


def _collect_preflight(context, settings, source):
    objects, report_objects, source_issues, source_label = _resolve_source(
        context, settings, source,
    )
    issues = list(source_issues)
    if objects:
        issues.extend(collect_issues(
            context, objects, settings.export_directory,
            check_existing=not settings.overwrite_existing,
            ignore_ngons=settings.ignore_ngons,
        ))
    return objects, report_objects, issues, source_label


def _store_report(scene, issues, heading, objects=()):
    object_names = [obj if isinstance(obj, str) else obj.name for obj in objects]
    error_count = sum(issue.severity == "ERROR" for issue in issues)
    warning_count = sum(issue.severity == "WARNING" for issue in issues)
    lines = [
        f"HEADER\t{heading}",
        f"SUMMARY\t{_counted(error_count, 'error')}, {_counted(warning_count, 'warning')}",
    ]

    general_labels = {"Scene", "Export", "Selection"}
    general_issues = [issue for issue in issues if issue.object_name in general_labels]
    if general_issues:
        lines.append("SECTION\tGeneral")
        lines.extend(f"{issue.severity}\t{issue.message}\t{issue.detail}" for issue in general_issues)

    ordered_names = list(dict.fromkeys(object_names))
    ordered_names.extend(
        issue.object_name for issue in issues
        if issue.object_name not in general_labels and issue.object_name not in ordered_names
    )
    for name in ordered_names:
        lines.append(f"SECTION\t{name}")
        object_issues = [issue for issue in issues if issue.object_name == name]
        if object_issues:
            lines.extend(f"{issue.severity}\t{issue.message}\t{issue.detail}" for issue in object_issues)
        else:
            lines.append("PASS\tReady to export")
    scene.cs2_batch_export_report = "\n".join(lines)
    scene.cs2_batch_export_settings.report_expanded = True

    groups = scene.cs2_batch_export_report_groups
    groups.clear()

    def add_group(name, group_issues):
        group = groups.add()
        group.name = name
        if not group_issues:
            report_issue = group.issues.add()
            report_issue.severity = "PASS"
            report_issue.message = "Ready to export"
            return
        for issue in group_issues:
            report_issue = group.issues.add()
            report_issue.severity = issue.severity
            report_issue.message = issue.message
            report_issue.detail = issue.detail
            report_issue.action = "MATERIAL" if issue.message in MATERIAL_ISSUE_MESSAGES else ""
            if issue.severity == "ERROR":
                group.error_count += 1
            elif issue.severity == "WARNING":
                group.warning_count += 1

    if general_issues:
        add_group("General", general_issues)
    for name in ordered_names:
        add_group(name, [issue for issue in issues if issue.object_name == name])

    preferred_index = next((index for index, group in enumerate(groups) if group.error_count), None)
    if preferred_index is None:
        preferred_index = next((index for index, group in enumerate(groups) if group.warning_count), 0)
    scene.cs2_batch_export_report_index = preferred_index

    rows = scene.cs2_batch_export_report_rows
    rows.clear()
    for group in groups:
        count_parts = []
        if group.error_count:
            count_parts.append(
                f"{group.error_count} error" if group.error_count == 1 else f"{group.error_count} errors"
            )
        if group.warning_count:
            count_parts.append(
                f"{group.warning_count} warning" if group.warning_count == 1 else f"{group.warning_count} warnings"
            )
        header = rows.add()
        header.kind = "HEADER"
        header.object_name = group.name
        header.count_text = ", ".join(count_parts) if count_parts else "Ready"
        header.severity = (
            "ERROR" if group.error_count else "WARNING" if group.warning_count else "PASS"
        )
        for issue in group.issues:
            if issue.severity == "PASS":
                continue
            report_row = rows.add()
            report_row.kind = "ISSUE"
            report_row.object_name = group.name
            report_row.severity = issue.severity
            report_row.message = issue.message
            report_row.detail = issue.detail
            report_row.action = issue.action

    preferred_group_name = groups[preferred_index].name if groups else ""
    scene.cs2_batch_export_report_index = next(
        (index for index, row in enumerate(rows) if row.kind == "HEADER" and row.object_name == preferred_group_name),
        0,
    )


def _refresh_report_for_destination(settings, context):
    """Refresh an existing report immediately after the destination changes."""
    scene = getattr(context, "scene", None) if context else None
    if scene is None or not getattr(scene, "cs2_batch_export_report", ""):
        return
    objects, report_objects, issues, source_label = _collect_preflight(
        context, settings, settings.source_mode,
    )
    _store_report(
        scene, issues,
        f"Checked {len(objects)} mesh object(s) from {source_label}", report_objects,
    )


def _wrapped_text(text, width=48):
    return textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False) or [""]


def _draw_wrapped_label(layout, text, icon="NONE", icon_value=0, width=48, alert=False):
    for index, line in enumerate(_wrapped_text(text, width)):
        row = layout.row()
        row.alignment = "LEFT"
        row.alert = alert
        if index == 0 and icon_value:
            row.label(text=line, icon_value=icon_value)
        else:
            row.label(text=line, icon=icon if index == 0 else "BLANK1")


def _report_summary(scene):
    groups = scene.cs2_batch_export_report_groups
    object_count = sum(group.name != "General" for group in groups)
    error_count = sum(group.error_count for group in groups)
    warning_count = sum(group.warning_count for group in groups)

    return (
        f"{_counted(object_count, 'object')} checked · "
        f"{_counted(error_count, 'error')} · {_counted(warning_count, 'warning')}"
    )


def _report_summary_severity(scene):
    groups = scene.cs2_batch_export_report_groups
    if any(group.error_count for group in groups):
        return "ERROR"
    if any(group.warning_count for group in groups):
        return "WARNING"
    return "PASS"


def _draw_report_entry(layout, severity, message, detail="", width=48):
    icon = {"ERROR": "ERROR", "WARNING": "INFO", "PASS": "CHECKMARK"}.get(severity, "INFO")
    label = {"ERROR": "Error", "WARNING": "Warning", "PASS": "Ready"}.get(severity, severity.title())
    entry = layout.column(align=True)
    for index, line in enumerate(_wrapped_text(f"{label}: {message}", width=width)):
        row = entry.row()
        row.alignment = "LEFT"
        row.alert = severity == "ERROR"
        operator = row.operator(
            "cs2_batch.report_detail",
            text=line,
            icon=icon if index == 0 else "BLANK1",
            emboss=False,
        )
        operator.message = message
        operator.detail = detail or message
    entry.separator(factor=REPORT_ENTRY_SPACING)


def _draw_report_section(layout, name):
    section = layout.box()
    if name == "General":
        heading_row = section.row()
        heading_row.alignment = "LEFT"
        heading_row.label(text=name, icon="PREFERENCES")
        return section
    # UILayout headings use Blender's emphasized heading typography.
    return section.column(heading=name, align=True)


class CS2BatchCollectionEntry(PropertyGroup):
    collection: PointerProperty(type=bpy.types.Collection, options={"SKIP_SAVE"})


class CS2BatchExportSettings(PropertyGroup):
    source_mode: EnumProperty(
        name="Source",
        description="Choose whether the shared Check and Export actions use selected objects or collections",
        items=(
            ("SELECTION", "Selected Objects", "Use selected mesh objects in the active view layer", "OBJECT_DATA", 0),
            ("COLLECTION", "Collections", "Use the chosen collection or collection list", "OUTLINER_COLLECTION", 1),
        ),
        default="SELECTION",
    )
    report_expanded: BoolProperty(
        name="Show Report",
        description="Expand or collapse the report without clearing its contents",
        default=False,
        options={"SKIP_SAVE"},
    )
    export_directory: StringProperty(
        name="Export Folder",
        description="Folder for individual FBX files",
        subtype="DIR_PATH",
        update=_refresh_report_for_destination,
    )
    stop_on_warnings: BoolProperty(
        name="Stop on Warnings",
        description="Do not export while any preflight warning remains",
        default=False,
    )
    ignore_ngons: BoolProperty(
        name="Ignore N-gons",
        description="Do not report intentional N-gons as warnings; meshes are unchanged and FBX Triangulate Faces remains disabled",
        default=False,
    )
    overwrite_existing: BoolProperty(
        name="Overwrite Existing",
        description="Allow an existing same-named FBX to be replaced",
        default=False,
    )
    export_collection: PointerProperty(
        name="Collection",
        description="Quick single collection source, or choose a collection here and add it to the multi-collection list",
        type=bpy.types.Collection,
    )
    export_collections: CollectionProperty(type=CS2BatchCollectionEntry, options={"SKIP_SAVE"})
    export_collection_index: IntProperty(options={"SKIP_SAVE"})


class CS2BatchReportIssue(PropertyGroup):
    severity: StringProperty(options={"SKIP_SAVE"})
    message: StringProperty(options={"SKIP_SAVE"})
    detail: StringProperty(options={"SKIP_SAVE"})
    action: StringProperty(options={"SKIP_SAVE"})


class CS2BatchReportGroup(PropertyGroup):
    name: StringProperty(options={"SKIP_SAVE"})
    issues: CollectionProperty(type=CS2BatchReportIssue, options={"SKIP_SAVE"})
    error_count: IntProperty(options={"SKIP_SAVE"})
    warning_count: IntProperty(options={"SKIP_SAVE"})


class CS2BatchReportRow(PropertyGroup):
    kind: StringProperty(options={"SKIP_SAVE"})
    object_name: StringProperty(options={"SKIP_SAVE"})
    count_text: StringProperty(options={"SKIP_SAVE"})
    severity: StringProperty(options={"SKIP_SAVE"})
    message: StringProperty(options={"SKIP_SAVE"})
    detail: StringProperty(options={"SKIP_SAVE"})
    action: StringProperty(options={"SKIP_SAVE"})


class CS2BATCH_UL_report_rows(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if item.kind == "HEADER":
            header = layout.row(align=True)
            header.alignment = "LEFT"
            header.label(text=item.object_name, icon="OBJECT_DATA")
            status = header.row(align=True)
            status.alignment = "RIGHT"
            if item.count_text == "Ready":
                status.label(text="Ready", **_status_icon_options("PASS"))
            elif item.severity == "ERROR":
                status.label(text=item.count_text, **_status_icon_options("ERROR"))
            else:
                status.label(text=item.count_text, **_status_icon_options("WARNING"))
            return

        row = layout.row(align=True)
        row.alignment = "LEFT"
        row.label(text="", icon="BLANK1")
        severity = item.severity
        row.alert = severity == "ERROR"
        row.label(text="", **_status_icon_options(severity))
        if item.action == "MATERIAL":
            operator = row.operator(
                "cs2_batch.open_material_issue", text=f"Warning · {item.message}",
                icon="MATERIAL", emboss=True,
            )
            operator.object_name = item.object_name
            operator.message = item.message
            operator.detail = item.detail or item.message
        else:
            display_message = (
                f"Error · {item.message}" if severity == "ERROR"
                else f"Warning · {item.message}" if severity == "WARNING"
                else item.message
            )
            row.label(text=display_message)
            detail = row.operator(
                "cs2_batch.report_detail", text="", icon="INFO", emboss=False,
            )
            detail.message = item.message
            detail.detail = item.detail or item.message


class CS2BATCH_UL_collections(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        collection = item.collection
        layout.label(
            text=collection.name if collection else "Missing collection",
            icon="OUTLINER_COLLECTION" if collection else "ERROR",
        )


class CS2BATCH_OT_report_detail(Operator):
    bl_idname = "cs2_batch.report_detail"
    bl_label = "Report Detail"
    bl_options = {"INTERNAL"}

    message: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    detail: StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    @classmethod
    def description(cls, context, properties):
        return properties.detail or properties.message

    def execute(self, context):
        return {"FINISHED"}


def _open_material_properties(context):
    window_manager = getattr(context, "window_manager", None)
    for window in getattr(window_manager, "windows", ()):
        for area in window.screen.areas:
            if area.type != "PROPERTIES":
                continue
            try:
                area.spaces.active.context = "MATERIAL"
            except (AttributeError, TypeError, ValueError):
                continue
            area.tag_redraw()
            return True
    return False


class CS2BATCH_OT_open_material_issue(Operator):
    bl_idname = "cs2_batch.open_material_issue"
    bl_label = "Open Material Issue"
    bl_options = {"REGISTER", "UNDO"}

    object_name: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    message: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    detail: StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    @classmethod
    def description(cls, context, properties):
        explanation = properties.detail or properties.message
        return f"Select '{properties.object_name}' and open Material Properties. {explanation}"

    def execute(self, context):
        obj = context.view_layer.objects.get(self.object_name)
        if obj is None:
            self.report({"WARNING"}, f"Object '{self.object_name}' is not available in this view layer.")
            return {"CANCELLED"}

        if context.mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except RuntimeError:
                self.report({"WARNING"}, "Switch to Object Mode to open this material issue.")
                return {"CANCELLED"}

        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        context.view_layer.objects.active = obj

        if _open_material_properties(context):
            self.report({"INFO"}, f"Opened Material Properties for '{obj.name}'.")
        else:
            self.report({"WARNING"}, f"Selected '{obj.name}'; no Properties editor is open.")
        return {"FINISHED"}


class CS2BATCH_OT_clear_export_selection(Operator):
    bl_idname = "cs2_batch.clear_export_selection"
    bl_label = "Clear Export Selection"
    bl_description = "Deselect scene objects and clear collection export choices; destination, options, report, and files are unchanged"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def execute(self, context):
        settings = context.scene.cs2_batch_export_settings
        if context.mode == "OBJECT":
            bpy.ops.object.select_all(action="DESELECT")
        settings.export_collection = None
        settings.export_collections.clear()
        settings.export_collection_index = 0
        self.report({"INFO"}, "Export selection cleared.")
        return {"FINISHED"}


class CS2BATCH_OT_clear_report(Operator):
    bl_idname = "cs2_batch.clear_report"
    bl_label = "Clear Report"
    bl_description = "Clear only the generated report and keep all exporter choices"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.cs2_batch_export_report)

    def execute(self, context):
        scene = context.scene
        scene.cs2_batch_export_report = ""
        scene.cs2_batch_export_report_groups.clear()
        scene.cs2_batch_export_report_rows.clear()
        scene.cs2_batch_export_report_index = 0
        scene.cs2_batch_export_settings.report_expanded = False
        self.report({"INFO"}, "Report cleared.")
        return {"FINISHED"}


class CS2BATCH_OT_add_collection(Operator):
    bl_idname = "cs2_batch.add_collection"
    bl_label = "Add Collection"
    bl_description = "Add the chosen collection to the multi-collection export list"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.scene.cs2_batch_export_settings.export_collection is not None

    def execute(self, context):
        settings = context.scene.cs2_batch_export_settings
        collection = settings.export_collection
        if any(entry.collection == collection for entry in settings.export_collections):
            self.report({"INFO"}, f"'{collection.name}' is already in the collection list.")
            return {"CANCELLED"}
        entry = settings.export_collections.add()
        entry.collection = collection
        settings.export_collection_index = len(settings.export_collections) - 1
        self.report({"INFO"}, f"Added collection '{collection.name}'.")
        return {"FINISHED"}


class CS2BATCH_OT_remove_collection(Operator):
    bl_idname = "cs2_batch.remove_collection"
    bl_label = "Remove Collection"
    bl_description = "Remove the highlighted collection from the multi-collection export list"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.cs2_batch_export_settings.export_collections)

    def execute(self, context):
        settings = context.scene.cs2_batch_export_settings
        index = min(max(settings.export_collection_index, 0), len(settings.export_collections) - 1)
        settings.export_collections.remove(index)
        settings.export_collection_index = min(index, max(0, len(settings.export_collections) - 1))
        return {"FINISHED"}


class CS2BATCH_OT_check(Operator):
    bl_idname = "cs2_batch.check_selected"
    bl_label = "Check Export Source"
    bl_description = "Run CS2 preflight checks for the chosen export source without changing the scene"
    bl_options = {"REGISTER"}

    source: EnumProperty(
        items=(("SELECTION", "Selection", "Check selected objects"),
               ("COLLECTION", "Collection", "Check objects in the chosen collection")),
        default="SELECTION",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def execute(self, context):
        settings = context.scene.cs2_batch_export_settings
        objects, report_objects, issues, source_label = _collect_preflight(
            context, settings, self.source,
        )
        _store_report(
            context.scene, issues,
            f"Checked {len(objects)} mesh object(s) from {source_label}", report_objects,
        )
        error_count = sum(issue.severity == "ERROR" for issue in issues)
        warning_count = sum(issue.severity == "WARNING" for issue in issues)
        self.report(
            {"ERROR" if error_count else "INFO"},
            f"Preflight: {_counted(error_count, 'error')}, {_counted(warning_count, 'warning')}",
        )
        return {"FINISHED"}


class CS2BATCH_OT_export(Operator):
    bl_idname = "cs2_batch.export_selected"
    bl_label = "Export FBX Files"
    bl_description = "Export each mesh in the chosen source as an individual FBX using its exact object name"
    bl_options = {"REGISTER"}

    source: EnumProperty(
        items=(("SELECTION", "Selection", "Export selected objects"),
               ("COLLECTION", "Collection", "Export objects in the chosen collection")),
        default="SELECTION",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def execute(self, context):
        scene = context.scene
        settings = scene.cs2_batch_export_settings
        if not _has_valid_export_destination(settings.export_directory):
            self.report({"ERROR"}, "Choose a valid export folder.")
            return {"CANCELLED"}

        objects, report_objects, issues, source_label = _collect_preflight(
            context, settings, self.source,
        )
        errors = [issue for issue in issues if issue.severity == "ERROR"]
        warnings = [issue for issue in issues if issue.severity == "WARNING"]
        if errors or (settings.stop_on_warnings and warnings):
            _store_report(scene, issues, "Export stopped by preflight", report_objects)
            self.report({"ERROR"}, "Export stopped. Review the preflight report.")
            return {"CANCELLED"}

        directory = Path(bpy.path.abspath(settings.export_directory))
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            issues.append(Issue("ERROR", "Export", "Cannot create folder", str(exc)))
            _store_report(scene, issues, "Export failed", report_objects)
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
                    **FBX_EXPORT_SETTINGS,
                )
                if result != {"FINISHED"}:
                    raise RuntimeError(f"Blender FBX exporter returned {result!r}")
                exported.append(os.fspath(destination.relative_to(directory)))
        except Exception as exc:  # Blender operators can raise several runtime exception types.
            issues.append(Issue("ERROR", "Export", "FBX export failed", str(exc)))
            _store_report(scene, issues, f"Export failed after {len(exported)} file(s)", report_objects)
            self.report({"ERROR"}, f"Export failed after {len(exported)} file(s).")
            return {"CANCELLED"}
        finally:
            bpy.ops.object.select_all(action="DESELECT")
            for obj in original_selection:
                if obj.name in context.view_layer.objects:
                    obj.select_set(True)
            if original_active and original_active.name in context.view_layer.objects:
                context.view_layer.objects.active = original_active

        _store_report(
            scene, warnings,
            f"Exported {len(exported)} file(s) from {source_label} to {directory}", report_objects,
        )
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
        report_width = max(24, min(56, int(context.region.width / 7))) if context.region else 48

        destination = layout.box()
        destination.label(text="Destination", icon="FILE_FOLDER")
        destination.prop(settings, "export_directory", text="")

        options = layout.box()
        options.label(text="Options", icon="PREFERENCES")
        row = options.row(align=True)
        row.prop(settings, "overwrite_existing")
        row.prop(settings, "stop_on_warnings")
        options.prop(settings, "ignore_ngons")

        source_box = layout.box()
        source_box.label(text="Export Source", icon="OUTLINER_COLLECTION")
        source_selector = source_box.row(align=True)
        source_selector.prop(settings, "source_mode", expand=True)

        if settings.source_mode == "COLLECTION":
            collection_box = source_box.box()
            collection_box.prop(settings, "export_collection", text="")
            collection_actions = collection_box.row(align=True)
            collection_actions.operator("cs2_batch.add_collection", text="Add", icon="ADD")
            remove_row = collection_actions.row(align=True)
            remove_row.enabled = bool(settings.export_collections)
            remove_row.operator("cs2_batch.remove_collection", text="Remove", icon="REMOVE")
            if settings.export_collections:
                collection_box.template_list(
                    "CS2BATCH_UL_collections", "export_collections",
                    settings, "export_collections",
                    settings, "export_collection_index",
                    rows=min(4, max(2, len(settings.export_collections))), maxrows=4,
                )
        else:
            source_hint = source_box.row()
            source_hint.alignment = "LEFT"
            source_hint.label(text="Uses selected mesh objects", icon="OBJECT_DATA")

        check_row = source_box.row()
        check_row.operator(
            "cs2_batch.check_selected", text="Check Export Source", icon="CHECKMARK",
        ).source = settings.source_mode
        export_row = source_box.row()
        export_row.scale_y = 1.2
        export_row.enabled = _has_valid_export_destination(settings.export_directory)
        export_row.operator(
            "cs2_batch.export_selected", text="Export FBX Files", icon="EXPORT",
        ).source = settings.source_mode

        clear_selection_row = layout.row()
        clear_selection_row.alignment = "LEFT"
        clear_selection_row.operator(
            "cs2_batch.clear_export_selection", text="Clear Export Selection", icon="X",
        )

        report = layout.box()
        report_header = report.row(align=True)
        report_header.prop(
            settings, "report_expanded", text="",
            icon="TRIA_DOWN" if settings.report_expanded else "TRIA_RIGHT",
            emboss=False,
        )
        report_header.label(text="Report", icon="INFO")
        if settings.report_expanded:
            if scene.cs2_batch_export_report:
                clear_report = report_header.row(align=True)
                clear_report.alignment = "RIGHT"
                clear_report.operator("cs2_batch.clear_report", text="Clear Report", icon="TRASH")

                for line in scene.cs2_batch_export_report.splitlines():
                    kind, _, text = line.partition("\t")
                    if kind == "HEADER":
                        _draw_wrapped_label(report, text, width=report_width)
                    elif kind == "SUMMARY":
                        summary_severity = _report_summary_severity(scene)
                        summary_row = report.row()
                        summary_row.alignment = "LEFT"
                        summary_row.alert = summary_severity == "ERROR"
                        summary_row.label(text=text, **_status_icon_options(summary_severity))

                report_rows = scene.cs2_batch_export_report_rows
                if report_rows:
                    list_rows = max(4, min(12, len(report_rows)))
                    report.template_list(
                        "CS2BATCH_UL_report_rows", "report_rows",
                        scene, "cs2_batch_export_report_rows",
                        scene, "cs2_batch_export_report_index",
                        rows=list_rows, maxrows=12,
                    )
            else:
                empty_report = report.row()
                empty_report.alignment = "LEFT"
                empty_report.label(text="No report generated", icon="INFO")
        elif scene.cs2_batch_export_report:
            summary_severity = _report_summary_severity(scene)
            summary_icon = _status_icon_options(summary_severity)
            _draw_wrapped_label(
                report, _report_summary(scene),
                width=report_width, alert=summary_severity == "ERROR",
                **summary_icon,
            )
        else:
            empty_report = report.row()
            empty_report.alignment = "LEFT"
            empty_report.label(text="No report generated")


CLASSES = (
    CS2BatchCollectionEntry,
    CS2BatchReportIssue,
    CS2BatchReportGroup,
    CS2BatchReportRow,
    CS2BatchExportSettings,
    CS2BATCH_UL_report_rows,
    CS2BATCH_UL_collections,
    CS2BATCH_OT_report_detail,
    CS2BATCH_OT_open_material_issue,
    CS2BATCH_OT_clear_export_selection,
    CS2BATCH_OT_clear_report,
    CS2BATCH_OT_add_collection,
    CS2BATCH_OT_remove_collection,
    CS2BATCH_OT_check,
    CS2BATCH_OT_export,
    CS2BATCH_PT_panel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.cs2_batch_export_settings = bpy.props.PointerProperty(type=CS2BatchExportSettings)
    bpy.types.Scene.cs2_batch_export_report = StringProperty(options={"SKIP_SAVE"})
    bpy.types.Scene.cs2_batch_export_report_groups = CollectionProperty(
        type=CS2BatchReportGroup, options={"SKIP_SAVE"},
    )
    bpy.types.Scene.cs2_batch_export_report_rows = CollectionProperty(
        type=CS2BatchReportRow, options={"SKIP_SAVE"},
    )
    bpy.types.Scene.cs2_batch_export_report_index = IntProperty(options={"SKIP_SAVE"})
    try:
        _ensure_status_icons()
    except Exception:
        # Native semantic icons remain available if preview creation is unavailable.
        _remove_status_icons()


def unregister():
    del bpy.types.Scene.cs2_batch_export_report_index
    del bpy.types.Scene.cs2_batch_export_report_rows
    del bpy.types.Scene.cs2_batch_export_report_groups
    del bpy.types.Scene.cs2_batch_export_report
    del bpy.types.Scene.cs2_batch_export_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    _remove_status_icons()


if __name__ == "__main__":
    register()
