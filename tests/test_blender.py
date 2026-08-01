import os
import shutil
import sys
import tempfile

import bpy


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import mw_cs2_batch_exporter as addon


def make_mesh_object(name, x_offset=0.0):
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(
        [(-0.5, -0.5, 0.0), (0.5, -0.5, 0.0), (0.5, 0.5, 0.0), (-0.5, 0.5, 0.0)],
        [],
        [(0, 1, 2, 3)],
    )
    mesh.uv_layers.new(name="UVMap")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    material = bpy.data.materials.new(name)
    obj.data.materials.append(material)
    obj.location.x = x_offset
    return obj


def main():
    addon.register()
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    bpy.ops.object.select_all(action="DESELECT")

    first = make_mesh_object("Object")
    second = make_mesh_object("Object_LOD1")
    third = make_mesh_object("Object_LOD2")
    fourth = make_mesh_object("Object_Win")
    for obj in (first, second, third, fourth):
        obj.select_set(True)
    bpy.context.view_layer.objects.active = second

    output_dir = tempfile.mkdtemp(prefix="mw_cs2_batch_exporter_")
    try:
        os.mkdir(os.path.join(output_dir, "Object"))  # Existing matching folder must be reused.
        settings = scene.cs2_batch_export_settings
        settings.export_directory = output_dir
        settings.overwrite_existing = False

        issues = addon.collect_issues(bpy.context, addon.selected_meshes(bpy.context), output_dir)
        assert not [issue for issue in issues if issue.severity == "ERROR"], issues

        result = bpy.ops.cs2_batch.export_selected()
        assert result == {"FINISHED"}, result
        expected = {"Object.fbx", "Object_LOD1.fbx", "Object_LOD2.fbx", "Object_Win.fbx"}
        assert os.listdir(output_dir) == ["Object"], os.listdir(output_dir)
        asset_dir = os.path.join(output_dir, "Object")
        assert set(os.listdir(asset_dir)) == expected, os.listdir(asset_dir)
        assert all(os.path.getsize(os.path.join(asset_dir, name)) > 100 for name in expected)
        assert set(bpy.context.selected_objects) == {first, second, third, fourth}
        assert bpy.context.view_layer.objects.active is second

        existing_issues = addon.collect_issues(bpy.context, addon.selected_meshes(bpy.context), output_dir)
        assert sum("already exists" in issue.message for issue in existing_issues) == 4

        assert addon.main_asset_name("Object") == "Object"
        assert addon.main_asset_name("Object_LOD1") == "Object"
        assert addon.main_asset_name("Object_LOD2_Win") == "Object"
        assert addon.main_asset_name("Object_Win_LOD1") == "Object"

        first.scale.x = 2.0
        transform_issues = addon.collect_issues(bpy.context, [first], "", check_existing=False)
        assert any(issue.severity == "ERROR" and "Scale is not applied" in issue.message for issue in transform_issues)

        print("MW_CS2_BATCH_EXPORTER_TEST_OK")
    finally:
        shutil.rmtree(output_dir)
        addon.unregister()


main()
