import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

import bpy


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import mw_cs2_batch_exporter as addon


class FakeLayout:
    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)
        if name == "alert" and value and hasattr(self, "events"):
            self.events.append(("alert", True))

    def __init__(self, events=None):
        self.events = events if events is not None else []
        self.alignment = "EXPAND"
        self.alert = False
        self.enabled = True

    def box(self):
        return FakeLayout(self.events)

    def row(self, **kwargs):
        if kwargs.get("heading"):
            self.events.append(("heading", kwargs["heading"]))
        return FakeLayout(self.events)

    def column(self, **kwargs):
        if kwargs.get("heading"):
            self.events.append(("heading", kwargs["heading"]))
        return FakeLayout(self.events)

    def label(self, **kwargs):
        self.events.append(("label", kwargs.get("text", "")))
        self.events.append(("label_options", kwargs.get("text", ""), dict(kwargs)))

    def prop(self, *args, **kwargs):
        property_name = args[1] if len(args) > 1 else ""
        self.events.append(("prop", property_name, kwargs.get("expand", False)))
        self.events.append(("prop_options", property_name, dict(kwargs)))

    def separator(self, **kwargs):
        self.events.append(("separator", kwargs.get("factor")))

    def operator(self, *args, **kwargs):
        operator_id = args[0] if args else ""
        self.events.append(("operator", operator_id, kwargs.get("text", "")))
        self.events.append(("operator_enabled", operator_id, self.enabled))
        self.events.append(("operator_options", operator_id, kwargs.get("text", ""), dict(kwargs)))
        properties = SimpleNamespace(source="", message="", detail="")
        self.events.append(("operator_properties", operator_id, properties))
        return properties

    def template_list(self, *args, **kwargs):
        self.events.append(("template_list", args[0], kwargs.get("rows"), kwargs.get("maxrows")))


def make_mesh_object(name, x_offset=0.0, material_name=None):
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(
        [(-0.5, -0.5, 0.0), (0.5, -0.5, 0.0), (0.5, 0.5, 0.0), (-0.5, 0.5, 0.0)],
        [],
        [(0, 1, 2, 3)],
    )
    mesh.uv_layers.new(name="UVMap")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if material_name is not False:
        material = bpy.data.materials.get(material_name or name) or bpy.data.materials.new(material_name or name)
        obj.data.materials.append(material)
    obj.location.x = x_offset
    return obj


def assert_cancelled_error(operator_call, expected_message):
    """Accept Blender's Python error-report behavior for a cancelled operator."""
    try:
        result = operator_call()
    except RuntimeError as exc:
        assert expected_message in str(exc), exc
    else:
        assert result == {"CANCELLED"}, result


def main():
    addon.register()
    assert addon.bl_info["version"] == (0, 1, 24)
    assert addon.FBX_EXPORT_SETTINGS == {
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
    icon_items = bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items
    icons = {item.identifier for item in icon_items}
    assert {
        "ERROR", "INFO", "CHECKMARK", "OBJECT_DATA", "PREFERENCES",
        "BLANK1", "FILE_FOLDER", "OUTLINER_COLLECTION", "X", "ADD", "REMOVE", "TRASH",
        "TRIA_DOWN", "TRIA_RIGHT", "MATERIAL",
        "STATUS_ERROR", "STATUS_ERROR_FILLED", "STATUS_WARNING", "STATUS_WARNING_FILLED",
    } <= icons
    column_parameters = bpy.types.UILayout.bl_rna.functions["column"].parameters
    assert "heading" in {parameter.identifier for parameter in column_parameters}
    assert 0.0 < addon.REPORT_ENTRY_SPACING < 0.3
    assert len(addon._wrapped_text("This report text should wrap onto several separate lines.", width=18)) > 1
    warning_pixels = addon._status_icon_pixels("WARNING")
    ready_pixels = addon._status_icon_pixels("READY")
    opaque_warning = [warning_pixels[index:index + 4] for index in range(0, len(warning_pixels), 4) if warning_pixels[index + 3] > 0.9]
    opaque_ready = [ready_pixels[index:index + 4] for index in range(0, len(ready_pixels), 4) if ready_pixels[index + 3] > 0.9]
    assert any(red > 0.9 and green > 0.4 and blue < 0.1 for red, green, blue, _ in opaque_warning)
    assert any(green > red * 2 and green > blue * 2 for red, green, blue, _ in opaque_ready)
    icon_directory = os.path.join(bpy.app.tempdir or tempfile.gettempdir(), "mw_cs2_batch_exporter")
    for filename in (addon.WARNING_ICON_FILE, addon.READY_ICON_FILE):
        with open(os.path.join(icon_directory, filename), "rb") as icon_file:
            assert icon_file.read(8) == b"\x89PNG\r\n\x1a\n"
    original_warning_id = addon._WARNING_ICON_ID
    original_ready_id = addon._READY_ICON_ID
    addon._WARNING_ICON_ID = 2_147_483_647
    addon._READY_ICON_ID = 2_147_483_646
    assert addon._status_icon_options("WARNING") == {"icon": "STATUS_WARNING_FILLED"}
    assert addon._status_icon_options("PASS") == {"icon": "CHECKMARK"}
    assert addon._status_icon_options("ERROR") == {"icon": "STATUS_ERROR_FILLED"}
    addon._WARNING_ICON_ID = original_warning_id
    addon._READY_ICON_ID = original_ready_id
    assert addon._counted(0, "warning") == "0 warnings"
    assert addon._counted(1, "warning") == "1 warning"
    assert addon._counted(2, "warning") == "2 warnings"
    assert addon._counted(0, "error") == "0 errors"
    assert addon._counted(1, "error") == "1 error"
    assert addon._counted(2, "error") == "2 errors"
    tooltip = addon.CS2BATCH_OT_report_detail.description(
        None, SimpleNamespace(message="N-gons used", detail="Detailed explanation"),
    )
    assert tooltip == "Detailed explanation"
    material_tooltip = addon.CS2BATCH_OT_open_material_issue.description(
        None, SimpleNamespace(
            object_name="Object_LOD2", message="LOD2 has materials",
            detail="LOD2 meshes should have zero material slots.",
        ),
    )
    assert material_tooltip.startswith("Select 'Object_LOD2' and open Material Properties.")
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    bpy.ops.object.select_all(action="DESELECT")

    first = make_mesh_object("Object", x_offset=12.0, material_name="Shared_Building_Material")
    second = make_mesh_object("Object_LOD1", material_name="Shared_Building_Material")
    third = make_mesh_object("Object_LOD2", material_name=False)
    fourth = make_mesh_object("Object_Win", material_name=False)
    camera_data = bpy.data.cameras.new("HelperCamera_Data")
    camera = bpy.data.objects.new("HelperCamera", camera_data)
    bpy.context.collection.objects.link(camera)
    empty = bpy.data.objects.new("HelperEmpty", None)
    bpy.context.collection.objects.link(empty)
    for obj in (first, second, third, fourth, camera, empty):
        obj.select_set(True)
    bpy.context.view_layer.objects.active = second

    output_dir = tempfile.mkdtemp(prefix="mw_cs2_batch_exporter_")
    try:
        os.mkdir(os.path.join(output_dir, "Object"))  # Existing matching folder must be reused.
        settings = scene.cs2_batch_export_settings
        settings.export_directory = output_dir
        settings.overwrite_existing = False
        empty_source_issues = addon.collect_issues(bpy.context, [], "", check_existing=False)
        assert {issue.message for issue in empty_source_issues} == {"No mesh objects"}
        assert "Triangulate Faces remains disabled" in settings.bl_rna.properties["ignore_ngons"].description
        assert not settings.report_expanded
        empty_report_layout = FakeLayout()
        addon.CS2BATCH_PT_panel.draw(SimpleNamespace(layout=empty_report_layout), bpy.context)
        assert (
            "operator_enabled", "cs2_batch.export_selected", True
        ) in empty_report_layout.events
        empty_report_toggle = next(
            event[2] for event in empty_report_layout.events
            if event[:2] == ("prop_options", "report_expanded")
        )
        assert empty_report_toggle["icon"] == "TRIA_RIGHT"
        assert ("label", "No report generated") in empty_report_layout.events
        assert not any(
            event[:2] == ("operator", "cs2_batch.clear_report")
            for event in empty_report_layout.events
        )

        resolved, report_objects, source_issues, source_label = addon._resolve_source(
            bpy.context, settings, "SELECTION",
        )
        assert not source_issues
        assert source_label == "the selection"
        assert resolved == report_objects
        assert {obj.name for obj in resolved} == {"Object", "Object_LOD1", "Object_LOD2", "Object_Win"}
        assert all(obj.type == "MESH" for obj in report_objects)

        issues = addon.collect_issues(bpy.context, addon.selected_meshes(bpy.context), output_dir)
        assert not [issue for issue in issues if issue.severity == "ERROR"], issues
        assert not any("world origin" in issue.message or "does not match" in issue.message for issue in issues)

        assert bpy.ops.cs2_batch.check_selected(source="SELECTION") == {"FINISHED"}
        settings.export_directory = ""
        assert "No export folder" not in scene.cs2_batch_export_report
        assert "Invalid export path" not in scene.cs2_batch_export_report
        assert addon._report_summary(scene) == "4 objects checked · 0 errors · 0 warnings"
        settings.report_expanded = False
        missing_folder_layout = FakeLayout()
        addon.CS2BATCH_PT_panel.draw(SimpleNamespace(layout=missing_folder_layout), bpy.context)
        assert (
            "operator_enabled", "cs2_batch.export_selected", False
        ) in missing_folder_layout.events
        assert (
            "label", "4 objects checked · 0 errors · 0 warnings"
        ) in missing_folder_layout.events
        missing_folder_summary_style = next(
            event[2] for event in missing_folder_layout.events
            if event[:2] == ("label_options", "4 objects checked · 0 errors · 0 warnings")
        )
        assert all(
            missing_folder_summary_style.get(key) == value
            for key, value in addon._status_icon_options("PASS").items()
        )
        assert ("alert", True) not in missing_folder_layout.events
        report_without_folder = scene.cs2_batch_export_report
        assert_cancelled_error(
            lambda: bpy.ops.cs2_batch.export_selected(source="SELECTION"),
            "Choose a valid export folder.",
        )
        assert scene.cs2_batch_export_report == report_without_folder
        settings.export_directory = output_dir
        assert addon._report_summary(scene) == "4 objects checked · 0 errors · 0 warnings"
        restored_destination_layout = FakeLayout()
        addon.CS2BATCH_PT_panel.draw(
            SimpleNamespace(layout=restored_destination_layout), bpy.context,
        )
        assert (
            "operator_enabled", "cs2_batch.export_selected", True
        ) in restored_destination_layout.events

        result = bpy.ops.cs2_batch.export_selected()
        assert result == {"FINISHED"}, result
        assert settings.report_expanded
        expected = {"Object.fbx", "Object_LOD1.fbx", "Object_LOD2.fbx", "Object_Win.fbx"}
        assert os.listdir(output_dir) == ["Object"], os.listdir(output_dir)
        asset_dir = os.path.join(output_dir, "Object")
        assert set(os.listdir(asset_dir)) == expected, os.listdir(asset_dir)
        assert all(os.path.getsize(os.path.join(asset_dir, name)) > 100 for name in expected)
        assert set(bpy.context.selected_objects) == {first, second, third, fourth, camera, empty}
        assert bpy.context.view_layer.objects.active is second
        assert scene.cs2_batch_export_report.count("SECTION\t") == 4
        assert scene.cs2_batch_export_report.count("PASS\tReady to export") == 4
        assert addon._report_summary(scene) == "4 objects checked · 0 errors · 0 warnings"
        assert "SECTION\tObject_LOD1" in scene.cs2_batch_export_report
        assert len(scene.cs2_batch_export_report_groups) == 4
        assert len(scene.cs2_batch_export_report_rows) == 4
        assert all(row.severity == "PASS" for row in scene.cs2_batch_export_report_rows)
        assert "HelperCamera" not in scene.cs2_batch_export_report
        assert "HelperEmpty" not in scene.cs2_batch_export_report
        ready_layout = FakeLayout()
        addon.CS2BATCH_UL_report_rows.draw_item(
            SimpleNamespace(), bpy.context, ready_layout, scene,
            scene.cs2_batch_export_report_rows[0], 0,
            scene, "cs2_batch_export_report_index", 0,
        )
        assert ("label", "Object") in ready_layout.events
        assert ("label", "Ready") in ready_layout.events
        ready_style = next(
            event[2] for event in ready_layout.events
            if event[:2] == ("label_options", "Ready")
        )
        assert ready_style == addon._status_icon_options("PASS") | {"text": "Ready"}

        source_collection = bpy.data.collections.new("Batch Source")
        scene.collection.children.link(source_collection)
        for obj in (first, second, third, fourth, camera, empty):
            source_collection.objects.link(obj)
        settings.export_collection = source_collection
        settings.overwrite_existing = True
        bpy.ops.object.select_all(action="DESELECT")

        collection_check = bpy.ops.cs2_batch.check_selected(source="COLLECTION")
        assert collection_check == {"FINISHED"}, collection_check
        assert "from collection 'Batch Source'" in scene.cs2_batch_export_report
        settings.source_mode = "COLLECTION"
        settings.export_directory = ""
        assert "from collection 'Batch Source'" in scene.cs2_batch_export_report
        assert "No export folder" not in scene.cs2_batch_export_report
        assert addon._report_summary(scene) == "4 objects checked · 0 errors · 0 warnings"
        missing_collection_folder_layout = FakeLayout()
        addon.CS2BATCH_PT_panel.draw(
            SimpleNamespace(layout=missing_collection_folder_layout), bpy.context,
        )
        assert (
            "operator_enabled", "cs2_batch.export_selected", False
        ) in missing_collection_folder_layout.events
        collection_report_without_folder = scene.cs2_batch_export_report
        assert_cancelled_error(
            lambda: bpy.ops.cs2_batch.export_selected(source="COLLECTION"),
            "Choose a valid export folder.",
        )
        assert scene.cs2_batch_export_report == collection_report_without_folder
        settings.export_directory = output_dir
        assert addon._report_summary(scene) == "4 objects checked · 0 errors · 0 warnings"
        restored_collection_folder_layout = FakeLayout()
        addon.CS2BATCH_PT_panel.draw(
            SimpleNamespace(layout=restored_collection_folder_layout), bpy.context,
        )
        assert (
            "operator_enabled", "cs2_batch.export_selected", True
        ) in restored_collection_folder_layout.events
        collection_result = bpy.ops.cs2_batch.export_selected(source="COLLECTION")
        assert collection_result == {"FINISHED"}, collection_result
        assert not bpy.context.selected_objects
        assert set(os.listdir(asset_dir)) == expected
        assert scene.cs2_batch_export_report.count("SECTION\t") == 4
        assert "HelperCamera" not in scene.cs2_batch_export_report
        assert "HelperEmpty" not in scene.cs2_batch_export_report

        nested_collection = bpy.data.collections.new("Nested Source")
        source_collection.children.link(nested_collection)
        nested = make_mesh_object("NestedAsset", material_name="NestedAsset")
        nested_collection.objects.link(nested)
        second_collection = bpy.data.collections.new("Second Source")
        scene.collection.children.link(second_collection)
        second_collection.objects.link(first)  # Deliberate duplicate membership.
        second_asset = make_mesh_object("SecondAsset", material_name="SecondAsset")
        second_collection.objects.link(second_asset)

        settings.export_collection = source_collection
        assert bpy.ops.cs2_batch.add_collection() == {"FINISHED"}
        assert bpy.ops.cs2_batch.add_collection() == {"CANCELLED"}
        settings.export_collection = second_collection
        assert bpy.ops.cs2_batch.add_collection() == {"FINISHED"}
        assert [entry.collection for entry in settings.export_collections] == [source_collection, second_collection]
        settings.export_collection_index = 1
        assert bpy.ops.cs2_batch.remove_collection() == {"FINISHED"}
        assert [entry.collection for entry in settings.export_collections] == [source_collection]
        assert bpy.ops.cs2_batch.add_collection() == {"FINISHED"}

        resolved, report_objects, source_issues, source_label = addon._resolve_source(
            bpy.context, settings, "COLLECTION",
        )
        assert not source_issues
        assert source_label == "2 collections"
        assert [obj.name for obj in resolved] == [
            "NestedAsset", "Object", "Object_LOD1", "Object_LOD2", "Object_Win", "SecondAsset",
        ]
        assert len({obj.as_pointer() for obj in report_objects}) == 6
        assert all(obj.type == "MESH" for obj in report_objects)

        settings.overwrite_existing = True
        multi_check = bpy.ops.cs2_batch.check_selected(source="COLLECTION")
        assert multi_check == {"FINISHED"}
        assert "from 2 collections" in scene.cs2_batch_export_report
        assert len(scene.cs2_batch_export_report_groups) == 6
        assert "HelperCamera" not in scene.cs2_batch_export_report
        assert "HelperEmpty" not in scene.cs2_batch_export_report
        multi_export = bpy.ops.cs2_batch.export_selected(source="COLLECTION")
        assert multi_export == {"FINISHED"}
        assert os.path.exists(os.path.join(output_dir, "NestedAsset", "NestedAsset.fbx"))
        assert os.path.exists(os.path.join(output_dir, "SecondAsset", "SecondAsset.fbx"))
        assert len(scene.cs2_batch_export_report_groups) == 6

        settings.source_mode = "COLLECTION"
        collection_layout = FakeLayout()
        addon.CS2BATCH_PT_panel.draw(SimpleNamespace(layout=collection_layout), bpy.context)
        assert ("prop", "source_mode", True) in collection_layout.events
        assert ("prop", "ignore_ngons", False) in collection_layout.events
        assert ("template_list", "CS2BATCH_UL_collections", 2, 4) in collection_layout.events
        assert any(event[:2] == ("template_list", "CS2BATCH_UL_report_rows") for event in collection_layout.events)
        assert sum(
            event[:2] == ("operator", "cs2_batch.export_selected")
            for event in collection_layout.events
        ) == 1
        assert ("operator", "cs2_batch.export_selected", "Export FBX Files") in collection_layout.events
        collection_export_properties = next(
            event[2] for event in collection_layout.events
            if event[:2] == ("operator_properties", "cs2_batch.export_selected")
        )
        assert collection_export_properties.source == "COLLECTION"
        assert sum(
            event[:2] == ("operator", "cs2_batch.check_selected")
            for event in collection_layout.events
        ) == 1
        assert sum(
            event[:2] == ("operator", "cs2_batch.clear_report")
            for event in collection_layout.events
        ) == 1
        assert not any(event == ("label", "CS2 Preset") for event in collection_layout.events)

        settings.source_mode = "SELECTION"
        selection_layout = FakeLayout()
        addon.CS2BATCH_PT_panel.draw(SimpleNamespace(layout=selection_layout), bpy.context)
        assert not any(event[:2] == ("template_list", "CS2BATCH_UL_collections") for event in selection_layout.events)
        assert sum(
            event[:2] == ("operator", "cs2_batch.export_selected")
            for event in selection_layout.events
        ) == 1
        selection_export_properties = next(
            event[2] for event in selection_layout.events
            if event[:2] == ("operator_properties", "cs2_batch.export_selected")
        )
        assert selection_export_properties.source == "SELECTION"

        settings.overwrite_existing = False
        for obj in (first, second, third, fourth):
            obj.select_set(True)
        bpy.context.view_layer.objects.active = second

        existing_issues = addon.collect_issues(bpy.context, addon.selected_meshes(bpy.context), output_dir)
        assert sum(issue.message == "Existing FBX" for issue in existing_issues) == 4

        assert addon.main_asset_name("Object") == "Object"
        assert addon.main_asset_name("Object_LOD1") == "Object"
        assert addon.main_asset_name("Object_LOD2_Win") == "Object"
        assert addon.main_asset_name("Object_Win_LOD1") == "Object"
        assert addon._is_lod2("Object_LOD2")
        assert addon._is_lod2("Object_LOD2_Win")
        assert addon._is_lod2("Object_Win_LOD2")

        third.data.materials.append(bpy.data.materials["Shared_Building_Material"])
        lod2_issues = addon.collect_issues(bpy.context, [third], output_dir, check_existing=False)
        assert any(issue.message == "LOD2 has materials" and issue.detail for issue in lod2_issues)
        addon._store_report(scene, lod2_issues, "Material navigation test", [third])
        material_row = next(
            row for row in scene.cs2_batch_export_report_rows
            if row.kind == "ISSUE" and row.message == "LOD2 has materials"
        )
        assert material_row.action == "MATERIAL"
        material_layout = FakeLayout()
        addon.CS2BATCH_UL_report_rows.draw_item(
            SimpleNamespace(), bpy.context, material_layout, scene,
            material_row, 0, scene, "cs2_batch_export_report_index", 1,
        )
        assert ("operator", "cs2_batch.open_material_issue", "Warning · LOD2 has materials") in material_layout.events
        assert ("alert", True) not in material_layout.events
        assert any(
            event[0] == "label_options" and all(
                event[2].get(key) == value for key, value in addon._status_icon_options("WARNING").items()
            )
            for event in material_layout.events
        )
        material_button_style = next(
            event[3] for event in material_layout.events
            if event[:3] == ("operator_options", "cs2_batch.open_material_issue", "Warning · LOD2 has materials")
        )
        assert material_button_style["icon"] == "MATERIAL"
        assert material_button_style["emboss"] is True
        material_operator = next(
            event[2] for event in material_layout.events
            if event[:2] == ("operator_properties", "cs2_batch.open_material_issue")
        )
        assert material_operator.object_name == third.name
        assert material_operator.detail

        bpy.ops.object.select_all(action="DESELECT")
        first.select_set(True)
        bpy.context.view_layer.objects.active = first
        open_material_result = bpy.ops.cs2_batch.open_material_issue(
            object_name=third.name,
            message="LOD2 has materials",
            detail="LOD2 meshes should have zero material slots.",
        )
        assert open_material_result == {"FINISHED"}
        assert set(bpy.context.selected_objects) == {third}
        assert bpy.context.view_layer.objects.active is third

        redraw_calls = []
        fake_space = SimpleNamespace(context="OBJECT")
        fake_area = SimpleNamespace(
            type="PROPERTIES", spaces=SimpleNamespace(active=fake_space),
            tag_redraw=lambda: redraw_calls.append(True),
        )
        fake_material_context = SimpleNamespace(
            window_manager=SimpleNamespace(
                windows=[SimpleNamespace(screen=SimpleNamespace(areas=[fake_area]))],
            ),
        )
        assert addon._open_material_properties(fake_material_context)
        assert fake_space.context == "MATERIAL"
        assert redraw_calls == [True]
        assert not addon._open_material_properties(
            SimpleNamespace(window_manager=SimpleNamespace(windows=[])),
        )
        third.data.materials.clear()

        bpy.ops.object.select_all(action="DESELECT")
        for obj in (first, second, third, fourth):
            obj.select_set(True)
        bpy.context.view_layer.objects.active = second

        first.data.materials.append(bpy.data.materials.new("Second_Material"))
        material_issues = addon.collect_issues(bpy.context, [first], output_dir, check_existing=False)
        assert any(issue.message == "Multiple materials" and issue.detail for issue in material_issues)
        first.data.materials.pop(index=1)

        ngon_mesh = bpy.data.meshes.new("Ngon_Mesh")
        ngon_mesh.from_pydata(
            [(0, 0, 0), (1, 0, 0), (1.5, 0.5, 0), (0.5, 1.5, 0), (-0.5, 0.5, 0)],
            [], [(0, 1, 2, 3, 4)],
        )
        ngon_mesh.uv_layers.new(name="UVMap")
        ngon = bpy.data.objects.new("Ngon", ngon_mesh)
        bpy.context.collection.objects.link(ngon)
        ngon.data.materials.append(bpy.data.materials.new("Ngon_Material"))
        ngon_issues = addon.collect_issues(bpy.context, [ngon], output_dir, check_existing=False)
        assert any(issue.message == "N-gons used" and issue.detail for issue in ngon_issues)
        ignored_ngon_issues = addon.collect_issues(
            bpy.context, [ngon], output_dir, check_existing=False, ignore_ngons=True,
        )
        assert not any(issue.message == "N-gons used" for issue in ignored_ngon_issues)
        addon._store_report(scene, ngon_issues, "Checked 1 mesh object", [ngon])
        assert settings.report_expanded
        assert "SUMMARY\t0 errors, 1 warning" in scene.cs2_batch_export_report
        assert addon._report_summary(scene) == "1 object checked · 0 errors · 1 warning"
        assert "SECTION\tNgon" in scene.cs2_batch_export_report
        assert "WARNING\tN-gons used\tFaces with more than four vertices" in scene.cs2_batch_export_report
        assert [(row.kind, row.object_name, row.count_text, row.message) for row in scene.cs2_batch_export_report_rows] == [
            ("HEADER", "Ngon", "1 warning", ""),
            ("ISSUE", "Ngon", "", "N-gons used"),
        ]
        layout = FakeLayout()
        addon.CS2BATCH_PT_panel.draw(SimpleNamespace(layout=layout), bpy.context)
        assert ("template_list", "CS2BATCH_UL_report_rows", 4, 12) in layout.events

        header_layout = FakeLayout()
        addon.CS2BATCH_UL_report_rows.draw_item(
            SimpleNamespace(), bpy.context, header_layout, scene,
            scene.cs2_batch_export_report_rows[0], 0,
            scene, "cs2_batch_export_report_index", 0,
        )
        assert ("label", "Ngon") in header_layout.events
        assert ("label", "1 warning") in header_layout.events
        warning_count_style = next(
            event[2] for event in header_layout.events
            if event[:2] == ("label_options", "1 warning")
        )
        assert all(
            warning_count_style.get(key) == value
            for key, value in addon._status_icon_options("WARNING").items()
        )
        issue_layout = FakeLayout()
        addon.CS2BATCH_UL_report_rows.draw_item(
            SimpleNamespace(), bpy.context, issue_layout, scene,
            scene.cs2_batch_export_report_rows[1], 0,
            scene, "cs2_batch_export_report_index", 1,
        )
        assert ("label", "Warning · N-gons used") in issue_layout.events
        assert ("alert", True) not in issue_layout.events
        assert any(
            event[0] == "label_options" and all(
                event[2].get(key) == value for key, value in addon._status_icon_options("WARNING").items()
            )
            for event in issue_layout.events
        )
        assert ("operator", "cs2_batch.report_detail", "") in issue_layout.events
        detail_style = next(
            event[3] for event in issue_layout.events
            if event[:3] == ("operator_options", "cs2_batch.report_detail", "")
        )
        assert detail_style["icon"] == "INFO"
        assert not any(
            event[0] in {"label_options", "operator_options"}
            and event[-1].get("icon") == "QUESTION"
            for event in issue_layout.events
        )
        assert not any(
            event[:2] == ("operator", "cs2_batch.open_material_issue")
            for event in issue_layout.events
        )
        error_layout = FakeLayout()
        addon.CS2BATCH_UL_report_rows.draw_item(
            SimpleNamespace(), bpy.context, error_layout, scene,
            SimpleNamespace(
                kind="ISSUE", severity="ERROR", action="", message="Scale not applied",
                detail="Apply scale.", object_name="ErrorObject",
            ),
            0, scene, "cs2_batch_export_report_index", 0,
        )
        assert any(
            event[0] == "label_options" and event[2].get("icon") == "STATUS_ERROR_FILLED"
            for event in error_layout.events
        )
        assert ("alert", True) in error_layout.events
        assert ("label", "Error · Scale not applied") in error_layout.events

        addon._store_report(
            scene,
            [addon.Issue("ERROR", "ErrorObject", "Scale not applied", "Apply scale.")],
            "Error colour test", ["ErrorObject"],
        )
        assert "SUMMARY\t1 error, 0 warnings" in scene.cs2_batch_export_report
        error_header = scene.cs2_batch_export_report_rows[0]
        assert error_header.kind == "HEADER" and error_header.severity == "ERROR"
        error_header_layout = FakeLayout()
        addon.CS2BATCH_UL_report_rows.draw_item(
            SimpleNamespace(), bpy.context, error_header_layout, scene,
            error_header, 0, scene, "cs2_batch_export_report_index", 0,
        )
        error_count_style = next(
            event[2] for event in error_header_layout.events
            if event[:2] == ("label_options", "1 error")
        )
        assert error_count_style["icon"] == "STATUS_ERROR_FILLED"
        settings.report_expanded = False
        error_summary_layout = FakeLayout()
        addon.CS2BATCH_PT_panel.draw(SimpleNamespace(layout=error_summary_layout), bpy.context)
        error_summary_style = next(
            event[2] for event in error_summary_layout.events
            if event[:2] == ("label_options", "1 object checked · 1 error · 0 warnings")
        )
        assert error_summary_style["icon"] == "STATUS_ERROR_FILLED"
        assert ("alert", True) in error_summary_layout.events

        bpy.ops.object.select_all(action="DESELECT")
        ngon.select_set(True)
        bpy.context.view_layer.objects.active = ngon
        settings.overwrite_existing = True
        settings.stop_on_warnings = True
        settings.ignore_ngons = True
        assert bpy.ops.cs2_batch.check_selected(source="SELECTION") == {"FINISHED"}
        assert addon._report_summary(scene) == "1 object checked · 0 errors · 0 warnings"
        assert "N-gons used" not in scene.cs2_batch_export_report
        assert bpy.ops.cs2_batch.export_selected(source="SELECTION") == {"FINISHED"}
        assert os.path.exists(os.path.join(output_dir, "Ngon", "Ngon.fbx"))

        settings.ignore_ngons = False
        assert bpy.ops.cs2_batch.check_selected(source="SELECTION") == {"FINISHED"}
        assert addon._report_summary(scene) == "1 object checked · 0 errors · 1 warning"
        assert "N-gons used" in scene.cs2_batch_export_report
        try:
            blocked_export = bpy.ops.cs2_batch.export_selected(source="SELECTION")
        except RuntimeError as exc:
            assert "Export stopped" in str(exc)
        else:
            assert blocked_export == {"CANCELLED"}
        settings.stop_on_warnings = False

        count_names = ["CountOne", "CountTwo"]
        count_issues = [
            addon.Issue("WARNING", "CountOne", "No UV map", "CountOne detail"),
            addon.Issue("WARNING", "CountTwo", "No UV map", "CountTwo UV detail"),
            addon.Issue("WARNING", "CountTwo", "Multiple materials", "CountTwo material detail"),
        ]
        addon._store_report(scene, count_issues, "Count test", count_names)
        assert [(row.kind, row.object_name, row.count_text, row.message) for row in scene.cs2_batch_export_report_rows] == [
            ("HEADER", "CountOne", "1 warning", ""),
            ("ISSUE", "CountOne", "", "No UV map"),
            ("HEADER", "CountTwo", "2 warnings", ""),
            ("ISSUE", "CountTwo", "", "No UV map"),
            ("ISSUE", "CountTwo", "", "Multiple materials"),
        ]

        many_names = [f"ReportObject_{index:02d}" for index in range(30)]
        many_objects = []
        for name in many_names:
            obj = bpy.data.objects.new(name, ngon_mesh)
            bpy.context.collection.objects.link(obj)
            many_objects.append(obj)
        bpy.ops.object.select_all(action="DESELECT")
        for obj in many_objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = many_objects[0]
        settings.ignore_ngons = False
        assert bpy.ops.cs2_batch.check_selected(source="SELECTION") == {"FINISHED"}
        assert addon._report_summary(scene) == "30 objects checked · 0 errors · 30 warnings"
        assert len(scene.cs2_batch_export_report_groups) == 30
        assert len(scene.cs2_batch_export_report_rows) == 60
        scene.cs2_batch_export_report_index = 34
        report_text_before_collapse = scene.cs2_batch_export_report
        selection_before_collapse = set(bpy.context.selected_objects)
        settings.report_expanded = False
        collapsed_layout = FakeLayout()
        addon.CS2BATCH_PT_panel.draw(SimpleNamespace(layout=collapsed_layout), bpy.context)
        collapsed_toggle = next(
            event[2] for event in collapsed_layout.events
            if event[:2] == ("prop_options", "report_expanded")
        )
        assert collapsed_toggle["icon"] == "TRIA_RIGHT"
        assert ("label", "30 objects checked · 0 errors · 30 warnings") in collapsed_layout.events
        collapsed_summary_style = next(
            event[2] for event in collapsed_layout.events
            if event[:2] == ("label_options", "30 objects checked · 0 errors · 30 warnings")
        )
        assert all(
            collapsed_summary_style.get(key) == value
            for key, value in addon._status_icon_options("WARNING").items()
        )
        assert ("alert", True) not in collapsed_layout.events
        assert not any(event[:2] == ("template_list", "CS2BATCH_UL_report_rows") for event in collapsed_layout.events)
        assert not any(event[:2] == ("operator", "cs2_batch.clear_report") for event in collapsed_layout.events)
        assert scene.cs2_batch_export_report == report_text_before_collapse
        assert len(scene.cs2_batch_export_report_groups) == 30
        assert len(scene.cs2_batch_export_report_rows) == 60
        assert scene.cs2_batch_export_report_index == 34
        assert set(bpy.context.selected_objects) == selection_before_collapse

        settings.report_expanded = True
        long_layout = FakeLayout()
        addon.CS2BATCH_PT_panel.draw(SimpleNamespace(layout=long_layout), bpy.context)
        expanded_toggle = next(
            event[2] for event in long_layout.events
            if event[:2] == ("prop_options", "report_expanded")
        )
        assert expanded_toggle["icon"] == "TRIA_DOWN"
        assert ("template_list", "CS2BATCH_UL_report_rows", 12, 12) in long_layout.events
        expanded_summary_style = next(
            event[2] for event in long_layout.events
            if event[:2] == ("label_options", "0 errors, 30 warnings")
        )
        assert all(
            expanded_summary_style.get(key) == value
            for key, value in addon._status_icon_options("WARNING").items()
        )
        assert ("alert", True) not in long_layout.events
        assert sum(
            event[:2] == ("operator", "cs2_batch.clear_report")
            for event in long_layout.events
        ) == 1
        assert scene.cs2_batch_export_report_rows[34].kind == "HEADER"
        assert scene.cs2_batch_export_report_rows[34].object_name == "ReportObject_17"
        assert scene.cs2_batch_export_report_rows[35].kind == "ISSUE"
        assert scene.cs2_batch_export_report_rows[35].object_name == "ReportObject_17"

        list_layout = FakeLayout()
        addon.CS2BATCH_UL_report_rows.draw_item(
            SimpleNamespace(),
            bpy.context, list_layout, scene,
            scene.cs2_batch_export_report_rows[34], 0,
            scene, "cs2_batch_export_report_index", 34,
        )
        assert ("label", "ReportObject_17") in list_layout.events
        assert ("label", "1 warning") in list_layout.events

        settings.ignore_ngons = True
        assert bpy.ops.cs2_batch.check_selected(source="SELECTION") == {"FINISHED"}
        assert addon._report_summary(scene) == "30 objects checked · 0 errors · 0 warnings"
        assert "N-gons used" not in scene.cs2_batch_export_report
        assert len(scene.cs2_batch_export_report_groups) == 30
        assert len(scene.cs2_batch_export_report_rows) == 30
        settings.report_expanded = False
        ignored_long_layout = FakeLayout()
        addon.CS2BATCH_PT_panel.draw(SimpleNamespace(layout=ignored_long_layout), bpy.context)
        assert ("label", "30 objects checked · 0 errors · 0 warnings") in ignored_long_layout.events
        ignored_summary_style = next(
            event[2] for event in ignored_long_layout.events
            if event[:2] == ("label_options", "30 objects checked · 0 errors · 0 warnings")
        )
        assert all(
            ignored_summary_style.get(key) == value
            for key, value in addon._status_icon_options("PASS").items()
        )
        assert ("alert", True) not in ignored_long_layout.events
        assert all(len(poly.vertices) == 5 for poly in ngon_mesh.polygons)
        settings.ignore_ngons = False

        bpy.ops.object.select_all(action="DESELECT")
        for obj in (first, second):
            obj.select_set(True)
        bpy.context.view_layer.objects.active = second

        first.scale.x = 2.0
        transform_issues = addon.collect_issues(bpy.context, [first], "", check_existing=False)
        assert any(issue.severity == "ERROR" and issue.message == "Scale not applied" for issue in transform_issues)

        addon._store_report(scene, ngon_issues, "Temporary report", [ngon])
        settings.export_directory = output_dir
        settings.export_collection = second_collection
        settings.overwrite_existing = True
        settings.stop_on_warnings = True
        for obj in (first, second):
            obj.select_set(True)
        selection_before_clear_report = set(bpy.context.selected_objects)
        assert addon.CS2BATCH_OT_clear_report.poll(bpy.context)
        clear_report_result = bpy.ops.cs2_batch.clear_report()
        assert clear_report_result == {"FINISHED"}, clear_report_result
        assert scene.cs2_batch_export_report == ""
        assert not scene.cs2_batch_export_report_groups
        assert not scene.cs2_batch_export_report_rows
        assert not settings.report_expanded
        assert settings.export_directory == output_dir
        assert settings.export_collection is second_collection
        assert len(settings.export_collections) == 2
        assert settings.overwrite_existing and settings.stop_on_warnings
        assert set(bpy.context.selected_objects) == selection_before_clear_report
        assert not addon.CS2BATCH_OT_clear_report.poll(bpy.context)
        no_report_layout = FakeLayout()
        addon.CS2BATCH_PT_panel.draw(SimpleNamespace(layout=no_report_layout), bpy.context)
        assert not any(
            event[:2] == ("operator", "cs2_batch.clear_report")
            for event in no_report_layout.events
        )

        addon._store_report(scene, ngon_issues, "Preserved report", [ngon])
        preserved_report = scene.cs2_batch_export_report
        preserved_rows = len(scene.cs2_batch_export_report_rows)
        assert addon.CS2BATCH_OT_clear_export_selection.poll(bpy.context)
        clear_selection_result = bpy.ops.cs2_batch.clear_export_selection()
        assert clear_selection_result == {"FINISHED"}, clear_selection_result
        assert not bpy.context.selected_objects
        assert settings.export_collection is None
        assert not settings.export_collections
        assert settings.export_directory == output_dir
        assert settings.overwrite_existing and settings.stop_on_warnings
        assert settings.source_mode == "SELECTION"
        assert scene.cs2_batch_export_report == preserved_report
        assert len(scene.cs2_batch_export_report_rows) == preserved_rows

        print("MW_CS2_BATCH_EXPORTER_TEST_OK")
    finally:
        shutil.rmtree(output_dir)
        addon.unregister()


main()
