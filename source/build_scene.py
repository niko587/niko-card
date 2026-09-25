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



# ---------------------------------------------------------------- the deck: three cards, a silk band, a bow
CARD_W, CARD_H, CARD_T = 3.5, 2.0, 0.045
REST = {"CardL": ((0, 0, -0.05), (math.pi, 0, -0.035)), "CardM": ((0, 0, 0.0), (math.pi, 0, 0.026)), "CardR": ((0, 0, 0.05), (math.pi, 0, -0.017))}
FAN = {"CardL": ((-2.05, 0.10, 0.0), (0.21, 0, -0.26)), "CardM": ((0, -0.30, 0.03), (0.21, 0, 0)), "CardR": ((2.05, 0.10, 0.0), (0.21, 0, 0.26))}


def ribbon_mesh(name, pts, nu, nv, mat, closed_u=False):
    """Build a ribbon mesh from a (nv+1) x (nu+1) grid of points (row-major, v outer)."""
    row = nu + 1
    faces = []
    for j in range(nv):
        for i in range(nu):
            a = j * row + i
            b = j * row + ((i + 1) % row if not closed_u else (i + 1) % nu)
            if closed_u:
                a = j * nu + i; b = j * nu + (i + 1) % nu
                faces.append((a, b, b + nu, a + nu))
            else:
                faces.append((a, a + 1, a + 1 + row, a + row))
    me = bpy.data.meshes.new(name)
    me.from_pydata(pts, [], faces)
    me.update()
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat)
    uv = me.uv_layers.new(name="UVMap")
    per_row = nu if closed_u else row
    for loop in me.loops:
        vi = loop.vertex_index
        uv.data[loop.index].uv = ((vi % per_row) / per_row, (vi // per_row) / nv)
    return ob


def band_points(nu, nv, mode):
    """Closed silk loop around the pile: rounded rectangle in the YZ plane, ribbon width along X."""
    hy, hz, r = 1.03, 0.1025, 0.06
    # sample the rounded rectangle by arc length
    straight_y, straight_z = 2 * (hy - r), 2 * (hz - r)
    per = 2 * straight_y + 2 * straight_z + 2 * math.pi * r
    def point(s):
        s = s % per
        segs = [("y+", straight_y), ("c1", math.pi * r / 2), ("z-", straight_z), ("c2", math.pi * r / 2),
                ("y-", straight_y), ("c3", math.pi * r / 2), ("z+", straight_z), ("c4", math.pi * r / 2)]
        for kind, L in segs:
            if s <= L:
                t = s / L if L else 0
                if kind == "y+": return (-(hy - r) + straight_y * t, hz)          # along top, +Y direction
                if kind == "c1": a = math.pi / 2 - t * math.pi / 2; return ((hy - r) + r * math.cos(a), (hz - r) + r * math.sin(a))
                if kind == "z-": return (hy, (hz - r) - straight_z * t)
                if kind == "c2": a = -t * math.pi / 2; return ((hy - r) + r * math.cos(a), -(hz - r) + r * math.sin(a))
                if kind == "y-": return ((hy - r) - straight_y * t, -hz)
                if kind == "c3": a = -math.pi / 2 - t * math.pi / 2; return (-(hy - r) + r * math.cos(a), -(hz - r) + r * math.sin(a))
                if kind == "z+": return (-hy, -(hz - r) + straight_z * t)
                if kind == "c4": a = math.pi - t * math.pi / 2; return (-(hy - r) + r * math.cos(a), (hz - r) + r * math.sin(a))
            s -= L
        return (-(hy - r), hz)
    pts = []
    for j in range(nv + 1):
        xf = j / nv - 0.5
        x = 0.35 + 0.55 * xf
        for i in range(nu):
            u = i / nu
            y, z = point(u * per)
            if mode in ("loose", "off"):
                d = math.hypot(y, z) or 1
                y *= 1.08; z *= 1.08
                z += 0.02 * math.sin(4 * math.pi * xf + 8 * math.pi * u)
            if mode == "off":
                y *= 1.15; z *= 1.15
                x2 = x + 2.6
                y += 0.05 * math.sin(6 * math.pi * u + math.pi * xf)
                z += 0.03 * math.cos(4 * math.pi * u)
                pts.append((x2, y, z))
            else:
                pts.append((x, y, z))
    return pts


def bow_object(mat):
    parts = []
    # two loops
    for sgn in (-1, 1):
        cx, cz, R = sgn * 0.24, 0.12, 0.20
        nu, nv = 40, 4
        pts = []
        for j in range(nv + 1):
            v = j / nv - 0.5
            for i in range(nu + 1):
                a = 2 * math.pi * i / nu
                w = 0.26 * (0.35 + 0.65 * abs(math.sin(a / 2)))
                pts.append((cx + R * math.cos(a) * sgn, v * w, cz + R * math.sin(a) * 0.75 + 0.02))
        parts.append(ribbon_mesh("BowLoop%d" % (sgn + 1), pts, nu, nv, mat))
    # two tails
    for sgn in (-1, 1):
        nu, nv = 16, 4
        pts = []
        for j in range(nv + 1):
            v = j / nv - 0.5
            for i in range(nu + 1):
                t = i / nu
                x = sgn * 0.35 * t; y = -sgn * 0.15 * t; z = 0.10 - 0.15 * t + 0.03 * math.sin(3 * t)
                pts.append((x + v * 0.24 * 0.3, y + v * 0.24, z))
        parts.append(ribbon_mesh("BowTail%d" % (sgn + 1), pts, nu, nv, mat))
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.12))
    knot = bpy.context.active_object
    knot.scale = (0.18, 0.14, 0.10)
    knot.data.materials.append(mat)
    parts.append(knot)
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    bow = bpy.context.active_object
    bow.name = "Bow"; bow.data.name = "Bow"
    bow.location = (0, 0, 0.0775)
    return bow


def _to_nla(ob, clip):
    """Move the object's current action into an NLA track named after the clip."""
    ad = ob.animation_data
    act = ad.action
    act.name = clip + "_" + ob.name
    ad.action = None
    track = ad.nla_tracks.new()
    track.name = clip
    strip = track.strips.new(clip, 0, act)
    if hasattr(strip, "action_slot") and len(getattr(act, "slots", [])):
        strip.action_slot = act.slots[0]
    for fc in _fcurves(act):
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"; kp.easing = "EASE_IN_OUT"


def build_deck():
    reset()
    silk = material("SilkCrimson", (0.62, 0.02, 0.10), 0.25, 0.28)
    edge_mats = {"CardL": material("EdgeBronze", (0.55, 0.30, 0.14), 1.0, 0.32),
                 "CardM": material("EdgeSilver", (0.75, 0.76, 0.80), 1.0, 0.32),
                 "CardR": material("EdgeGold", (0.78, 0.56, 0.24), 1.0, 0.32)}
    deck = bpy.data.objects.new("Deck", None)
    bpy.context.collection.objects.link(deck)
    cards = {}
    for slot in ("CardL", "CardM", "CardR"):
        rig = bpy.data.objects.new(slot, None)
        bpy.context.collection.objects.link(rig)
        rig.parent = deck
        bpy.ops.mesh.primitive_cube_add(size=1)
        body = bpy.context.active_object
        body.name = slot + "Body"
        body.scale = (CARD_W, CARD_H, CARD_T)
        bpy.ops.object.transform_apply(scale=True)
        bev = body.modifiers.new("Bevel", "BEVEL")
        bev.width, bev.segments, bev.limit_method = 0.08, 6, "ANGLE"
        bpy.ops.object.modifier_apply(modifier="Bevel")
        body.data.materials.append(edge_mats[slot])
        for p in body.data.polygons:
            p.use_smooth = True
        s = slot[-1]
        front = face(slot + "Face", CARD_W - 0.2, CARD_H - 0.2, CARD_T / 2 + 0.002, False, material("Face" + s, (1, 1, 1)))
        back = face(slot + "Back", CARD_W - 0.2, CARD_H - 0.2, -CARD_T / 2 - 0.002, True, material("Back" + s, (0.05, 0.01, 0.02)))
        for ob in (body, front, back):
            ob.parent = rig
        cards[slot] = rig
    band = ribbon_mesh("Band", band_points(120, 6, "basis"), 120, 6, silk, closed_u=True)
    band.data.name = "Band"
    band.shape_key_add(name="Basis", from_mix=False)
    for key, mode in (("Loose", "loose"), ("Off", "off")):
        sk = band.shape_key_add(name=key, from_mix=False)
        for idx, co in enumerate(band_points(120, 6, mode)):
            sk.data[idx].co = co
        sk.value = 0.0
    band.parent = deck
    bow = bow_object(silk)
    bow.parent = deck

    def pose(slot, p, frame):
        rig = cards[slot]
        rig.location, rig.rotation_euler = p[0], p[1]
        rig.keyframe_insert("location", frame=frame); rig.keyframe_insert("rotation_euler", frame=frame)

    # Idle: the whole deck breathes
    for f in range(0, 241, 30):
        a = 2 * math.pi * f / 240
        deck.location = (0, 0, 0.015 * math.sin(a))
        deck.rotation_euler = (0.009 * math.sin(a + 1.1), 0, 0.014 * math.sin(a))
        deck.keyframe_insert("location", frame=f); deck.keyframe_insert("rotation_euler", frame=f)
    for fc in _fcurves(deck.animation_data.action):
        for kp in fc.keyframe_points:
            kp.interpolation = "SINE"
    _to_nla(deck, "Idle")

    # Square: a quick tidy tap of the pile
    for slot, s in (("CardR", 0), ("CardM", 2), ("CardL", 4)):
        loc, rot = REST[slot]
        pose(slot, REST[slot], 0)
        pose(slot, ((loc[0], loc[1], loc[2] + 0.06), (rot[0], rot[1], 0)), 4 + s)
        pose(slot, ((loc[0], loc[1], loc[2] + 0.03), (rot[0], rot[1], rot[2] * 0.5)), 12 + s)
        pose(slot, REST[slot], 24)
        _to_nla(cards[slot], "Square")
    # Cut: the top card lifts, slides out and returns
    for slot in ("CardL", "CardM", "CardR"):
        loc, rot = REST[slot]
        pose(slot, REST[slot], 0)
        if slot == "CardR":
            pose(slot, ((0, 0, 0.20), rot), 6)
            pose(slot, ((0.8, 0, 0.20), rot), 14)
            pose(slot, ((0.8, 0, 0.20), rot), 20)
            pose(slot, ((0, 0, 0.20), rot), 28)
        pose(slot, REST[slot], 36)
        _to_nla(cards[slot], "Cut")
    # Deal: cards rise, flip and fan out face-up
    for slot, s in (("CardR", 0), ("CardM", 4), ("CardL", 8)):
        loc, rot = REST[slot]; floc, frot = FAN[slot]
        pose(slot, REST[slot], 0)
        pose(slot, ((loc[0], loc[1], loc[2] + 0.25), rot), 8 + s)
        pose(slot, ((loc[0], loc[1], loc[2] + 0.25), rot), 20 + s)
        pose(slot, ((floc[0], floc[1], floc[2] + 0.12), (0, 0, frot[2])), 48 + s)
        pose(slot, FAN[slot], 66)
        _to_nla(cards[slot], "Deal")
    # Bow: pops in when the client books
    for f, sc in ((0, 0.0), (14, 1.15), (24, 1.0)):
        bow.scale = (sc, sc, sc); bow.keyframe_insert("scale", frame=f)
    _to_nla(bow, "Bow")

    # rest pose is the exported static pose
    for slot in cards:
        cards[slot].location, cards[slot].rotation_euler = REST[slot]
    deck.location, deck.rotation_euler = (0, 0, 0), (0, 0, 0)
    bow.scale = (0, 0, 0)
    bpy.context.scene.frame_set(0)
    bpy.ops.export_scene.gltf(filepath=OUT + "deck.glb", export_format="GLB", export_animations=True,
                              export_animation_mode="NLA_TRACKS", export_nla_strips=True, export_force_sampling=True,
                              export_morph=True, export_morph_normal=False, export_apply=False,
                              export_materials="EXPORT", export_yup=True)


if __name__ == "__main__":
    which = [a for a in sys.argv[1:] if a in ("silk", "card", "deck")] or ["silk", "card", "deck"]
    if "silk" in which: build_silk()
    if "card" in which: build_card()
    if "deck" in which: build_deck()
    print("exported", which, "to", OUT)
