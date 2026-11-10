"""Build the CS2 reference asset in an empty scene; also usable from Blender's Text Editor."""
import bpy

ASSET = "Reference Corner"
# Explicit contract taken from Settings Generator's fbx.rs and scan.rs.
ROLES = {
    "": ("Main", 1),
    "_LOD1": ("Lod1", 1),
    "_LOD2": ("Lod2", 0),
    "_Win": ("Window", 0),
    "_Wif": ("WifWindow", 0),
    "_Wio": ("WioWindow", 0),
    "_LOD1_Win": ("Lod1Window", 0),
    "_LOD2_Win": ("Lod2Window", 0),
}


def build(scene):
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    material = bpy.data.materials.new("ReferenceMasonry")
    material.diffuse_color = (0.54, 0.25, 0.12, 1)
    body = [
        (0, 0, 0), (8, 0, 0), (7, 5, 0), (0, 4, 0),
        (0, 0, 6), (8, 0, 6), (7, 5, 6), (0, 4, 6),
    ]
    shell = [(0, 3, 2), (0, 2, 1), (0, 1, 5), (0, 5, 4),
             (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6),
             (3, 0, 4), (3, 4, 7)]
    collection = bpy.data.collections.new(ASSET + " Source")
    scene.collection.children.link(collection)
    objects = {}
    for suffix, (_, slots) in ROLES.items():
        if suffix in ("", "_LOD1", "_LOD2"):
            vertices, faces = list(body), list(shell)
            if suffix == "_LOD2":
                faces.extend([(4, 5, 6), (4, 6, 7)])
            else:
                vertices.append((2, 1, 8))
                faces.extend([(4, 5, 8), (5, 6, 8), (6, 7, 8), (7, 4, 8)])
                if not suffix:
                    # Subdivide one roof face to make the detail levels distinct.
                    a, b, c = faces.pop()
                    vertices.append(tuple(sum(vertices[i][axis] for i in (a, b, c)) / 3
                                          for axis in range(3)))
                    faces.extend([(a, b, 9), (b, c, 9), (c, a, 9)])
        else:
            x = {"_Wif": 3, "_Wio": 5}.get(suffix, 1)
            vertices = [(x, -0.02, 2), (x + 1.2, -0.02, 2),
                        (x + 1.2, -0.02, 4), (x, -0.02, 3.7)]
            faces = [(0, 1, 2), (0, 2, 3)]
        name = ASSET + suffix
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        uv = mesh.uv_layers.new(name="UVMap")
        for face in mesh.polygons:
            for corner, loop in enumerate(face.loop_indices):
                # Unequal corner coordinates and seams catch swapped UVs.
                u, v = ((0.06, 0.08), (0.19, 0.10), (0.09, 0.20))[corner]
                uv.data[loop].uv = (u + 0.23 * (face.index % 4),
                                    v + 0.23 * (face.index // 4))
        if slots:
            mesh.materials.append(material)
        obj = bpy.data.objects.new(name, mesh)
        collection.objects.link(obj)
        objects[suffix] = obj
    return objects, material, collection


if __name__ == "__main__":
    build(bpy.context.scene)
