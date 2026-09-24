"""Model and animate the business-card 3D assets in Blender, then export GLB files.

silk.glb : three flowing silk ribbons, each looping via animated shape keys (8 s @ 30 fps)
card.glb : a bevelled business card (front/back faces UV-mapped) that floats, sways and flips
"""
import math, sys, os
import bpy, bmesh

OUT = sys.argv[-1] if sys.argv[-1].endswith("/") else os.path.dirname(os.path.abspath(__file__)) + "/"
FPS, LOOP = 30, 240


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene
    s.render.fps = FPS
    s.frame_start, s.frame_end = 0, LOOP
    return s


def material(name, rgb, metallic=0.0, rough=0.4):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough
    return m


# ---------------------------------------------------------------- silk ribbons
def ribbon_points(nu, nv, p, phase):
    L, W = p["length"], p["width"]
    pts = []
    for j in range(nv + 1):
        v = j / nv - 0.5
        for i in range(nu + 1):
            u = i / nu
            a = 2 * math.pi * u
            x = -L / 2 + L * u
            y = p["y"] + p["amp"] * math.sin(a * p["freq"] + phase) + p["sag"] * (u - 0.5) ** 2
            z = p["z"] + 0.35 * p["amp"] * math.cos(a * p["freq"] * 0.7 + phase * 1.3)
            th = p["twist"] * u + p["tw0"] + 0.55 * math.sin(a * 0.9 + phase)
            # soft ripple across the width gives the fabric its folds
            ripple = 0.05 * math.sin(v * 9 + a * 2 + phase * 2)
            # (x, up, toward camera) -> Blender (x, -depth, up) so the glTF Y-up export faces the web camera
            up, depth = y + W * v * math.cos(th), z + W * v * math.sin(th) + ripple
            pts.append((x, -depth, up))
    return pts


def make_ribbon(name, p, mat, nu=90, nv=12):
    verts = ribbon_points(nu, nv, p, 0.0)
    faces = []
    row = nu + 1
    for j in range(nv):
        for i in range(nu):
            a = j * row + i
            faces.append((a, a + 1, a + 1 + row, a + row))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    for poly in me.polygons:
        poly.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat)

    # UVs along length/width so a sheen texture can run with the weave
    uv = me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        vi = loop.vertex_index
        uv.data[loop.index].uv = ((vi % row) / nu, (vi // row) / nv)

    # shape keys: the ribbon at four phases of its wave; blending them in sequence loops the motion
    ob.shape_key_add(name="Basis", from_mix=False)
    keys = []
    for k in (1, 2, 3):
        sk = ob.shape_key_add(name=f"phase{k}", from_mix=False)
        for idx, co in enumerate(ribbon_points(nu, nv, p, k * math.pi / 2)):
            sk.data[idx].co = co
        keys.append(sk)
    seg = LOOP // 4
    for n, sk in enumerate(keys):
        peak = (n + 1) * seg
        for f, val in ((peak - seg, 0.0), (peak, 1.0), (peak + seg, 0.0)):
            sk.value = val
            sk.keyframe_insert("value", frame=f)
    act = ob.data.shape_keys.animation_data.action
    for fc in _fcurves(act):
        for kp in fc.keyframe_points:
            kp.interpolation = "SINE"
    ob.data.shape_keys.animation_data.action.name = f"{name}Flow"
    return ob


def _fcurves(action):
    if hasattr(action, "fcurves") and len(getattr(action, "fcurves", [])):
        return list(action.fcurves)
    out = []  # Blender 4.4+ layered actions
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            for bag in strip.channelbags:
                out.extend(bag.fcurves)
    return out


def build_silk():
    reset()
    deep = material("SilkDeep", (0.35, 0.01, 0.05), 0.2, 0.32)
    crimson = material("SilkCrimson", (0.62, 0.02, 0.10), 0.25, 0.28)
    black = material("SilkBlack", (0.03, 0.005, 0.01), 0.3, 0.35)
    make_ribbon("RibbonBack", dict(length=9, width=2.6, y=0.6, z=-1.6, amp=0.7, freq=0.8, sag=-1.2, twist=2.4, tw0=0.3), black)
    make_ribbon("RibbonMid", dict(length=8, width=1.9, y=0.1, z=-0.6, amp=0.55, freq=1.0, sag=0.8, twist=3.1, tw0=1.2), deep)
    make_ribbon("RibbonFront", dict(length=7.5, width=1.3, y=-0.5, z=0.3, amp=0.45, freq=1.2, sag=-0.6, twist=3.8, tw0=2.0), crimson)
    # a thin sash that sweeps in front of the portrait on the web page
    make_ribbon("RibbonSash", dict(length=8, width=0.7, y=-1.25, z=1.1, amp=0.35, freq=1.4, sag=0.5, twist=4.4, tw0=0.6), crimson)
    bpy.ops.export_scene.gltf(filepath=OUT + "silk.glb", export_format="GLB", export_animations=True,
                              export_morph=True, export_morph_normal=True, export_apply=False,
                              export_materials="EXPORT", export_yup=True)


# ---------------------------------------------------------------- 3D business card
def face(name, w, h, z, flip, mat):
    me = bpy.data.meshes.new(name)
    hw, hh = w / 2, h / 2
    if not flip:
        verts = [(-hw, -hh, z), (hw, -hh, z), (hw, hh, z), (-hw, hh, z)]
    else:  # back face winds the other way so its normal points -Z, UVs read correctly from behind
        verts = [(hw, -hh, z), (-hw, -hh, z), (-hw, hh, z), (hw, hh, z)]
    me.from_pydata(verts, [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for i, c in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
        uv.data[i].uv = c
    ob = bpy.data.objects.new(name, me)
    ob.data.materials.append(mat)
    bpy.context.collection.objects.link(ob)
    return ob


def build_card():
    reset()
    W, H, T = 3.5, 2.0, 0.045  # 3.5 x 2 in, the card's real proportions
    rig = bpy.data.objects.new("Card", None)
    bpy.context.collection.objects.link(rig)

    bpy.ops.mesh.primitive_cube_add(size=1)
    body = bpy.context.active_object
    body.name = "CardEdge"
    body.scale = (W, H, T)
    bpy.ops.object.transform_apply(scale=True)
    bev = body.modifiers.new("Bevel", "BEVEL")
    bev.width, bev.segments = 0.08, 6
    bev.limit_method = "ANGLE"
    bpy.ops.object.modifier_apply(modifier="Bevel")
    body.data.materials.append(material("CardEdge", (0.02, 0.0, 0.004), 0.6, 0.3))
    for poly in body.data.polygons:
        poly.use_smooth = True
    body.parent = rig

    inset = 0.01
    front = face("CardFront", W - inset, H - inset, T / 2 + 0.002, False, material("CardFront", (1, 1, 1)))
    back = face("CardBack", W - inset, H - inset, -T / 2 - 0.002, True, material("CardBack", (0.4, 0.02, 0.07)))
    # stand the card upright facing Blender -Y (the web camera after the Y-up export)
    for ob in (body, front, back):
        ob.rotation_euler = (math.pi / 2, 0, 0)
        bpy.ops.object.select_all(action="DESELECT")
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.transform_apply(rotation=True)
    front.parent = back.parent = rig

    # autonomous motion: bob, sway, and one full turn per loop to show the back ("tap to save")
    keys = [(0, -0.18, 0.00), (60, 0.18, 0.06), (120, 0.20, -0.04), (150, 0.0, 0.05),
            (210, 2 * math.pi - 0.18, -0.02), (240, 2 * math.pi - 0.18, 0.0)]
    for f, ry, bob in keys:
        rig.rotation_euler = (0.10 * math.sin(f / LOOP * 2 * math.pi), 0.04 * math.cos(f / LOOP * 2 * math.pi), ry)
        rig.location = (0, 0, bob)
        rig.keyframe_insert("rotation_euler", frame=f)
        rig.keyframe_insert("location", frame=f)
    rig.animation_data.action.name = "CardFloat"
    for fc in _fcurves(rig.animation_data.action):
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
            kp.easing = "EASE_IN_OUT"
    bpy.ops.export_scene.gltf(filepath=OUT + "card.glb", export_format="GLB", export_animations=True,
                              export_apply=True, export_materials="EXPORT", export_yup=True)


if __name__ == "__main__":
    build_silk()
    build_card()
    print("exported to", OUT)
