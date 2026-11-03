"""Focused static-mesh regression; callable in an isolated scene via Flue."""
import math
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Matrix


def run(addon):
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1
    objects = []
    for name in ('Reliability', 'Reliability_LOD2', 'Reliability_Win', 'Reliability_Wif', 'Reliability_Wio'):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([(0, 0, 0), (2, 0, 0), (0, 3, 0), (0, 0, 5)], [],
                         [(0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)])
        mesh.uv_layers.new()
        for loop in mesh.uv_layers.active.data:
            loop.uv = (0.2, 0.7)
        obj = bpy.data.objects.new(name, mesh)
        scene.collection.objects.link(obj)
        objects.append(obj)
    obj = objects[0]
    checks = 0
    for mode in ('XYZ', 'ZYX', 'QUATERNION', 'AXIS_ANGLE'):
        obj.rotation_mode = mode
        for angle, expected in ((0, True), (2 * math.pi, True), (1e-7, True), (0.2, False)):
            if mode == 'QUATERNION':
                obj.rotation_quaternion = (math.cos(angle/2), 0, 0, math.sin(angle/2))
            elif mode == 'AXIS_ANGLE':
                obj.rotation_axis_angle = (angle, 0, 0, 1)
            else:
                obj.rotation_euler = (0, 0, angle)
            assert addon._rotation_is_identity(obj) == expected, (mode, angle)
            checks += 1
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = (-1, 0, 0, 0)
    assert addon._rotation_is_identity(obj)
    obj.rotation_euler = (0.5, 0, 0)  # inactive values must be ignored
    assert addon._rotation_is_identity(obj)
    obj.delta_rotation_quaternion = (math.cos(0.15), 0, 0, math.sin(0.15))
    assert not addon._rotation_is_identity(obj)
    obj.delta_rotation_quaternion = (1, 0, 0, 0)
    context = SimpleNamespace(scene=SimpleNamespace(
        unit_settings=scene.unit_settings,
        cs2_batch_export_settings=SimpleNamespace(decals=[])), view_layer=bpy.context.view_layer)
    obj.scale = (-1, 1, 1)
    issues = addon.collect_issues(context, [obj], '')
    assert {'Negative scale', 'Scale not applied'} <= {issue.message for issue in issues}
    obj.scale = (1, 1, 1)
    # Applied reflection lives in the mesh; restore winding to retain outward normals.
    obj.data.transform(Matrix.Diagonal((-1, 1, 1, 1)))
    for polygon in obj.data.polygons:
        polygon.flip()
    assert addon._rotation_is_identity(obj)
    results = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for bake in (True, False):
            for source in objects:
                bpy.ops.object.select_all(action='DESELECT')
                source.select_set(True)
                bpy.context.view_layer.objects.active = source
                path = root / f'{source.name}-{bake}.fbx'
                preset = dict(addon.FBX_EXPORT_SETTINGS, bake_space_transform=bake)
                assert bpy.ops.export_scene.fbx(filepath=str(path), **preset) == {'FINISHED'}
                addon._validate_staged_fbx(path)
                before = set(scene.objects)
                assert bpy.ops.import_scene.fbx(filepath=str(path), use_custom_normals=True) == {'FINISHED'}
                imported = (set(scene.objects) - before).pop()
                original_points = sorted(tuple(round(v, 4) for v in source.matrix_world @ vertex.co) for vertex in source.data.vertices)
                imported_points = sorted(tuple(round(v, 4) for v in imported.matrix_world @ vertex.co) for vertex in imported.data.vertices)
                assert original_points == imported_points, (source.name, bake, original_points, imported_points)
                # Local bounding boxes differ when conversion is held on the
                # imported object. Compare world-space extents instead.
                for axis in range(3):
                    assert abs((max(p[axis] for p in original_points)-min(p[axis] for p in original_points)) - (max(p[axis] for p in imported_points)-min(p[axis] for p in imported_points))) < 1e-4
                assert len(source.data.polygons) == len(imported.data.polygons)
                assert len(source.data.uv_layers.active.data) == len(imported.data.uv_layers.active.data)
                assert all((a.uv-b.uv).length < 1e-5 for a,b in zip(source.data.uv_layers.active.data, imported.data.uv_layers.active.data))
                normal_matrix = imported.matrix_world.to_3x3().inverted().transposed()
                for a,b in zip(source.data.polygons, imported.data.polygons):
                    assert a.normal.dot((normal_matrix @ b.normal).normalized()) > 0.9999
                results.append((source.name, bake, tuple(round(v, 4) for v in imported.rotation_euler)))
                bpy.data.objects.remove(imported, do_unlink=True)
        # Exercise the actual operator staging path without touching registered
        # add-on settings or report properties in the user's working scene.
        settings = SimpleNamespace(export_directory=str(root), stop_on_warnings=False,
                                   overwrite_existing=True)
        fake_context = SimpleNamespace(scene=SimpleNamespace(cs2_batch_export_settings=settings),
                                       view_layer=bpy.context.view_layer,
                                       selected_objects=list(bpy.context.selected_objects))
        operator = SimpleNamespace(source='SELECTION', report=lambda *args: None)
        snapshots = {}
        for source in objects:
            destination = addon.export_path(root, source.name)
            destination.parent.mkdir(exist_ok=True)
            destination.write_bytes(b'previous FBX')
            snapshots[destination] = destination.read_bytes()
        real_export = bpy.ops.export_scene.fbx
        calls = [0]
        def interrupted_export(**kwargs):
            calls[0] += 1
            if calls[0] == 2:
                raise KeyboardInterrupt('injected export interruption')
            return real_export(**kwargs)
        selected = list(bpy.context.selected_objects)
        active = bpy.context.view_layer.objects.active
        with patch.object(addon, '_collect_preflight', return_value=(objects, objects, [], 'test')), \
             patch.object(addon, '_store_report'), \
             patch.object(addon, 'bpy', SimpleNamespace(path=bpy.path, ops=SimpleNamespace(object=bpy.ops.object, export_scene=SimpleNamespace(fbx=interrupted_export)))):
            assert addon.CS2BATCH_OT_export.execute(operator, fake_context) == {'CANCELLED'}
        assert all(path.read_bytes() == data for path, data in snapshots.items())
        assert set(bpy.context.selected_objects) == set(selected)
        assert bpy.context.view_layer.objects.active == active
        assert not list(root.glob('.mw-cs2-stage-*'))
        invalid = root / 'invalid.fbx'
        for payload in (b'', b'Kaydara FBX Binary  \x00\x1a\x00garbage'):
            invalid.write_bytes(payload)
            try:
                addon._validate_staged_fbx(invalid)
            except Exception:
                pass
            else:
                raise AssertionError('Invalid FBX accepted')
        stage = root / 'stage'
        stage.mkdir()
        pairs = [(stage / str(i), root / f'dest{i}') for i in range(3)]
        real_replace = addon.os.replace
        for interrupt in (False, True):
            for source, target in pairs:
                source.write_bytes(b'new')
                target.write_bytes(b'old')
            def failing_replace(source, target):
                if Path(source) == pairs[1][0]:
                    if interrupt:
                        raise KeyboardInterrupt('injected interruption')
                    raise OSError('injected replacement failure')
                return real_replace(source, target)
            with patch.object(addon.os, 'replace', failing_replace):
                try:
                    addon._publish_staged_batch(pairs, stage, True)
                except RuntimeError as exc:
                    assert 'restored' in str(exc)
                else:
                    raise AssertionError('Expected failure')
            assert all(target.read_bytes() == b'old' for _, target in pairs)
        for source, target in pairs:
            source.write_bytes(b'new')
        addon._publish_staged_batch(pairs, stage, True)
        assert all(target.read_bytes() == b'new' for _, target in pairs)
    return {'rotation_cases': checks, 'roundtrips': results, 'failure_rollback': 'passed'}
