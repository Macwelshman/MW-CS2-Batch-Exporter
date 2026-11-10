"""Run the real exporter and Blender importer on a complete reference asset."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import json
import runpy
import subprocess

import bpy

fixture = runpy.run_path(str(Path(__file__).with_name("reference_scene.py")))
ASSET, ROLES = fixture["ASSET"], fixture["ROLES"]
POSITION_EPS = 1e-4  # metres
UV_EPS = 1e-5


def snapshot(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    points = [obj.matrix_world @ vertex.co for vertex in mesh.vertices]
    bounds = tuple(max(p[i] for p in points) - min(p[i] for p in points) for i in range(3))
    uv = mesh.uv_layers.active
    assert uv is not None, obj.name
    triangles = []
    for tri in mesh.loop_triangles:
        material = obj.material_slots[tri.material_index].material.name if obj.material_slots else None
        triangles.append((tuple(tri.vertices), tuple(uv.data[i].uv.copy() for i in tri.loops), material))
    return points, bounds, triangles, tuple(slot.material.name for slot in obj.material_slots)


def face_map(triangles, indices):
    result = {}
    for vertices, uvs, material in triangles:
        mapped = tuple(indices[i] for i in vertices)
        start = mapped.index(min(mapped))
        # Rotate the starting corner but preserve winding.
        key = mapped[start:] + mapped[:start]
        assert key not in result, key
        result[key] = (uvs[start:] + uvs[:start], material)
    return result


def compare(name, expected, actual):
    points, bounds, triangles, slots = expected
    other, other_bounds, other_triangles, other_slots = actual
    assert len(points) == len(other), (name, "vertex count")
    assert len(triangles) == len(other_triangles), (name, "triangle count")
    assert all(abs(a - b) <= POSITION_EPS for a, b in zip(bounds, other_bounds)), (name, "dimensions")
    assert slots == other_slots, (name, "material slots", slots, other_slots)
    indices = []
    for point in other:
        matches = [i for i, source in enumerate(points) if (source - point).length <= POSITION_EPS]
        assert len(matches) == 1, (name, "world position/orientation", point)
        indices.append(matches[0])
    assert len(set(indices)) == len(points), (name, "vertex correspondence")
    source_faces = face_map(triangles, range(len(points)))
    imported_faces = face_map(other_triangles, indices)
    assert source_faces.keys() == imported_faces.keys(), (name, "topology/winding")
    for key, (uvs, material) in source_faces.items():
        actual_uvs, actual_material = imported_faces[key]
        assert material == actual_material, (name, key, "face material")
        assert all((a - b).length <= UV_EPS for a, b in zip(uvs, actual_uvs)), (name, key, "corner UV")


def remove_objects(scene):
    for obj in list(scene.objects):
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if isinstance(mesh, bpy.types.Mesh) and not mesh.users:
            bpy.data.meshes.remove(mesh)


def check_settings_generator(scanner, root, paths, expected):
    scan = json.loads(subprocess.check_output([scanner, str(root)], text=True, timeout=10))
    assert len(scan["assets"]) == 1, [(asset["name"], asset["folder"]) for asset in scan["assets"]]
    asset, = scan["assets"]
    assert asset["name"] == ASSET and Path(asset["folder"]).resolve() == (root / ASSET).resolve()
    by_path = {Path(file["path"]).resolve(): file for file in asset["files"]}
    assert set(by_path) == {path.resolve() for path in paths}
    for path, suffix in paths.items():
        file = by_path[path.resolve()]
        role, _ = ROLES[suffix]
        assert file["kind"] == role[0].lower() + role[1:], file
        assert file["parseError"] is None and file["meshNames"] == [path.stem], file
        assert file["materialNames"] == list(expected[suffix][3]), file
    mesh_issues = {"orphanFbxVariant", "multipleMainMeshes", "lod1Missing", "lod2WithoutLod1",
                   "lodVariantWithoutMesh", "duplicateFbxRole", "fbxMaterialSlotCount",
                   "meshNameMismatch", "fbxParseFailed"}
    assert not [issue for issue in scan["globalIssues"] + asset["issues"]
                if issue["code"] in mesh_issues]
    print("MW_CS2_SETTINGS_REFERENCE_SCAN_OK")


def run(addon, scanner=None):
    window = bpy.context.window
    previous = window.scene
    scene = bpy.data.scenes.new("CS2 Reference")
    window.scene = scene
    material = collection = None
    try:
        objects, material, collection = fixture["build"](scene)
        settings = scene.cs2_batch_export_settings
        settings.stop_on_warnings = True
        settings.export_collection = collection
        for obj in objects.values():
            obj.select_set(True)
        bpy.context.view_layer.objects.active = objects[""]
        bpy.context.view_layer.update()
        expected = {suffix: snapshot(obj) for suffix, obj in objects.items()}
        assert [len(expected[s][2]) for s in ("", "_LOD1", "_LOD2")] == [16, 14, 12]

        with TemporaryDirectory(prefix="mw-cs2-reference-") as directory:
            root = Path(directory)
            settings.export_directory = directory
            try:
                result = bpy.ops.cs2_batch.export_selected(source="COLLECTION")
            except RuntimeError as exc:
                raise AssertionError(scene.cs2_batch_export_report) from exc
            assert result == {"FINISHED"}, scene.cs2_batch_export_report
            count = len(ROLES)
            assert f"{count} exported, {count} verified, 0 skipped, 0 failed" in scene.cs2_batch_export_report
            assert set(bpy.context.selected_objects) == set(objects.values())
            assert bpy.context.view_layer.objects.active == objects[""]
            for suffix, obj in objects.items():
                compare(obj.name, expected[suffix], snapshot(obj))

            paths = {root / ASSET / f"{ASSET}{suffix}.fbx": suffix for suffix in ROLES}
            assert set(root.rglob("*.fbx")) == set(paths), "Wrong asset grouping or filenames"
            assert not list(root.glob(".mw-cs2-stage-*"))
            if scanner:
                check_settings_generator(scanner, root, paths, expected)
            files = {path: path.read_bytes() for path in paths}
            # Call execute directly so expected ERROR reports don't raise via bpy.ops.
            op = SimpleNamespace(source="COLLECTION", report=lambda *args: None)
            assert addon.CS2BATCH_OT_export.execute(op, bpy.context) == {"CANCELLED"}
            assert f"0 exported, 0 verified, {count} skipped, 0 failed" in scene.cs2_batch_export_report
            settings.overwrite_existing = True
            validate = addon._validate_staged_fbx
            calls = []
            def reject_second(path):
                calls.append(path)
                if len(calls) == 2:
                    raise ValueError("Injected invalid staged FBX")
                validate(path)

            with patch.object(addon, "_validate_staged_fbx", reject_second):
                assert addon.CS2BATCH_OT_export.execute(op, bpy.context) == {"CANCELLED"}
            report = scene.cs2_batch_export_report
            assert f"0 exported, 1 verified, {count - 1} skipped, 1 failed" in report
            failed = sorted((obj.name for obj in objects.values()), key=str.casefold)[1]
            assert f"{failed}.fbx" in report and "Injected invalid staged FBX" in report
            assert any(row.object_name == failed for row in scene.cs2_batch_export_report_rows)
            assert all(path.read_bytes() == data for path, data in files.items())
            assert not list(root.glob(".mw-cs2-stage-*"))

            replace = addon.os.replace
            failed_destination = root / ASSET / f"{failed}.fbx"

            def reject_publish(source, destination):
                if Path(destination) == failed_destination and Path(source).suffix == ".fbx":
                    raise PermissionError("Injected publication failure")
                return replace(source, destination)

            with patch.object(addon.os, "replace", reject_publish):
                assert addon.CS2BATCH_OT_export.execute(op, bpy.context) == {"CANCELLED"}
            report = scene.cs2_batch_export_report
            assert f"0 exported, {count} verified, {count - 1} skipped, 1 failed" in report
            assert "destination files restored" in report
            assert any(row.object_name == failed and row.severity == "ERROR"
                       for row in scene.cs2_batch_export_report_rows)
            assert all(path.read_bytes() == data for path, data in files.items())
            assert not list(root.glob(".mw-cs2-stage-*"))
            assert set(bpy.context.selected_objects) == set(objects.values())
            assert bpy.context.view_layer.objects.active == objects[""]

            # Free source names before import so Blender cannot mask a name
            # mismatch with its automatic name disambiguation.
            remove_objects(scene)
            bpy.data.materials.remove(material)
            material = None
            for path, suffix in paths.items():
                before_materials = set(bpy.data.materials)
                assert bpy.ops.import_scene.fbx(filepath=str(path), use_custom_normals=True) == {"FINISHED"}
                bpy.context.view_layer.update()
                imported, = scene.objects
                role, slots = ROLES[suffix]
                assert imported.type == "MESH" and imported.name == path.stem, (role, imported.name)
                assert imported.parent is None and len(imported.material_slots) == slots, role
                compare(path.stem, expected[suffix], snapshot(imported))
                remove_objects(scene)
                for imported_material in set(bpy.data.materials) - before_materials:
                    bpy.data.materials.remove(imported_material)
    finally:
        remove_objects(scene)
        window.scene = previous
        bpy.data.scenes.remove(scene)
        if collection is not None:
            bpy.data.collections.remove(collection)
        if material is not None:
            bpy.data.materials.remove(material)
