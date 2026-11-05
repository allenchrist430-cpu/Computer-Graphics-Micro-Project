# -*- coding: utf-8 -*-
"""
ALLIANCE UNIVERSITY - ADMINISTRATIVE BLOCK
Procedural Blender model  +  Painter's Algorithm viewport engine   (CORRECTED VERSION)

How to run
    Blender > Scripting workspace > Open this file > Run Script (Alt+P).
    The model is generated and the Painter's-Algorithm viewer starts automatically.

Viewer controls
    WASD  : fly            Q / E : down / up        Middle-mouse drag : look
    SPACE : Painter's sort ON / OFF (scrambled)     Z : GPU Z-buffer ON / OFF
    G     : depth shading  - / = : draw progress    1-6 : camera presets    ESC : stop

What was corrected in this version
    * Building is now fully closed: front block, two long wings, rear range, galleries,
      orange tiled hip / gable roofs (as in the aerial photo), white domes, rear facade.
    * The floor that cut through Ganesha's head is gone.  The Ganesha rotunda is open
      up to the dome; there are NO floors in the entrance hall.
    * Two storeys of balconies (ground colonnade + first-floor black ornate railing)
      on the front left / right (loggias) and on the left / right / rear sides of the
      atrium, with staircases, wooden doors and windows - as in the reference photos.
    * Garden behind the Ganesha statue plus side gardens, palms and potted plants.
    * Entrance facade has REAL openings (3 upper windows, 2 lower windows, double door)
      so you can see through them from the Ganesha statue to the outside.
    * Camera presets 2, 3 and 4 were looking straight down; they are fixed.
"""

import bpy
import bmesh
import math
import time
import random
from mathutils import Vector, Matrix, Quaternion
import gpu
from gpu_extras.batch import batch_for_shader
import blf

# ==============================================================================
# 1. GLOBAL STATE & CONFIGURATION FOR PAINTER'S ALGORITHM ENGINE
# ==============================================================================
class PainterEngineState:
    handle_3d = None
    handle_2d = None
    is_running = False

    painter_sort_on = True
    z_buffer_on = False
    depth_shading_on = False
    labels_on = True
    draw_progress = 1.0

    render_items = []
    scrambled_indices = []
    sorted_landmarks = []

    total_polygons = 0
    drawn_polygons = 0
    objects_sorted = 0
    sort_time_ms = 0.0
    cam_pos = Vector((0.0, -55.0, 5.0))
    cam_forward = Vector((0.0, 1.0, 0.0))
    current_scene_name = "Free Fly"

STATE = PainterEngineState()

# ==============================================================================
# 2. COLOR PALETTE
# ==============================================================================
PALETTE = {
    "WallCream":      (0.992, 0.984, 0.969, 1.0),
    "WallTrim":       (0.945, 0.935, 0.910, 1.0),
    "Terracotta":     (0.784, 0.294, 0.192, 1.0),
    "DarkWood":       (0.243, 0.153, 0.137, 1.0),
    "CarvedWood":     (0.360, 0.210, 0.140, 1.0),
    "GlassDark":      (0.110, 0.165, 0.215, 1.0),
    "PathwayGrey":    (0.260, 0.275, 0.290, 1.0),
    "StairStone":     (0.740, 0.710, 0.660, 1.0),
    "DrainGrate":     (0.160, 0.160, 0.170, 1.0),
    "CurbBlack":      (0.080, 0.080, 0.080, 1.0),
    "CurbWhite":      (0.950, 0.950, 0.950, 1.0),
    "IronBlack":      (0.100, 0.105, 0.115, 1.0),
    "GoldSpire":      (0.880, 0.700, 0.200, 1.0),
    "VelvetRed":      (0.820, 0.120, 0.120, 1.0),
    "MarbleRed":      (0.420, 0.220, 0.200, 1.0),
    "MarbleCream":    (0.910, 0.875, 0.810, 1.0),
    "SofaPink":       (0.760, 0.560, 0.570, 1.0),
    "SofaCushion":    (0.720, 0.310, 0.220, 1.0),
    "FoliageDark":    (0.176, 0.353, 0.153, 1.0),
    "FoliageLight":   (0.298, 0.686, 0.314, 1.0),
    "FoliageYellow":  (0.480, 0.740, 0.220, 1.0),
    "TrunkBrown":     (0.290, 0.200, 0.140, 1.0),
    "LawnGreen":      (0.150, 0.310, 0.130, 1.0),
    "BoardNavy":      (0.070, 0.130, 0.200, 1.0),
    "FlowerRed":      (0.850, 0.150, 0.150, 1.0),
    "FlowerYellow":   (0.950, 0.800, 0.100, 1.0),
    "SkyBlue":        (0.530, 0.810, 0.920, 1.0),
    "LampPost":       (0.120, 0.120, 0.130, 1.0),
    "ConcreteGrey":   (0.550, 0.550, 0.540, 1.0),
    # ---- new in the corrected version -------------------------------------
    "WoodFrame":      (0.360, 0.160, 0.100, 1.0),   # window / door frames (brown wood)
    "DoorWood":       (0.400, 0.200, 0.120, 1.0),
    "RoofOrange":     (0.860, 0.430, 0.220, 1.0),   # clay-tile roof, light course
    "RoofOrange2":    (0.780, 0.350, 0.170, 1.0),   # clay-tile roof, dark course
    "RoofRidge":      (0.600, 0.260, 0.130, 1.0),
    "PotBlack":       (0.070, 0.070, 0.080, 1.0),
    "FrameGold":      (0.800, 0.620, 0.220, 1.0),
    "PaintingRed":    (0.780, 0.300, 0.180, 1.0),
    "TableWood":      (0.300, 0.170, 0.120, 1.0),
    "FloorInlay":     (0.300, 0.200, 0.160, 1.0),
}

MAT_CACHE = {}

def get_material(name, rgba):
    if name in MAT_CACHE:
        return MAT_CACHE[name]
    mat = bpy.data.materials.new(name=f"Mat_{name}")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out_node = nodes.new(type='ShaderNodeOutputMaterial')
    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = rgba
    bsdf.inputs['Roughness'].default_value = 0.75
    links.new(bsdf.outputs['BSDF'], out_node.inputs['Surface'])
    mat.diffuse_color = rgba
    MAT_CACHE[name] = mat
    return mat

# ==============================================================================
# 2b. KEY DIMENSIONS (metres)
# ==============================================================================
PL        = 1.60            # top of the main plinth
FZ        = PL + 0.06       # finished interior floor level
F1        = PL + 3.70       # first-floor slab top (balcony level)
WALL_TOP  = PL + 7.40       # top of walls  (z = 9.00)
ROOF_Z    = PL + 7.70       # top of flat roof slab / start of tiled roofs (z = 9.30)
GAL_D     = 2.30            # depth of the courtyard galleries
RC        = Vector((0.0, 6.0, PL))     # centre of the Ganesha rotunda
WING_X0   = 21.75           # inner face of the side wings
WING_X1   = 30.25           # outer face of the side wings
Y_FRONT_W = -10.5           # front face of the end pavilions
Y_REAR    = 25.0            # rear outer face of the whole building
Y_REAR_IN = 21.0            # inner face of the rear range
Y_HALL_BK = -1.0            # rear face of the front block (hall opens to the rotunda here)
FACADE_Y  = -8.5            # centre-plane of the entrance facade wall (0.6 thick)

# ==============================================================================
# 3. FAST BMESH PRIMITIVE FACTORY
# ==============================================================================
MAIN_COLLECTION = None
CUR_BIAS = 0.0     # painter-sort bias for "detail" objects (windows, railings...)

class bias_scope:
    """Detail objects (window frames, railings...) get a small sort bias so the
    Painter's algorithm draws them AFTER the wall they sit on."""
    def __init__(self, value):
        self.value = value
        self.old = 0.0
    def __enter__(self):
        global CUR_BIAS
        self.old = CUR_BIAS
        CUR_BIAS = self.value
    def __exit__(self, *args):
        global CUR_BIAS
        CUR_BIAS = self.old


def register_obj(mesh, name, location, rotation, mat_name, is_landmark=False):
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    obj.rotation_euler = rotation
    rgba = PALETTE.get(mat_name, (0.9, 0.9, 0.9, 1.0))
    mat = get_material(mat_name, rgba)
    obj.data.materials.append(mat)
    obj["painter_color"] = rgba
    obj["is_landmark"] = is_landmark
    obj["landmark_label"] = name
    obj["painter_bias"] = float(CUR_BIAS)
    MAIN_COLLECTION.objects.link(obj)
    return obj


def _finish_mesh(bm, name):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def _bm_box(bm, cx, cy, cz, sx, sy, sz):
    """Add one axis-aligned box (outward-facing quads) to a bmesh."""
    hx, hy, hz = sx * 0.5, sy * 0.5, sz * 0.5
    vs = []
    for ix in (-1.0, 1.0):
        for iy in (-1.0, 1.0):
            for iz in (-1.0, 1.0):
                vs.append(bm.verts.new((cx + ix * hx, cy + iy * hy, cz + iz * hz)))
    for f in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
              (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
        bm.faces.new([vs[i] for i in f])


def _bm_sphere(bm, center, radius, scale=(1.0, 1.0, 1.0), rot=(0.0, 0.0, 0.0),
               segs=10, rings=6):
    """Add one (scaled, rotated) UV-sphere to a bmesh."""
    rm = (Matrix.Rotation(rot[2], 3, 'Z') @ Matrix.Rotation(rot[1], 3, 'Y')
          @ Matrix.Rotation(rot[0], 3, 'X'))
    cx, cy, cz = center

    def P(x, y, z):
        v = rm @ Vector((x * scale[0], y * scale[1], z * scale[2]))
        return bm.verts.new((cx + v.x, cy + v.y, cz + v.z))

    top = P(0.0, 0.0, radius)
    bot = P(0.0, 0.0, -radius)
    ring = []
    for i in range(1, rings):
        phi = math.pi * i / rings
        r = radius * math.sin(phi)
        z = radius * math.cos(phi)
        ring.append([P(r * math.cos(2.0 * math.pi * j / segs),
                       r * math.sin(2.0 * math.pi * j / segs), z) for j in range(segs)])
    for j in range(segs):
        j2 = (j + 1) % segs
        bm.faces.new((top, ring[0][j], ring[0][j2]))
        bm.faces.new((bot, ring[-1][j2], ring[-1][j]))
        for i in range(len(ring) - 1):
            bm.faces.new((ring[i][j], ring[i + 1][j], ring[i + 1][j2], ring[i][j2]))


def add_box(name, loc, scale, mat_name, rot=(0.0, 0.0, 0.0), is_landmark=False):
    bm = bmesh.new()
    _bm_box(bm, 0.0, 0.0, 0.0, scale[0], scale[1], scale[2])
    return register_obj(_finish_mesh(bm, name), name, loc, rot, mat_name, is_landmark)


def add_boxes(name, loc, parts, mat_name, rot=(0.0, 0.0, 0.0), is_landmark=False):
    """Several boxes merged into ONE object.  parts = [(cx,cy,cz, sx,sy,sz), ...]
    given in the object's local axes."""
    bm = bmesh.new()
    n = 0
    for (cx, cy, cz, sx, sy, sz) in parts:
        if sx < 1e-4 or sy < 1e-4 or sz < 1e-4:
            continue
        _bm_box(bm, cx, cy, cz, sx, sy, sz)
        n += 1
    if n == 0:
        bm.free()
        return None
    return register_obj(_finish_mesh(bm, name), name, loc, rot, mat_name, is_landmark)


def add_ellipsoids(name, loc, items, mat_name, rot=(0.0, 0.0, 0.0), segs=10, rings=6):
    """Several (scaled / rotated) spheres merged into ONE object.
    items = [((ox,oy,oz), radius, (sx,sy,sz), (rx,ry,rz)), ...]"""
    bm = bmesh.new()
    for (off, radius, sc, rt) in items:
        _bm_sphere(bm, off, radius, sc, rt, segs, rings)
    return register_obj(_finish_mesh(bm, name), name, loc, rot, mat_name)


def add_cylinder(name, loc, radius, depth, mat_name, segs=16, rot=(0.0, 0.0, 0.0),
                 is_landmark=False, hollow=False):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=(not hollow), cap_tris=False,
                          segments=segs, radius1=radius, radius2=radius, depth=depth)
    mesh = _finish_mesh(bm, name)
    return register_obj(mesh, name, loc, rot, mat_name, is_landmark)


def add_cone(name, loc, r1, r2, depth, mat_name, segs=16, rot=(0.0, 0.0, 0.0), is_landmark=False):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=True, segments=segs,
                          radius1=r1, radius2=r2, depth=depth)
    mesh = _finish_mesh(bm, name)
    return register_obj(mesh, name, loc, rot, mat_name, is_landmark)


def add_sphere(name, loc, radius, mat_name, segs=14, rings=10,
               scale=(1.0, 1.0, 1.0), rot=(0.0, 0.0, 0.0), hemisphere=False, is_landmark=False):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=radius)
    if hemisphere:
        verts_to_remove = [v for v in bm.verts if v.co.z < -0.01]
        bmesh.ops.delete(bm, geom=verts_to_remove, context='VERTS')
    bmesh.ops.scale(bm, vec=scale, verts=bm.verts)
    mesh = _finish_mesh(bm, name)
    return register_obj(mesh, name, loc, rot, mat_name, is_landmark)


def add_pitched_gable(name, loc, width, depth, height, mat_name, rot=(0.0, 0.0, 0.0), is_landmark=False):
    """Closed triangular prism: ridge runs along Y, base at loc.z."""
    bm = bmesh.new()
    hw, hd = width / 2.0, depth / 2.0
    v1 = bm.verts.new((-hw, -hd, 0.0))
    v2 = bm.verts.new(( hw, -hd, 0.0))
    v3 = bm.verts.new(( 0.0, -hd, height))
    v4 = bm.verts.new((-hw,  hd, 0.0))
    v5 = bm.verts.new(( hw,  hd, 0.0))
    v6 = bm.verts.new(( 0.0,  hd, height))
    bm.faces.new((v1, v2, v3))
    bm.faces.new((v6, v5, v4))
    bm.faces.new((v1, v4, v5, v2))
    bm.faces.new((v2, v5, v6, v3))
    bm.faces.new((v3, v6, v4, v1))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = _finish_mesh(bm, name)
    return register_obj(mesh, name, loc, rot, mat_name, is_landmark)


# ------------------------------------------------------------------------------
# Local "wall frames":  u runs ALONG a wall, n points AWAY from it, z is world z.
# Every facade / gallery detail is authored once in this frame and placed anywhere.
# ------------------------------------------------------------------------------
class Frame:
    def __init__(self, ox, oy, ang=0.0):
        self.ox, self.oy, self.ang = ox, oy, ang
        c, s = math.cos(ang), math.sin(ang)
        self.ux, self.uy = c, s            # u axis (world)
        self.nx, self.ny = -s, c           # n axis (world)
        self.rot = (0.0, 0.0, ang)

    def w(self, u, n, z=0.0):
        return Vector((self.ox + self.ux * u + self.nx * n,
                       self.oy + self.uy * u + self.ny * n, z))

    def local(self, x, y):
        dx, dy = x - self.ox, y - self.oy
        return (dx * self.ux + dy * self.uy, dx * self.nx + dy * self.ny)


def add_box_f(name, fr, u, n, z, su, sn, sz, mat_name, is_landmark=False):
    return add_box(name, fr.w(u, n, z), (su, sn, sz), mat_name, rot=fr.rot, is_landmark=is_landmark)


def add_boxes_f(name, fr, u, n, z, parts, mat_name, is_landmark=False):
    return add_boxes(name, fr.w(u, n, z), parts, mat_name, rot=fr.rot, is_landmark=is_landmark)


def add_arch(name, fr, u, n, z_spring, radius, depth, mat_name, segs=14):
    """Half-disc (semicircular arch head) standing on z_spring."""
    bm = bmesh.new()
    front, back = [], []
    for i in range(segs + 1):
        t = math.pi * i / segs
        pu, pz = radius * math.cos(t), radius * math.sin(t)
        front.append(bm.verts.new((pu,  depth / 2.0, pz)))
        back.append(bm.verts.new((pu, -depth / 2.0, pz)))
    bm.faces.new(front)
    bm.faces.new(list(reversed(back)))
    for i in range(segs):
        bm.faces.new((front[i], back[i], back[i + 1], front[i + 1]))
    bm.faces.new((front[-1], back[-1], back[0], front[0]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = _finish_mesh(bm, name)
    return register_obj(mesh, name, fr.w(u, n, z_spring), fr.rot, mat_name)


def add_beam(name, p0, p1, thick, height, zc, mat_name, chunk=8.0, shift=None):
    """A long horizontal band from p0 to p1 (XY), cut into chunks <= `chunk` metres
    so the Painter's sort stays accurate.  `shift` moves the band sideways (XY)."""
    d = Vector((p1.x - p0.x, p1.y - p0.y, 0.0))
    L = d.length
    if L < 0.05:
        return
    ang = math.atan2(d.y, d.x)
    nch = max(1, int(math.ceil(L / chunk)))
    sl = L / nch
    sh = shift if shift is not None else Vector((0.0, 0.0, 0.0))
    for k in range(nch):
        t = (k + 0.5) / nch
        c = Vector((p0.x + d.x * t + sh.x, p0.y + d.y * t + sh.y, zc))
        add_box(f"{name}_{k}", c, (sl, thick, height), mat_name, rot=(0.0, 0.0, ang))


def add_face_band(name, p0, p1, out, thick, height, zc, mat_name, chunk=8.0):
    """Decorative band hugging a wall face.  p0->p1 lies ON the wall face and `out`
    is the unit vector pointing away from the wall."""
    sh = Vector((out.x * (thick / 2.0 - 0.01), out.y * (thick / 2.0 - 0.01), 0.0))
    add_beam(name, p0, p1, thick, height, zc, mat_name, chunk, sh)

# ==============================================================================
# 4. ARCHITECTURAL SUB-ASSEMBLIES
# ==============================================================================
# ---- 4a. windows, doors and walls with real openings -------------------------
def build_window(prefix, fr, u, n, zc, w, h, rows=4, cols=4, depth=0.16, frame_t=0.12,
                 mat_frame="WoodFrame", trim=True, trim_dn=0.0, trim_depth=None, extra=None):
    """Grid window made of 3 objects (glass / wooden frame+mullions / sill+lintel)."""
    td = (depth + 0.10) if trim_depth is None else trim_depth
    with bias_scope(2.5):
        add_box_f(f"{prefix}_Glass", fr, u, n, zc, w, 0.06, h, "GlassDark")
        parts = [(0.0, 0.0,  h / 2.0, w + frame_t, depth, frame_t),
                 (0.0, 0.0, -h / 2.0, w + frame_t, depth, frame_t),
                 (-w / 2.0, 0.0, 0.0, frame_t, depth, h),
                 ( w / 2.0, 0.0, 0.0, frame_t, depth, h)]
        for r in range(1, rows):
            parts.append((0.0, 0.0, -h / 2.0 + r * h / rows, w, depth * 0.8, 0.055))
        for c in range(1, cols):
            parts.append((-w / 2.0 + c * w / cols, 0.0, 0.0, 0.055, depth * 0.8, h))
        if extra:
            parts.extend(extra)
        add_boxes_f(f"{prefix}_Frame", fr, u, n, zc, parts, mat_frame)
        if trim:
            tp = [(0.0, trim_dn, -h / 2.0 - 0.14, w + 0.55, td, 0.14),
                  (0.0, trim_dn,  h / 2.0 + 0.12, w + 0.45, td * 0.8, 0.12)]
            add_boxes_f(f"{prefix}_Trim", fr, u, n, zc, tp, "WallTrim")


def build_door(prefix, fr, u, n, z0, w, h, depth=0.16, trim=True, trim_dn=0.0, trim_depth=None):
    """Wooden double door with glazed upper part."""
    extra = [(0.0, 0.0, 0.0, 0.09, depth, h),                       # centre split
             (0.0, 0.0, -h / 2.0 + 0.45, w - 0.1, depth * 1.1, 0.9)]  # kick panels
    build_window(prefix, fr, u, n, z0 + h / 2.0, w, h, rows=4, cols=2, depth=depth,
                 mat_frame="DoorWood", trim=trim, trim_dn=trim_dn, trim_depth=trim_depth,
                 extra=extra)


def wall_with_openings(prefix, fr, u0, u1, z0, z1, thick, cols, mat_name):
    """A wall in frame `fr` (centre-plane n=0) made of separate boxes AROUND the
    openings, so windows / doors are real holes.
    cols = [(ua, ub, [(za, zb), ...]), ...]  (openings stacked in one column)."""
    k = [0]

    def piece(ua, ub, za, zb):
        if ub - ua < 0.02 or zb - za < 0.02:
            return
        add_box_f(f"{prefix}_{k[0]}", fr, (ua + ub) / 2.0, 0.0, (za + zb) / 2.0,
                  ub - ua, thick, zb - za, mat_name)
        k[0] += 1

    cur = u0
    for ua, ub, ops in sorted(cols, key=lambda c: c[0]):
        piece(cur, ua, z0, z1)
        zp = z0
        for za, zb in sorted(ops):
            piece(ua, ub, zp, za)
            zp = max(zp, zb)
        piece(ua, ub, zp, z1)
        cur = ub
    piece(cur, u1, z0, z1)


# ---- 4b. columns --------------------------------------------------------------
def build_classical_pillar(prefix, base_loc, height=7.2, radius=0.45, is_landmark=False):
    add_box(f"{prefix}_Plinth", base_loc + Vector((0.0, 0.0, 0.25)),
            (radius * 3.0, radius * 3.0, 0.5), "WallCream")
    add_cylinder(f"{prefix}_Torus", base_loc + Vector((0.0, 0.0, 0.60)),
                 radius * 1.3, 0.22, "WallTrim", segs=16)
    add_cylinder(f"{prefix}", base_loc + Vector((0.0, 0.0, 0.7 + (height - 1.3) / 2.0)),
                 radius, height - 1.3, "WallCream", segs=20, is_landmark=is_landmark)
    add_cone(f"{prefix}_CapBell", base_loc + Vector((0.0, 0.0, height - 0.35)),
             radius, radius * 1.45, 0.45, "WallTrim", segs=16)
    add_box(f"{prefix}_Abacus", base_loc + Vector((0.0, 0.0, height - 0.08)),
            (radius * 3.1, radius * 3.1, 0.18), "WallCream")


def build_slim_column(prefix, base, height, radius=0.28):
    """Light-weight 2-object column used in galleries / loggias."""
    add_cylinder(f"{prefix}_Shaft", base + Vector((0.0, 0.0, height / 2.0)),
                 radius, max(0.2, height - 0.5), "WallCream", segs=14)
    r = radius
    parts = [(0.0, 0.0, 0.10, r * 2.5, r * 2.5, 0.20),
             (0.0, 0.0, 0.26, r * 2.0, r * 2.0, 0.12),
             (0.0, 0.0, height - 0.20, r * 2.1, r * 2.1, 0.14),
             (0.0, 0.0, height - 0.07, r * 3.2, r * 3.2, 0.14)]
    add_boxes(f"{prefix}_BaseCap", base.copy(), parts, "WallCream")


# ---- 4c. railings -------------------------------------------------------------
def build_balcony_railing(prefix, p0, p1, z, height=0.95, seg=3.0, gap=0.20):
    """Black ornate iron railing with wooden top rail, cut into <=3 m segments."""
    d = Vector((p1.x - p0.x, p1.y - p0.y, 0.0))
    L = d.length
    if L < 0.05:
        return
    ang = math.atan2(d.y, d.x)
    ns = max(1, int(math.ceil(L / seg)))
    sl = L / ns
    with bias_scope(1.5):
        for k in range(ns):
            t = (k + 0.5) / ns
            loc = Vector((p0.x + d.x * t, p0.y + d.y * t, z))
            iron = [(0.0, 0.0, 0.14, sl, 0.05, 0.07),                  # bottom rail
                    (0.0, 0.0, height * 0.5, sl, 0.035, 0.04),         # mid rail
                    (0.0, 0.0, height * 0.46, sl, 0.012, height * 0.62),   # scroll panel
                    (-sl / 2.0, 0.0, height / 2.0, 0.08, 0.08, height),    # end posts
                    ( sl / 2.0, 0.0, height / 2.0, 0.08, 0.08, height)]
            nb = max(2, int(sl / gap))
            for i in range(nb + 1):
                uu = -sl / 2.0 + i * (sl / nb)
                iron.append((uu, 0.0, height / 2.0 - 0.02, 0.03, 0.03, height - 0.10))
            add_boxes(f"{prefix}_Iron_{k}", loc, iron, "IronBlack", rot=(0.0, 0.0, ang))
            add_box(f"{prefix}_TopRail_{k}", loc + Vector((0.0, 0.0, height)),
                    (sl + 0.04, 0.11, 0.07), "DarkWood", rot=(0.0, 0.0, ang))


def build_stair_railing(prefix, p0, p1, h=0.90, spacing=0.30):
    """Sloped wooden hand-rail with balusters.  p0 / p1 = points on the step noses."""
    d = p1 - p0
    horiz = math.hypot(d.x, d.y)
    ang = math.atan2(d.y, d.x)
    pitch = math.atan2(d.z, horiz)
    mid = (p0 + p1) * 0.5
    with bias_scope(1.5):
        add_box(f"{prefix}_Handrail", mid + Vector((0.0, 0.0, h)), (d.length, 0.09, 0.07),
                "WoodFrame", rot=(0.0, -pitch, ang))
        nb = max(2, int(d.length / spacing))
        parts = []
        for i in range(nb + 1):
            p = p0.lerp(p1, i / nb)
            parts.append((p.x, p.y, p.z + h / 2.0, 0.04, 0.04, h))
        add_boxes(f"{prefix}_Balusters", Vector((0.0, 0.0, 0.0)), parts, "WoodFrame")


# ---- 4d. tiled roofs ----------------------------------------------------------
def _dedupe(pts, tol=1e-5):
    out = []
    for p in pts:
        if not out or (p - out[-1]).length > tol:
            out.append(p)
    if len(out) > 1 and (out[0] - out[-1]).length <= tol:
        out.pop()
    return out


def _add_strips(bm_a, bm_b, p0, p1, p2, p3, courses):
    """Slice one roof slope into `courses` tile rows, alternating two bmeshes."""
    for k in range(courses):
        t0, t1 = k / courses, (k + 1) / courses
        a0, b0 = p0.lerp(p3, t0), p1.lerp(p2, t0)
        a1, b1 = p0.lerp(p3, t1), p1.lerp(p2, t1)
        pts = _dedupe([a0, b0, b1, a1])
        if len(pts) < 3:
            continue
        nrm = (pts[1] - pts[0]).cross(pts[2] - pts[0])
        if nrm.length < 1e-9:
            continue
        if nrm.z < 0.0:
            pts.reverse()
        bm = bm_a if (k % 2 == 0) else bm_b
        bm.faces.new([bm.verts.new(p) for p in pts])


def _roof_objects(prefix, loc, faces, courses, mat_a="RoofOrange", mat_b="RoofOrange2"):
    for fname, (p0, p1, p2, p3) in faces:
        bma, bmb = bmesh.new(), bmesh.new()
        _add_strips(bma, bmb, p0, p1, p2, p3, courses)
        for bm, mat, tag in ((bma, mat_a, "A"), (bmb, mat_b, "B")):
            if len(bm.faces) == 0:
                bm.free()
                continue
            nm = f"{prefix}_{fname}_{tag}"
            mesh = _finish_mesh(bm, nm)
            register_obj(mesh, nm, loc, (0.0, 0.0, 0.0), mat)


def build_hip_roof(prefix, cx, cy, z0, w, d, rise, ox=0.4, oy=0.4, courses=6):
    """Orange clay-tile HIP roof (4 slopes, each striped in 2 tile colours)."""
    bw, bd = w / 2.0 + ox, d / 2.0 + oy
    long_x = bw >= bd
    A, B = (bw, bd) if long_x else (bd, bw)
    rl = A - B

    def Lc(x, y, z):
        return Vector((x, y, z)) if long_x else Vector((y, x, z))

    R1, R2 = Lc(-rl, 0.0, rise), Lc(rl, 0.0, rise)
    a, b = Lc(-A, -B, 0.0), Lc(A, -B, 0.0)
    c, dd = Lc(A, B, 0.0), Lc(-A, B, 0.0)
    faces = [("S", (a, b, R2, R1)), ("E", (b, c, R2, R2)),
             ("N", (c, dd, R1, R2)), ("W", (dd, a, R1, R1))]
    _roof_objects(prefix, Vector((cx, cy, z0)), faces, courses)
    if rl > 0.3:
        add_box(f"{prefix}_Ridge", Vector((cx, cy, z0 + rise + 0.05)),
                (2.0 * rl + 0.5, 0.42, 0.26), "RoofRidge",
                rot=(0.0, 0.0, 0.0 if long_x else math.pi / 2.0))
    add_boxes(f"{prefix}_Fascia", Vector((cx, cy, z0)),
              [(0.0, -bd, 0.14, 2.0 * bw, 0.22, 0.30), (0.0, bd, 0.14, 2.0 * bw, 0.22, 0.30),
               (-bw, 0.0, 0.14, 0.22, 2.0 * bd, 0.30), (bw, 0.0, 0.14, 0.22, 2.0 * bd, 0.30)],
              "WallCream")


def build_gable_roof(prefix, cx, cy, z0, w, d, rise, ox=0.3, courses=6, end_boards=True):
    """Orange tiled GABLE roof, ridge along Y, plus white gable-end boards."""
    bw, hd = w / 2.0 + ox, d / 2.0
    R1, R2 = Vector((0.0, -hd, rise)), Vector((0.0, hd, rise))
    faces = [("W", (Vector((-bw, -hd, 0.0)), Vector((-bw, hd, 0.0)), R2, R1)),
             ("E", (Vector((bw, hd, 0.0)), Vector((bw, -hd, 0.0)), R1, R2))]
    _roof_objects(prefix, Vector((cx, cy, z0)), faces, courses)
    add_box(f"{prefix}_Ridge", Vector((cx, cy, z0 + rise + 0.05)),
            (0.42, d + 0.3, 0.26), "RoofRidge")
    add_boxes(f"{prefix}_Fascia", Vector((cx, cy, z0)),
              [(-bw, 0.0, 0.14, 0.22, d + 0.2, 0.30), (bw, 0.0, 0.14, 0.22, d + 0.2, 0.30)],
              "WallCream")
    if end_boards:
        for sgn, tag in ((-1.0, "Front"), (1.0, "Back")):
            add_pitched_gable(f"{prefix}_End{tag}", Vector((cx, cy + sgn * (hd + 0.04), z0)),
                              2.0 * bw, 0.14, rise, "WallCream")


# ---- 4e. tiered dome (unchanged design, now parametrised) ---------------------
def build_tiered_dome(prefix, center_loc, drum_radius, drum_height, dome_height,
                      num_windows=16, is_main=True):
    z = center_loc.z
    add_cylinder(f"{prefix}_Plinth", Vector((center_loc.x, center_loc.y, z + 0.4)),
                 drum_radius * 1.12, 0.8, "WallTrim", segs=24, hollow=True)
    z += 0.8
    add_cylinder(f"{prefix}_DrumCore", Vector((center_loc.x, center_loc.y, z + drum_height / 2.0)),
                 drum_radius * 0.96, drum_height, "WallCream", segs=24, hollow=True)

    for i in range(num_windows):
        ang = (2.0 * math.pi * i) / num_windows
        wx = center_loc.x + math.cos(ang) * (drum_radius * 0.97)
        wy = center_loc.y + math.sin(ang) * (drum_radius * 0.97)
        win_w = (2.0 * math.pi * drum_radius / num_windows) * 0.46
        add_box(f"{prefix}_DrumWin_{i}",
                Vector((wx, wy, z + drum_height * 0.5)),
                (0.12, win_w, drum_height * 0.60), "GlassDark",
                rot=(0.0, 0.0, ang))
        ang_p = ang + (math.pi / num_windows)
        px2 = center_loc.x + math.cos(ang_p) * (drum_radius * 1.02)
        py2 = center_loc.y + math.sin(ang_p) * (drum_radius * 1.02)
        add_box(f"{prefix}_DrumPilaster_{i}",
                Vector((px2, py2, z + drum_height * 0.5)),
                (0.22, win_w * 0.45, drum_height * 0.92), "WallCream",
                rot=(0.0, 0.0, ang_p))

    z += drum_height
    add_cylinder(f"{prefix}_Cornice", Vector((center_loc.x, center_loc.y, z + 0.2)),
                 drum_radius * 1.10, 0.4, "WallTrim", segs=28, hollow=True)
    add_cylinder(f"{prefix}_CorniceRing", Vector((center_loc.x, center_loc.y, z + 0.45)),
                 drum_radius * 1.05, 0.12, "Terracotta", segs=28, hollow=True)
    z += 0.35

    scale_z = dome_height / drum_radius
    add_sphere(f"{prefix}_DomeShell", Vector((center_loc.x, center_loc.y, z)),
               drum_radius, "WallCream", segs=24, rings=12,
               scale=(1.0, 1.0, scale_z), hemisphere=True, is_landmark=is_main)

    num_ribs = 12 if is_main else 8
    for i in range(num_ribs):
        ang = (math.pi * i) / num_ribs
        add_sphere(f"{prefix}_Rib_{i}",
                   Vector((center_loc.x, center_loc.y, z + 0.05)),
                   drum_radius * 1.015, "WallTrim", segs=16, rings=10,
                   scale=(0.035, 1.0, scale_z * 1.01), rot=(0.0, 0.0, ang), hemisphere=True)

    z += dome_height * 0.95
    cup_r, cup_h = drum_radius * 0.26, drum_height * 0.68
    add_cylinder(f"{prefix}_LanternBase", Vector((center_loc.x, center_loc.y, z + 0.2)),
                 cup_r * 1.3, 0.4, "WallTrim", segs=16)
    z += 0.4
    add_cylinder(f"{prefix}_LanternCore", Vector((center_loc.x, center_loc.y, z + cup_h / 2.0)),
                 cup_r * 0.85, cup_h, "GlassDark", segs=12)
    for i in range(8):
        ang = (2.0 * math.pi * i) / 8
        add_cylinder(f"{prefix}_LanternCol_{i}",
                     Vector((center_loc.x + math.cos(ang) * cup_r,
                              center_loc.y + math.sin(ang) * cup_r,
                              z + cup_h / 2.0)),
                     cup_r * 0.14, cup_h, "WallCream", segs=8)
    z += cup_h
    add_cylinder(f"{prefix}_LanternRim", Vector((center_loc.x, center_loc.y, z + 0.12)),
                 cup_r * 1.25, 0.24, "WallTrim", segs=16)
    z += 0.2
    add_sphere(f"{prefix}_LanternCap", Vector((center_loc.x, center_loc.y, z)),
               cup_r * 1.05, "WallCream", segs=14, rings=8,
               scale=(1.0, 1.0, 0.85), hemisphere=True)
    z += cup_r * 0.85
    add_sphere(f"{prefix}_GoldOrb", Vector((center_loc.x, center_loc.y, z + 0.18)),
               cup_r * 0.35, "GoldSpire", segs=10, rings=8)
    add_cone(f"{prefix}_GoldSpire", Vector((center_loc.x, center_loc.y, z + 0.85)),
             cup_r * 0.18, 0.02, 1.35, "GoldSpire", segs=10)


# ---- 4f. Ganesha statue (stands in the OPEN rotunda - nothing above its head) ---
def build_ganesha_statue(center_loc):
    z = center_loc.z
    add_box("Ganesha_Pedestal_Base", Vector((center_loc.x, center_loc.y, z + 0.25)),
            (1.9, 1.6, 0.5), "DarkWood")
    add_box("Ganesha_Pedestal_Core", Vector((center_loc.x, center_loc.y, z + 0.70)),
            (1.6, 1.35, 0.65), "CarvedWood")
    add_box("Ganesha_Pedestal_Cap", Vector((center_loc.x, center_loc.y, z + 1.10)),
            (1.8, 1.5, 0.18), "DarkWood")
    add_cylinder("Ganesha_Lotus_Pad", Vector((center_loc.x, center_loc.y, z + 1.28)),
                 0.68, 0.22, "CarvedWood", segs=16)

    gz = z + 1.40
    cx, cy = center_loc.x, center_loc.y
    add_sphere("Ganesha_LegL", Vector((cx - 0.22, cy, gz + 0.45)),
               0.22, "CarvedWood", scale=(0.8, 0.8, 2.0))
    add_sphere("Ganesha_LegR", Vector((cx + 0.22, cy, gz + 0.45)),
               0.22, "CarvedWood", scale=(0.8, 0.8, 2.0))
    add_sphere("Ganesha_Belly", Vector((cx, cy - 0.06, gz + 1.05)),
               0.46, "CarvedWood", scale=(1.0, 0.88, 1.15), is_landmark=True)
    add_sphere("Ganesha_Chest", Vector((cx, cy, gz + 1.55)),
               0.42, "CarvedWood", scale=(1.15, 0.82, 0.85))
    add_sphere("Ganesha_Head", Vector((cx, cy - 0.04, gz + 2.05)),
               0.34, "CarvedWood")
    add_sphere("Ganesha_EarL", Vector((cx - 0.42, cy + 0.02, gz + 2.05)),
               0.26, "CarvedWood", scale=(0.35, 0.7, 1.1))
    add_sphere("Ganesha_EarR", Vector((cx + 0.42, cy + 0.02, gz + 2.05)),
               0.26, "CarvedWood", scale=(0.35, 0.7, 1.1))
    add_sphere("Ganesha_Trunk1", Vector((cx, cy - 0.30, gz + 1.92)),
               0.14, "CarvedWood", scale=(0.8, 0.8, 1.4))
    add_sphere("Ganesha_Trunk2", Vector((cx + 0.08, cy - 0.36, gz + 1.68)),
               0.11, "CarvedWood", scale=(0.9, 0.8, 1.3))
    add_sphere("Ganesha_TrunkTip", Vector((cx + 0.18, cy - 0.32, gz + 1.56)),
               0.09, "CarvedWood")
    add_cone("Ganesha_Crown1", Vector((cx, cy - 0.02, gz + 2.52)),
             0.28, 0.14, 0.55, "CarvedWood", segs=12)
    add_cone("Ganesha_Crown2", Vector((cx, cy - 0.02, gz + 2.90)),
             0.14, 0.03, 0.35, "CarvedWood", segs=12)

    for side in (-1, 1):
        add_sphere(f"Ganesha_ArmUpper_{side}",
                   Vector((cx + side * 0.55, cy, gz + 1.65)),
                   0.14, "CarvedWood", scale=(1.6, 0.7, 0.7), rot=(0.0, side * 0.5, 0.0))
        add_sphere(f"Ganesha_ArmLower_{side}",
                   Vector((cx + side * 0.50, cy - 0.15, gz + 1.32)),
                   0.13, "CarvedWood", scale=(1.4, 0.7, 0.7), rot=(0.4, 0.0, 0.0))

    # carved flame-arch (prabhavali) behind the statue: radial petals
    for i in range(15):
        ang = -0.25 * math.pi + (1.5 * math.pi * i) / 14
        ax = cx + math.cos(ang) * 0.95
        az = gz + 1.60 + math.sin(ang) * 1.45
        if az >= gz + 0.15:
            add_sphere(f"Ganesha_ArchHalo_{i}",
                       Vector((ax, cy + 0.25, az)),
                       0.15, "DarkWood", segs=8, rings=6,
                       scale=(0.55, 0.25, 1.25), rot=(0.0, math.pi / 2.0 - ang, 0.0))

    # gold stanchions + red velvet rope around the pedestal
    for idx, sc in enumerate([
        Vector((cx - 1.25, cy - 1.15, z)), Vector((cx + 1.25, cy - 1.15, z)),
        Vector((cx - 1.25, cy + 1.15, z)), Vector((cx + 1.25, cy + 1.15, z))
    ]):
        add_cylinder(f"Stanchion_Base_{idx}", sc + Vector((0.0, 0.0, 0.04)),
                     0.22, 0.08, "GoldSpire", segs=14)
        add_cylinder(f"Stanchion_Pole_{idx}", sc + Vector((0.0, 0.0, 0.52)),
                     0.035, 0.95, "GoldSpire", segs=10)
        add_sphere(f"Stanchion_Ball_{idx}", sc + Vector((0.0, 0.0, 1.02)),
                   0.07, "GoldSpire", segs=10, rings=8)

    rope = []
    for r_i in range(9):
        t = r_i / 8.0
        rope.append(((-1.20 + t * 2.40, -1.15, 0.92 - math.sin(t * math.pi) * 0.28),
                     0.045, (1.8, 0.8, 0.8), (0.0, 0.0, 0.0)))
    add_ellipsoids("Velvet_Rope_Front", Vector((cx, cy, z)), rope, "VelvetRed", segs=8, rings=5)


# ---- 4g. plants, trees, furniture ---------------------------------------------
def build_potted_plant(prefix, loc, scale=1.0, pot_mat="PotBlack"):
    r, ph = 0.34 * scale, 0.62 * scale
    add_cylinder(f"{prefix}_Pot", loc + Vector((0.0, 0.0, ph / 2.0)), r, ph, pot_mat, segs=14)
    light, dark = [], []
    n = 8
    for i in range(n):
        a = 2.0 * math.pi * i / n
        it = ((math.cos(a) * 0.12 * scale, math.sin(a) * 0.12 * scale,
               ph + (0.62 + (i % 3) * 0.14) * scale),
              0.30 * scale, (0.35, 0.35, 1.9),
              (-math.sin(a) * 0.45, math.cos(a) * 0.45, 0.0))
        (light if i % 2 == 0 else dark).append(it)
    add_ellipsoids(f"{prefix}_LeavesA", loc.copy(), light, "FoliageLight", segs=8, rings=5)
    add_ellipsoids(f"{prefix}_LeavesB", loc.copy(), dark, "FoliageDark", segs=8, rings=5)


def build_palm_tree(prefix, base_loc, height=6.5):
    add_cone(f"{prefix}_Trunk", base_loc + Vector((0.0, 0.0, height / 2.0)),
             0.26, 0.16, height, "TrunkBrown", segs=8)
    top = base_loc + Vector((0.0, 0.0, height))
    light, dark = [], []
    for i in range(8):
        ang = (2.0 * math.pi * i) / 8
        it = ((math.cos(ang) * 1.35, math.sin(ang) * 1.35, -0.15), 0.85,
              (1.8, 0.42, 0.18), (0.0, 0.38, ang))
        (light if i % 2 == 0 else dark).append(it)
    add_ellipsoids(f"{prefix}_FrondsA", top, light, "FoliageLight", segs=10, rings=6)
    add_ellipsoids(f"{prefix}_FrondsB", top, dark, "FoliageDark", segs=10, rings=6)


def build_canopy_tree(prefix, base_loc, trunk_h=3.2, canopy_r=2.6, is_landmark=False):
    add_cylinder(f"{prefix}_Trunk", base_loc + Vector((0.0, 0.0, trunk_h / 2.0)),
                 0.34, trunk_h, "TrunkBrown", segs=10)
    top = base_loc + Vector((0.0, 0.0, trunk_h + canopy_r * 0.45))
    R = canopy_r
    dark = [((0.0, 0.0, 0.0), R, (1.15, 1.05, 0.78), (0.0, 0.0, 0.0)),
            ((0.2, R * 0.50, R * 0.28), R * 0.70, (1.1, 1.0, 0.75), (0.0, 0.0, 0.0))]
    light = [((R * 0.55, 0.0, R * 0.25), R * 0.72, (1.1, 1.0, 0.75), (0.0, 0.0, 0.0)),
             ((-R * 0.55, 0.2, R * 0.18), R * 0.68, (1.1, 1.0, 0.75), (0.0, 0.0, 0.0))]
    yellow = [((0.0, -R * 0.52, R * 0.15), R * 0.65, (1.1, 1.0, 0.75), (0.0, 0.0, 0.0))]
    o = add_ellipsoids(f"{prefix}_CanopyMain", top, dark, "FoliageDark", segs=12, rings=8)
    if is_landmark and o is not None:
        o["is_landmark"] = True
    add_ellipsoids(f"{prefix}_CanopyLight", top, light, "FoliageLight", segs=10, rings=8)
    add_ellipsoids(f"{prefix}_CanopyYellow", top, yellow, "FoliageYellow", segs=10, rings=8)


def build_shrub(prefix, loc, radius=0.65):
    add_sphere(f"{prefix}_Main", loc, radius, "FoliageDark",
               segs=8, rings=6, scale=(1.0, 1.0, 0.75))
    add_sphere(f"{prefix}_Top", loc + Vector((0.0, 0.0, radius * 0.5)),
               radius * 0.65, "FoliageLight", segs=8, rings=6)


def build_lamp_post(prefix, base_loc):
    add_cylinder(f"{prefix}_Base", base_loc + Vector((0.0, 0.0, 0.2)),
                 0.14, 0.4, "ConcreteGrey", segs=8)
    add_cylinder(f"{prefix}_Pole", base_loc + Vector((0.0, 0.0, 2.5)),
                 0.055, 4.6, "LampPost", segs=8)
    add_sphere(f"{prefix}_Globe", base_loc + Vector((0.0, 0.0, 4.85)),
               0.24, "GoldSpire", segs=10, rings=8)


def build_sofa(prefix, loc, rot_z, length=2.6):
    """Pink floral sofa with red cushions.  Back is on the local -Y side."""
    L = length
    body = [(0.0, 0.0, 0.20, L, 0.90, 0.40),
            (0.0, -0.36, 0.62, L, 0.18, 0.60),
            (-(L / 2.0 - 0.09), 0.0, 0.40, 0.18, 0.90, 0.52),
            ( (L / 2.0 - 0.09), 0.0, 0.40, 0.18, 0.90, 0.52)]
    cush = [(-L / 4.0, -0.22, 0.62, L / 2.0 - 0.24, 0.20, 0.46),
            ( L / 4.0, -0.22, 0.62, L / 2.0 - 0.24, 0.20, 0.46),
            (-L / 4.0,  0.06, 0.46, L / 2.0 - 0.24, 0.60, 0.12),
            ( L / 4.0,  0.06, 0.46, L / 2.0 - 0.24, 0.60, 0.12)]
    with bias_scope(1.0):
        add_boxes(f"{prefix}_Body", loc.copy(), body, "SofaPink", rot=(0.0, 0.0, rot_z))
        add_boxes(f"{prefix}_Cushions", loc.copy(), cush, "SofaCushion", rot=(0.0, 0.0, rot_z))


def build_table_set(prefix, loc):
    """Wooden table with four chairs (as in the reference photo)."""
    parts = [(0.0, 0.0, 0.74, 1.5, 0.9, 0.06)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append((sx * 0.65, sy * 0.36, 0.36, 0.06, 0.06, 0.72))
    with bias_scope(1.0):
        add_boxes(f"{prefix}_Table", loc.copy(), parts, "TableWood")
        for i, (dx, dy, rz) in enumerate([(0.0, -0.78, 0.0), (0.0, 0.78, math.pi),
                                          (-1.05, 0.0, -math.pi / 2.0), (1.05, 0.0, math.pi / 2.0)]):
            ch = [(0.0, 0.0, 0.45, 0.46, 0.46, 0.05), (0.0, -0.21, 0.76, 0.46, 0.05, 0.62)]
            for sx in (-1, 1):
                for sy in (-1, 1):
                    ch.append((sx * 0.20, sy * 0.20, 0.21, 0.04, 0.04, 0.42))
            add_boxes(f"{prefix}_Chair{i}", loc + Vector((dx, dy, 0.0)), ch, "DarkWood",
                      rot=(0.0, 0.0, rz))

# ==============================================================================
# 5. BUILDING ASSEMBLY
# ==============================================================================
FR_F = Frame(0.0, FACADE_Y, math.pi)      # entrance wall centre-plane, +n = outside (-Y)
FR_B = Frame(0.0, -8.8, math.pi)          # outer face of the front block, +n = outside

def _vx(x, y=0.0, z=0.0):
    return Vector((x, y, z))


# ---- 5a. campus ground, plinth, grand staircase ---------------------------------
def build_campus_ground():
    add_box("Campus_Lawn_Base", _vx(0.0, 0.0, -0.15), (130.0, 105.0, 0.3), "LawnGreen")
    add_box("Front_Avenue_Road", _vx(0.0, -34.0, 0.02), (110.0, 10.0, 0.08), "PathwayGrey")
    add_box("Storm_Drain_Channel", _vx(0.0, -28.5, 0.04), (56.0, 0.75, 0.09), "DrainGrate")
    add_box("Front_Path_Center", _vx(0.0, -20.0, 0.05), (5.5, 15.0, 0.10), "PathwayGrey")
    add_box("Side_Path_Left", _vx(-30.0, 0.0, 0.05), (2.0, 36.0, 0.08), "PathwayGrey")
    add_box("Side_Path_Right", _vx(30.0, 0.0, 0.05), (2.0, 36.0, 0.08), "PathwayGrey")
    add_box("Front_Lawn_L", _vx(-24.0, -17.0, 0.05), (20.0, 6.0, 0.15), "LawnGreen")
    add_box("Front_Lawn_R", _vx(24.0, -17.0, 0.05), (20.0, 6.0, 0.15), "LawnGreen")
    num_curbs = 54
    for i in range(num_curbs):
        add_box(f"Curb_Front_{i}", _vx(-54.0 + (i + 0.5) * (108.0 / num_curbs), -38.5, 0.14),
                (108.0 / num_curbs, 0.35, 0.24), "CurbBlack" if i % 2 == 0 else "CurbWhite")
    add_box("Main_Building_Plinth", _vx(0.0, 5.5, PL / 2.0), (62.0, 43.0, PL), "StairStone")
    num_steps = 14
    for s in range(num_steps):
        add_box(f"Grand_Stair_Step_{s + 1}",
                _vx(0.0, -24.5 + (s + 0.5) * (10.0 / num_steps), (s + 0.5) * (PL / num_steps)),
                (26.0 - s * 0.25, (10.0 / num_steps) * 1.05, PL / num_steps),
                "StairStone", is_landmark=(s == 0))


# ---- 5b. interior floor (tiles are drawn first by the painter engine) ----------
def build_floor():
    for i in range(6):
        for j in range(4):
            add_box(f"Floor_Tile_{i}_{j}", _vx(-21.75 + 7.25 * (i + 0.5), -8.2 + 7.3 * (j + 0.5), FZ - 0.05),
                    (7.25, 7.3, 0.10), "MarbleCream")

    def rect(prefix, x0, x1, y0, y1, w=0.12):
        zc = FZ + 0.006
        add_box(f"{prefix}_N", _vx((x0 + x1) / 2.0, y1, zc), (x1 - x0 + w, w, 0.012), "FloorInlay")
        add_box(f"{prefix}_S", _vx((x0 + x1) / 2.0, y0, zc), (x1 - x0 + w, w, 0.012), "FloorInlay")
        add_box(f"{prefix}_E", _vx(x1, (y0 + y1) / 2.0, zc), (w, y1 - y0 + w, 0.012), "FloorInlay")
        add_box(f"{prefix}_W", _vx(x0, (y0 + y1) / 2.0, zc), (w, y1 - y0 + w, 0.012), "FloorInlay")

    rect("Floor_Inlay_Hall1", -11.4, 11.4, -7.7, -1.6)
    rect("Floor_Inlay_Hall2", -10.9, 10.9, -7.2, -2.1)
    rect("Floor_Inlay_Court1", -19.0, 19.0, -0.4, 18.4)
    rect("Floor_Inlay_Court2", -18.5, 18.5, 0.1, 17.9)


# ---- 5c. solid masses: wings, rear range, front bays + their facade detail ------
def _wall_windows(prefix, fr, world_pts, w, rows, cols):
    """Two storeys of surface windows at the given world (x, y) positions."""
    for i, (wx, wy) in enumerate(world_pts):
        u, _n = fr.local(wx, wy)
        build_window(f"{prefix}_G{i}", fr, u, 0.05, 3.65, w, 2.1, rows=rows, cols=cols)
        build_window(f"{prefix}_U{i}", fr, u, 0.05, 7.15, w, 2.3, rows=rows, cols=cols)


def build_masses():
    # --- side wings (long, two storeys) ---
    y0, y1, nch = Y_FRONT_W, Y_REAR, 5
    L = (y1 - y0) / nch
    for side in (-1, 1):
        tag = "Right" if side == 1 else "Left"
        for k in range(nch):
            add_box(f"Pavilion_{tag}_Core" if k == 0 else f"Wing_{tag}_Core_{k}",
                    _vx(side * 26.0, y0 + (k + 0.5) * L, PL + 3.85), (8.5, L, 7.7),
                    "WallCream", is_landmark=(k == 0))
    # --- rear range between the wings ---
    for k in range(6):
        add_box(f"Rear_Core_{k}", _vx(-21.75 + 7.25 * (k + 0.5), 23.0, PL + 3.85),
                (7.25, 4.0, 7.7), "WallCream")
    # --- front bays (left / right of the entrance hall) ---
    for side in (-1, 1):
        tag = "R" if side == 1 else "L"
        add_box(f"Bay_{tag}_Core", _vx(side * 16.875, -4.9, PL + 3.85), (9.75, 7.8, 7.7), "WallCream")

    # --- horizontal bands / terracotta cornices on all outer faces ---
    def bands(prefix, p0, p1, out):
        add_face_band(f"{prefix}_Base", p0, p1, out, 0.14, 0.5, PL + 0.35, "WallTrim")
        add_face_band(f"{prefix}_Mid", p0, p1, out, 0.14, 0.30, F1 - 0.15, "WallTrim")
        add_face_band(f"{prefix}_Cornice", p0, p1, out, 0.16, 0.45, WALL_TOP - 0.22, "Terracotta")

    for side in (-1, 1):
        t = "R" if side == 1 else "L"
        bands(f"Band_Side_{t}", _vx(side * WING_X1, Y_FRONT_W), _vx(side * WING_X1, Y_REAR), _vx(side, 0.0))
        bands(f"Band_WingFront_{t}", _vx(side * WING_X0, Y_FRONT_W), _vx(side * WING_X1, Y_FRONT_W), _vx(0.0, -1.0))
    bands("Band_Rear", _vx(-WING_X1, Y_REAR), _vx(WING_X1, Y_REAR), _vx(0.0, 1.0))
    bands("Band_Front", _vx(-WING_X0, -8.8), _vx(WING_X0, -8.8), _vx(0.0, -1.0))

    # --- windows on the outer side walls of the wings ---
    ys = [-3.0, 3.0, 9.0, 15.0, 21.0]
    _wall_windows("SideWin_R", Frame(WING_X1, 0.0, -math.pi / 2.0), [(WING_X1, y) for y in ys], 2.4, 4, 3)
    _wall_windows("SideWin_L", Frame(-WING_X1, 0.0, math.pi / 2.0), [(-WING_X1, y) for y in ys], 2.4, 4, 3)

    # --- front pavilion faces: tall arched window ---
    for side in (-1, 1):
        t = "R" if side == 1 else "L"
        fr = Frame(0.0, Y_FRONT_W, math.pi)
        u = -side * 26.0
        build_window(f"PavWin_{t}", fr, u, 0.05, 4.4, 3.0, 4.0, rows=5, cols=3)
        add_arch(f"PavArchFrame_{t}", fr, u, 0.03, 6.4, 1.68, 0.12, "WoodFrame")
        add_arch(f"PavArchGlass_{t}", fr, u, 0.07, 6.4, 1.50, 0.06, "GlassDark")
        add_box_f(f"PavArchSill_{t}", fr, u, 0.10, 2.35, 3.6, 0.3, 0.14, "WallTrim")

    # --- rear facade: 2 rows of windows + first-floor balcony ---
    frr = Frame(0.0, Y_REAR, 0.0)
    for i, x in enumerate([-18.9, -13.5, -8.1, -2.7, 2.7, 8.1, 13.5, 18.9]):
        build_window(f"RearWin_G{i}", frr, x, 0.05, 3.65, 2.4, 2.1, rows=4, cols=3)
        build_window(f"RearWin_U{i}", frr, x, 0.05, 7.15, 2.4, 2.3, rows=4, cols=3)
    for k in range(4):
        add_box_f(f"Rear_Balcony_Slab_{k}", frr, -12.15 + 8.1 * k, 1.0, F1 - 0.15, 8.1, 2.0, 0.30, "StairStone")
        add_boxes_f(f"Rear_Balcony_Fascia_{k}", frr, -12.15 + 8.1 * k, 1.95, F1, [(0, 0, -0.38, 8.1, 0.30, 0.76)], "WallCream")
    for ci in range(5):
        add_box_f(f"Rear_Balcony_Corbel_{ci}", frr, -13.5 + ci * 6.75, 0.6, F1 - 0.85, 0.4, 1.2, 0.25, "WallCream")
    build_balcony_railing("Rear_Balcony_Rail", frr.w(-16.2, 1.9), frr.w(16.2, 1.9), F1)
    build_balcony_railing("Rear_Balcony_RailL", frr.w(-16.2, 0.0), frr.w(-16.2, 1.9), F1)
    build_balcony_railing("Rear_Balcony_RailR", frr.w(16.2, 0.0), frr.w(16.2, 1.9), F1)

    # --- rear faces of the front bays (look into the courtyard) ---
    frb = Frame(0.0, Y_HALL_BK, 0.0)
    for side in (-1, 1):
        t = "R" if side == 1 else "L"
        build_window(f"BayRearWin_G{t}", frb, side * 16.9, 0.05, 3.65, 3.2, 2.1, rows=4, cols=4)
        build_window(f"BayRearWin_U{t}", frb, side * 16.9, 0.05, 7.15, 3.2, 2.3, rows=4, cols=4)

    # --- hall: windows on the two side walls (reference: big grid windows + sofas) ---
    for side, fr in ((-1, Frame(-12.0, 0.0, -math.pi / 2.0)), (1, Frame(12.0, 0.0, math.pi / 2.0))):
        t = "R" if side == 1 else "L"
        u, _ = fr.local(side * 12.0, -5.0)
        build_window(f"HallWin_G{t}", fr, u, 0.05, 4.0, 3.4, 2.1, rows=4, cols=4)
        build_window(f"HallWin_U{t}", fr, u, 0.05, 7.15, 3.4, 2.5, rows=4, cols=4)


# ---- 5d. entrance facade with real openings ------------------------------------
def build_front_facade():
    cols = [(-8.0, -4.0, [(2.3, 5.0), (6.0, 8.4)]),
            (-2.0, 2.0, [(PL, 4.9), (6.0, 8.4)]),
            (4.0, 8.0, [(2.3, 5.0), (6.0, 8.4)])]
    wall_with_openings("Facade_Wall", FR_F, -12.0, 12.0, PL, WALL_TOP, 0.6, cols, "WallCream")
    kw = dict(depth=0.72, trim_dn=0.30, trim_depth=0.28)
    for i, (ua, ub, ops) in enumerate(cols):
        u, w = (ua + ub) / 2.0, ub - ua
        for j, (za, zb) in enumerate(ops):
            if za == PL:
                build_door(f"Grand_Entrance_Door", FR_F, u, 0.0, PL, w, zb - za, **kw)
            else:
                build_window(f"Facade_Win_{i}_{j}", FR_F, u, 0.0, (za + zb) / 2.0, w, zb - za,
                             rows=5, cols=6 if j == 1 else 5, **kw)
    # crest + name plate above the door (as in the reference photo)
    n = 0.36
    rot = (math.pi / 2.0, 0.0, 0.0)
    add_cylinder("Sign_Crest_Plate", FR_F.w(0.0, n, 5.55), 0.34, 0.08, "WallCream", segs=20, rot=rot)
    add_cylinder("Sign_Crest_Inner", FR_F.w(0.0, n + 0.02, 5.55), 0.25, 0.08, "Terracotta", segs=20, rot=rot)
    add_cylinder("Sign_Crest_Center", FR_F.w(0.0, n + 0.04, 5.55), 0.13, 0.08, "BoardNavy", segs=16, rot=rot)
    add_box_f("Sign_Gold_Border", FR_F, 0.0, n, 5.12, 1.9, 0.08, 0.30, "GoldSpire")
    add_box_f("Sign_Navy_Board", FR_F, 0.0, n + 0.03, 5.12, 1.74, 0.08, 0.22, "BoardNavy")
    for i in range(3):
        add_box_f(f"Sign_LetterBand_{i}", FR_F, -0.55 + i * 0.55, n + 0.06, 5.12, 0.42, 0.06, 0.10, "WallCream")


# ---- 5e. front loggias: TWO floors of balconies (replace the old windows) -------
def build_loggias():
    xs = [12.2, 15.0, 17.8, 20.6]
    y_col, x0, x1 = -10.9, 10.4, 21.75
    wdt, xc0 = x1 - x0, (x0 + x1) / 2.0
    for side in (-1, 1):
        t = "R" if side == 1 else "L"
        xc = side * xc0
        add_box(f"Loggia_{t}_Slab", _vx(xc, -10.0, F1 - 0.15), (wdt, 2.4, 0.30), "StairStone")
        add_boxes(f"Loggia_{t}_Fascia", _vx(xc, -11.05, F1), [(0, 0, -0.38, wdt, 0.30, 0.76)], "WallCream")
        add_boxes(f"Loggia_{t}_Moulding", _vx(xc, -11.05, F1),
                  [(0, -0.06, 0.05, wdt, 0.42, 0.10), (0, -0.08, -0.80, wdt, 0.40, 0.12)], "WallTrim")
        add_box(f"Loggia_{t}_RoofSlab", _vx(xc, -10.0, WALL_TOP + 0.15), (wdt, 2.4, 0.30), "WallCream")
        add_box(f"Loggia_{t}_RoofEdge", _vx(xc, -11.2, WALL_TOP + 0.05), (wdt, 0.45, 0.5), "WallTrim")
        for i, x in enumerate(xs):
            build_slim_column(f"Loggia_{t}_ColG{i}", _vx(side * x, y_col, PL), F1 - 0.30 - PL, 0.28)
            build_slim_column(f"Loggia_{t}_ColU{i}", _vx(side * x, y_col, F1), WALL_TOP - F1, 0.25)
        build_balcony_railing(f"Loggia_{t}_Rail", _vx(side * 10.5, -11.02), _vx(side * 21.6, -11.02), F1)
        build_balcony_railing(f"Loggia_{t}_RailRet", _vx(side * 10.5, -11.02), _vx(side * 10.5, -8.9), F1)
        # doors / windows behind the balconies
        for k, x in enumerate([13.6, 19.2]):
            u = -side * x
            build_door(f"Loggia_{t}_DoorG{k}", FR_B, u, 0.05, FZ, 1.6, 3.0)
        build_window(f"Loggia_{t}_WinG", FR_B, -side * 16.4, 0.05, 3.7, 1.8, 2.0, rows=4, cols=3)
        for k, x in enumerate([13.6, 16.4, 19.2]):
            build_door(f"Loggia_{t}_DoorU{k}", FR_B, -side * x, 0.05, F1, 1.6, 3.0)


# ---- 5f. portico with 6 columns, entablature, tiled gable roof ------------------
def build_portico():
    col_h = 8.0
    for i, x in enumerate([-9.0, -5.4, -1.8, 1.8, 5.4, 9.0]):
        build_classical_pillar(f"Portico_Pillar_{i + 1}", _vx(x, -16.0, PL), height=col_h,
                               radius=0.48, is_landmark=(i in (0, 5)))
    for side in (-1, 1):
        build_classical_pillar(f"Portico_SidePillar_{side}", _vx(side * 9.0, -12.5, PL),
                               height=col_h, radius=0.44)
    top = PL + col_h
    add_box("Portico_Entablature_Beam", _vx(0.0, -12.4, top + 0.375), (21.2, 8.4, 0.75), "WallCream")
    add_box("Portico_Entablature_Frieze", _vx(0.0, -12.4, top + 0.90), (21.6, 8.6, 0.30), "WallTrim")
    gz = top + 1.05
    build_gable_roof("Portico_Roof", 0.0, -12.35, gz, 21.4, 8.1, 3.3, ox=0.0, end_boards=False)
    add_pitched_gable("Portico_Pediment_Front", _vx(0.0, -16.6, gz - 0.05), 22.4, 0.5, 3.6,
                      "WallCream", is_landmark=True)
    add_pitched_gable("Portico_Pediment_Back", _vx(0.0, -8.3, gz - 0.05), 22.0, 0.2, 3.5, "WallCream")
    add_sphere("Portico_Finial", _vx(0.0, -16.5, gz + 3.7), 0.3, "WallCream", segs=10, rings=8)
    for sx in (-1, 1):
        build_potted_plant(f"Portico_GoldPot_{sx}", _vx(sx * 3.4, -9.6, PL), 1.3, pot_mat="FrameGold")
        build_potted_plant(f"Portico_GoldPotOuter_{sx}", _vx(sx * 7.4, -9.6, PL), 1.3, pot_mat="FrameGold")


# ---- 5g. two-storey galleries around the courtyard ------------------------------
def build_gallery(prefix, fr, length, slab_ranges, cols_u, tall_u, doors):
    G = GAL_D
    for r, (a, b) in enumerate(slab_ranges):
        nch = max(1, int(math.ceil((b - a) / 8.0)))
        sl = (b - a) / nch
        for k in range(nch):
            uc = a + (k + 0.5) * sl
            add_box_f(f"{prefix}_Slab_{r}_{k}", fr, uc, G / 2.0, F1 - 0.15, sl, G, 0.30, "StairStone")
            add_boxes_f(f"{prefix}_Fascia_{r}_{k}", fr, uc, G - 0.05, F1, [(0, 0, -0.38, sl, 0.30, 0.76)], "WallCream")
            add_boxes_f(f"{prefix}_Moulding_{r}_{k}", fr, uc, G - 0.05, F1,
                        [(0, 0.06, 0.05, sl, 0.42, 0.10), (0, 0.08, -0.80, sl, 0.40, 0.12)], "WallTrim")
        p0, p1 = fr.w(a, G - 0.12), fr.w(b, G - 0.12)
        build_balcony_railing(f"{prefix}_Rail_{r}", p0, p1, F1)
    # gallery roof (flat, white)
    nch = max(1, int(math.ceil(length / 8.0)))
    sl = length / nch
    for k in range(nch):
        uc = (k + 0.5) * sl
        add_box_f(f"{prefix}_RoofSlab_{k}", fr, uc, (G + 0.3) / 2.0, WALL_TOP + 0.15, sl, G + 0.3, 0.30, "WallCream")
        add_box_f(f"{prefix}_RoofEdge_{k}", fr, uc, G + 0.25, WALL_TOP + 0.05, sl, 0.40, 0.50, "WallTrim")
    for i, u in enumerate(cols_u):
        build_slim_column(f"{prefix}_ColG{i}", fr.w(u, G - 0.4, PL), F1 - 0.30 - PL, 0.28)
        build_slim_column(f"{prefix}_ColU{i}", fr.w(u, G - 0.4, F1), WALL_TOP - F1, 0.25)
    for i, u in enumerate(tall_u):
        build_slim_column(f"{prefix}_ColTall{i}", fr.w(u, G - 0.4, PL), WALL_TOP - PL, 0.28)
    for i, (u, kind) in enumerate(doors):
        for z0, tag in ((FZ, "G"), (F1, "U")):
            if kind == "door":
                build_door(f"{prefix}_Door{tag}{i}", fr, u, 0.05, z0, 1.5, 2.8)
            else:
                build_window(f"{prefix}_Win{tag}{i}", fr, u, 0.05, z0 + 1.5, 1.5, 1.8, rows=4, cols=3)
    add_face_band(f"{prefix}_WallCornice", fr.w(0, 0), fr.w(length, 0), _vx(fr.nx, fr.ny), 0.12, 0.40, 8.7, "Terracotta")


def build_stair(prefix, side):
    run, nst = 0.30, 12
    rise = (F1 - PL) / nst
    xc = side * 20.95
    parts = []
    for s in range(nst):
        h = (s + 1) * rise
        parts.append((0.0, 0.2 + (s + 0.5) * run, h / 2.0, 1.4, run * 1.02, h))
    add_boxes(f"{prefix}_Steps", _vx(xc, 0.0, PL), parts, "StairStone")
    xr = xc - side * 0.75
    build_stair_railing(f"{prefix}_Rail", _vx(xr, 0.35, PL + rise), _vx(xr, 0.2 + nst * run - 0.15, F1))
    add_box(f"{prefix}_Newel", _vx(xr, 0.2, PL + 0.55), (0.12, 0.12, 1.1), "WoodFrame")


def build_gallery_system():
    L_side, L_rear = 19.7, 43.5
    d = L_side - 0.7
    west_cols = [0.35 + i * d / 6.0 for i in range(1, 7)]
    stair_w = 14.9
    cols_w = [u for u in west_cols if u < stair_w]
    tall_w = [u for u in west_cols if u >= stair_w]
    doors_w = [(1.8, "door"), (5.1, "win"), (8.3, "door"), (11.4, "win")]
    build_gallery("GalW", Frame(-WING_X0, 18.7, -math.pi / 2.0), L_side, [(0.0, stair_w)],
                  cols_w, tall_w, doors_w)
    cols_e = [L_side - u for u in west_cols if u < stair_w]
    tall_e = [L_side - u for u in west_cols if u >= stair_w]
    doors_e = [(L_side - u, k) for (u, k) in doors_w]
    build_gallery("GalE", Frame(WING_X0, -1.0, math.pi / 2.0), L_side, [(L_side - stair_w, L_side)],
                  cols_e, tall_e, doors_e)
    cols_r = [1.95 + 3.3 * j for j in range(13)]
    doors_r = [(3.6 + 3.3 * j, "door" if j % 2 == 0 else "win") for j in range(12)]
    build_gallery("GalR", Frame(WING_X0, Y_REAR_IN, math.pi), L_rear, [(0.0, L_rear)], cols_r, [], doors_r)
    build_stair("Stair_W", -1)
    build_stair("Stair_E", 1)


# ---- 5h. rotunda, dome, Ganesha (open to the dome - no floor above the statue) --
def build_rotunda():
    z = FZ
    cx, cy = RC.x, RC.y
    add_cylinder("Atrium_Platform", _vx(cx, cy, z + 0.06), 6.85, 0.12, "MarbleCream", segs=48)
    add_cylinder("Atrium_Marble_Border", _vx(cx, cy, z + 0.07), 6.30, 0.14, "DarkWood", segs=48)
    add_cylinder("Atrium_Marble_Orange", _vx(cx, cy, z + 0.08), 6.12, 0.16, "Terracotta", segs=48)
    add_cylinder("Atrium_Marble_Inner", _vx(cx, cy, z + 0.09), 5.95, 0.18, "MarbleRed", segs=48)
    for i in range(8):
        ang = (2.0 * math.pi * i) / 8.0 + (math.pi / 8.0)
        build_classical_pillar(f"Atrium_Rotunda_Col_{i + 1}",
                               _vx(cx + math.cos(ang) * 6.2, cy + math.sin(ang) * 6.2, PL),
                               height=WALL_TOP - PL, radius=0.40)
    add_cylinder("Rotunda_Ring_Beam", _vx(cx, cy, WALL_TOP + 0.25), 6.62, 0.5, "WallCream", segs=48, hollow=True)
    add_cylinder("Rotunda_Ring_Band", _vx(cx, cy, WALL_TOP + 0.30), 6.68, 0.16, "Terracotta", segs=48, hollow=True)
    build_tiered_dome("Central_Main_Dome", _vx(cx, cy, WALL_TOP + 0.5), 6.2, 3.8, 6.0,
                      num_windows=18, is_main=True)
    build_ganesha_statue(_vx(cx, cy, z + 0.18))
    for sx in (-1, 1):
        build_potted_plant(f"Ganesha_Pot_{sx}", _vx(cx + sx * 1.85, cy - 0.55, z + 0.18), 1.5)
    for k, a in enumerate([40.0, 70.0, 110.0, 140.0]):          # pots on the rear rim (reference)
        r = math.radians(a)
        build_potted_plant(f"Rim_Pot_{k}", _vx(cx + math.cos(r) * 6.55, cy + math.sin(r) * 6.55, z + 0.12), 1.2)


# ---- 5i. tiled roofs -------------------------------------------------------------
def build_roofs():
    z0 = ROOF_Z
    # Hall roof is pulled back from the central dome: dome plinth front edge is at
    # y = RC.y - 6.2*1.12 = -0.94, so the roof now ends at y = -1.6 (~0.65 m gap)
    # and the dome stands free instead of being fused to the front roof.
    HALL_CY, HALL_D = -5.2, 7.2          # spans y = -8.8 .. -1.6
    add_box("Hall_Roof_Slab", _vx(0.0, HALL_CY, WALL_TOP + 0.15), (24.0, HALL_D, 0.30), "WallCream")
    build_hip_roof("Roof_Hall", 0.0, HALL_CY, z0, 24.0, HALL_D, 2.4, oy=0.0)
    for side in (-1, 1):
        t = "R" if side == 1 else "L"
        build_hip_roof(f"Roof_Bay_{t}", side * 16.875, -4.9, z0, 9.75, 7.8, 2.4)
        # wing: front gable pavilion, dome deck, two hips
        build_gable_roof(f"Roof_WingFront_{t}", side * 26.0, -8.25, z0, 8.5, 4.3, 2.8, ox=0.4)
        add_pitched_gable(f"WingPediment_{t}", _vx(side * 26.0, -10.65, z0 - 0.05), 9.3, 0.45, 2.95, "WallCream")
        add_boxes(f"WingDeckParapet_{t}", _vx(side * 26.0, -2.0, z0),
                  [(0, -4.1, 0.3, 8.5, 0.3, 0.6), (0, 4.1, 0.3, 8.5, 0.3, 0.6),
                   (-4.1, 0, 0.3, 0.3, 8.2, 0.6), (4.1, 0, 0.3, 0.3, 8.2, 0.6)], "WallCream")
        build_hip_roof(f"Roof_WingMid_{t}", side * 26.0, 8.05, z0, 8.5, 11.9, 2.4, oy=0.0)
        build_hip_roof(f"Roof_WingRear_{t}", side * 26.0, 19.3, z0, 8.5, 11.4, 2.4, oy=0.4)
        build_tiered_dome(f"{'Right' if side == 1 else 'Left'}_Side_Dome", _vx(side * 26.0, -2.0, z0 + 0.6),
                          2.8, 2.2, 3.0, num_windows=12, is_main=False)
    build_hip_roof("Roof_Rear", 0.0, 23.0, z0, 43.5, 4.0, 1.7, ox=0.0, oy=0.5)


# ---- 5j. interior furniture ------------------------------------------------------
def build_interior():
    add_box("Reception_Desk_Main", _vx(-17.5, 3.0, FZ + 0.50), (3.2, 1.1, 1.0), "DarkWood")
    add_box("Reception_Desk_Top", _vx(-17.5, 3.0, FZ + 1.02), (3.4, 1.25, 0.08), "MarbleCream")
    for sx in (-1, 1):
        build_sofa(f"Sofa_Facade_{sx}", _vx(sx * 6.0, -7.7, FZ), 0.0, 3.2)
        build_sofa(f"Sofa_Side_A{sx}", _vx(sx * 11.45, -5.6, FZ), sx * math.pi / 2.0, 2.6)
        build_sofa(f"Sofa_Side_B{sx}", _vx(sx * 11.45, -2.6, FZ), sx * math.pi / 2.0, 2.6)
        build_table_set(f"Dining_{sx}", _vx(sx * 17.8, 9.5, FZ))
        build_potted_plant(f"Hall_Pot_{sx}", _vx(sx * 10.6, -7.5, FZ), 1.3)
    # framed certificates (right wall) + portrait (left wall) - reference photos
    fr = Frame(12.0, 0.0, math.pi / 2.0)
    parts = [(-0.55 + c * 0.55, 0.0, r * 0.5, 0.40, 0.04, 0.32) for c in range(3) for r in range(2)]
    add_boxes_f("Wall_Certificates", fr, -2.3, 0.03, 4.0, parts, "FrameGold")
    frl = Frame(-12.0, 0.0, -math.pi / 2.0)
    add_box_f("Wall_Portrait_Frame", frl, 2.3, 0.04, 4.0, 0.95, 0.06, 1.25, "IronBlack")
    add_box_f("Wall_Portrait", frl, 2.3, 0.08, 4.0, 0.75, 0.04, 1.05, "PaintingRed")


# ---- 5k. garden behind Ganesha + side gardens -----------------------------------
def _bed(name, cx, cy, w, d):
    add_box(f"Garden_Bed_{name}", _vx(cx, cy, FZ + 0.11), (w, d, 0.22), "LawnGreen")
    add_box(f"Garden_Border_{name}_N", _vx(cx, cy + d / 2.0, FZ + 0.12), (w + 0.4, 0.22, 0.24), "StairStone")
    add_box(f"Garden_Border_{name}_S", _vx(cx, cy - d / 2.0, FZ + 0.12), (w + 0.4, 0.22, 0.24), "StairStone")
    add_box(f"Garden_Border_{name}_W", _vx(cx - w / 2.0, cy, FZ + 0.12), (0.22, d, 0.24), "StairStone")
    add_box(f"Garden_Border_{name}_E", _vx(cx + w / 2.0, cy, FZ + 0.12), (0.22, d, 0.24), "StairStone")


def build_courtyard_garden():
    _bed("Rear", 0.0, 16.2, 32.0, 4.6)
    _bed("L", -12.2, 7.5, 7.2, 9.0)
    _bed("R", 12.2, 7.5, 7.2, 9.0)
    gz = FZ + 0.22
    for i, (x, y, h) in enumerate([(-13.5, 16.4, 7.8), (-5.0, 16.8, 8.4), (4.5, 16.4, 7.6), (13.0, 16.8, 8.2)]):
        build_palm_tree(f"Garden_Palm_{i}", _vx(x, y, gz), h)
    build_canopy_tree("Garden_Tree_0", _vx(-9.0, 15.2, gz), 2.8, 2.3)
    build_canopy_tree("Garden_Tree_1", _vx(9.5, 15.0, gz), 2.8, 2.3)
    for i, x in enumerate(range(-14, 15, 4)):
        build_shrub(f"Garden_Shrub_{i}", _vx(x, 14.4, gz + 0.3), 0.6)
    for sx in (-1, 1):
        build_palm_tree(f"Side_Palm_{sx}", _vx(sx * 12.2, 5.0, gz), 7.2)
        build_canopy_tree(f"Court_Tree_{sx}", _vx(sx * 12.2, 9.5, gz), 2.6, 2.1)
        for i, y in enumerate([3.5, 7.0, 11.0]):
            build_shrub(f"Court_Shrub_{sx}_{i}", _vx(sx * 10.0, y, gz + 0.3), 0.5)


# ---- 5l. campus landscaping ------------------------------------------------------
def build_campus_landscape():
    front = [("Tree_FL1", -16.5, -20.0, 3.2, 2.8), ("Tree_FL2", -20.5, -21.5, 3.5, 3.1),
             ("Tree_FL3", -24.5, -20.5, 3.0, 2.7), ("Tree_FL4", -28.5, -21.0, 3.6, 3.2),
             ("Tree_FL5", -32.5, -20.0, 3.3, 2.9), ("Tree_FR1", 16.5, -20.0, 3.2, 2.8),
             ("Tree_FR2", 20.5, -21.5, 3.5, 3.1), ("Tree_FR3", 24.5, -20.5, 3.0, 2.7),
             ("Tree_FR4", 28.5, -21.0, 3.6, 3.2), ("Tree_FR5", 32.5, -20.0, 3.3, 2.9)]
    for nm, x, y, th, cr in front:
        build_canopy_tree(nm, _vx(x, y, 0.0), th, cr, is_landmark=nm in ("Tree_FL1", "Tree_FR1"))
    for nm, x, y in [("Palm_FL", -38.0, -22.0), ("Palm_FR", 38.0, -22.0),
                     ("Palm_BL", -38.0, 30.0), ("Palm_BR", 38.0, 30.0)]:
        build_palm_tree(nm, _vx(x, y, 0.0), 7.0)
    for side in (-1, 1):
        t = "L" if side == -1 else "R"
        add_box(f"Side_Garden_{t}", _vx(side * 38.0, 5.0, 0.0), (8.0, 30.0, 0.18), "LawnGreen")
        for ti, ty in enumerate([-6.0, 2.0, 10.0, 18.0]):
            build_canopy_tree(f"Side_Tree_{t}_{ti}", _vx(side * 38.0, ty, 0.0), 3.0, 2.4)
        for si, (sx, sy) in enumerate([(side * 35.0, -3.0), (side * 35.0, 4.0), (side * 41.0, 1.0)]):
            build_shrub(f"Side_Shrub_{t}_{si}", _vx(sx, sy, 0.25), 0.6)
    add_box("Rear_Lawn_1", _vx(0.0, 36.0, 0.0), (64.0, 18.0, 0.18), "LawnGreen")
    for ri, rx in enumerate([-25.0, -15.0, -5.0, 5.0, 15.0, 25.0]):
        build_canopy_tree(f"Rear_Tree_{ri}", _vx(rx, 33.0, 0.0), 3.5, 3.0)
    for fi, (fx, fy) in enumerate([(-10.0, 29.5), (0.0, 29.5), (10.0, 29.5), (-18.0, 30.5), (18.0, 30.5)]):
        add_box(f"Flower_Bed_{fi}", _vx(fx, fy, 0.12), (2.2, 1.4, 0.22),
                "FlowerYellow" if fi % 2 == 0 else "FlowerRed")
    for li, lx in enumerate([-20.0, -10.0, 0.0, 10.0, 20.0]):
        build_lamp_post(f"Lamp_{li}", _vx(lx, -30.0, 0.0))
    for si, sx in enumerate([-3.5, 3.5]):
        for sy in [-23.0, -19.0, -15.0]:
            build_shrub(f"Path_Shrub_{si}_{int(sy)}", _vx(sx, sy, 0.20), 0.5)


# ==============================================================================
# 9. MASTER PROCEDURAL GENERATOR
# ==============================================================================
def build_alliance_admin_block():
    global MAIN_COLLECTION
    MAT_CACHE.clear()
    for obj in list(bpy.data.objects):
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
        except Exception:
            pass
    for mesh in list(bpy.data.meshes):
        try:
            bpy.data.meshes.remove(mesh, do_unlink=True)
        except Exception:
            pass
    for mat in list(bpy.data.materials):
        try:
            bpy.data.materials.remove(mat, do_unlink=True)
        except Exception:
            pass
    for col in list(bpy.data.collections):
        if col.name.startswith("Alliance"):
            try:
                bpy.data.collections.remove(col)
            except Exception:
                pass

    MAIN_COLLECTION = bpy.data.collections.new("Alliance_Admin_Block_Hierarchy")
    bpy.context.scene.collection.children.link(MAIN_COLLECTION)

    build_campus_ground()      # ground-level slabs first (painter draws them first)
    build_floor()
    build_masses()
    build_front_facade()
    build_loggias()
    build_portico()
    build_gallery_system()
    build_rotunda()
    build_roofs()
    build_interior()
    build_courtyard_garden()
    build_campus_landscape()
    bpy.context.view_layer.update()
    print("Alliance University Admin Block built successfully.")
    print(f"Objects: {len(MAIN_COLLECTION.objects)}")


# ==============================================================================
# 10. PAINTER'S ALGORITHM GPU ENGINE
# ==============================================================================
def get_uniform_color_shader():
    try:
        return gpu.shader.from_builtin('UNIFORM_COLOR')
    except Exception:
        return gpu.shader.from_builtin('3D_UNIFORM_COLOR')

SHADER_3D = get_uniform_color_shader()
SHADER_2D = get_uniform_color_shader()

# objects drawn FIRST (ground-level slabs that everything else stands on)
BG_KEYS = ("Lawn", "Road", "Drain", "Curb", "Path_Center", "Side_Path", "Main_Building_Plinth",
           "Floor_Tile", "Floor_Inlay", "Atrium_Platform", "Atrium_Marble", "Garden_Bed",
           "Side_Garden")

def cache_scene_batches_for_painter():
    bpy.context.view_layer.update()
    STATE.render_items.clear()
    STATE.total_polygons = 0
    sun_dir = Vector((0.45, -0.65, 0.62)).normalized()

    for obj in MAIN_COLLECTION.objects:
        if obj.type != 'MESH':
            continue
        mesh = obj.data
        mesh.calc_loop_triangles()
        verts_world = [obj.matrix_world @ v.co for v in mesh.vertices]
        if not verts_world:
            continue

        bbox_min = Vector((min(v.x for v in verts_world),
                           min(v.y for v in verts_world),
                           min(v.z for v in verts_world)))
        bbox_max = Vector((max(v.x for v in verts_world),
                           max(v.y for v in verts_world),
                           max(v.z for v in verts_world)))
        world_center = (bbox_min + bbox_max) * 0.5
        indices = [tuple(lt.vertices) for lt in mesh.loop_triangles]
        if not indices:
            continue

        STATE.total_polygons += len(indices)
        batch = batch_for_shader(SHADER_3D, 'TRIS', {"pos": verts_world}, indices=indices)

        rot3 = obj.matrix_world.to_3x3().normalized()
        shade = 0.72 + 0.28 * max(0.0,
            sum((rot3 @ p.normal).dot(sun_dir) for p in mesh.polygons) / max(1, len(mesh.polygons)))
        base_col = obj.get("painter_color", (0.9, 0.9, 0.9, 1.0))
        is_bg = any(k in obj.name for k in BG_KEYS)

        STATE.render_items.append({
            "name":         obj.get("landmark_label", obj.name),
            "world_center": world_center,
            "batch":        batch,
            "color":        (min(1.0, base_col[0] * shade),
                             min(1.0, base_col[1] * shade),
                             min(1.0, base_col[2] * shade), 1.0),
            "poly_count":   len(indices),
            "is_landmark":  bool(obj.get("is_landmark", False)),
            "dist":         0.0,
            "bias":         float(obj.get("painter_bias", 0.0)),
            "is_bg":        is_bg,
        })

    STATE.objects_sorted    = len(STATE.render_items)
    STATE.scrambled_indices = list(range(STATE.objects_sorted))
    random.seed(42)
    random.shuffle(STATE.scrambled_indices)


def draw_callback_3d():
    if not STATE.is_running or not STATE.render_items:
        return
    region_3d = bpy.context.region_data
    if not region_3d:
        return

    view_inv = region_3d.view_matrix.inverted()
    cam_pos  = view_inv.translation
    STATE.cam_pos     = cam_pos.copy()
    STATE.cam_forward = (view_inv.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
    t0 = time.perf_counter()

    for item in STATE.render_items:
        item["dist"] = (9999999.0 if item["is_bg"]
                        else (item["world_center"] - cam_pos).length)

    if STATE.painter_sort_on:
        # far-first (stable, so ground slabs keep their creation order);
        # detail objects (windows, railings) carry a small bias so they land on top of their wall
        ordered_items = sorted(STATE.render_items,
                               key=lambda x: x["dist"] - (0.0 if x["is_bg"] else x["bias"]),
                               reverse=True)
    else:
        ordered_items = [STATE.render_items[i] for i in STATE.scrambled_indices]

    STATE.sort_time_ms = (time.perf_counter() - t0) * 1000.0
    STATE.sorted_landmarks = sorted(
        [it for it in STATE.render_items if it["is_landmark"]],
        key=lambda x: x["dist"])[:9]

    if STATE.z_buffer_on:
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(True)
    else:
        gpu.state.depth_test_set('NONE')
        gpu.state.depth_mask_set(False)

    gpu.state.blend_set('ALPHA')
    gpu.state.face_culling_set('NONE')

    SHADER_3D.bind()
    drawn_polys = 0
    visible_items = [it for it in ordered_items if not it["is_bg"]]
    max_d = max((it["dist"] for it in visible_items), default=100.0)
    min_d = min((it["dist"] for it in visible_items), default=1.0)
    span_d = max(0.001, max_d - min_d)

    num_to_draw = int(len(ordered_items) * STATE.draw_progress)
    for idx in range(num_to_draw):
        item = ordered_items[idx]
        drawn_polys += item["poly_count"]
        if STATE.depth_shading_on and not item["is_bg"]:
            t_depth = min(1.0, (item["dist"] - min_d) / span_d)
            SHADER_3D.uniform_float("color",
                (0.08 * (1.0 - t_depth),
                 0.88 * (1.0 - t_depth) + 0.18 * t_depth,
                 0.25 * (1.0 - t_depth) + 0.92 * t_depth,
                 1.0))
        else:
            SHADER_3D.uniform_float("color", item["color"])
        item["batch"].draw(SHADER_3D)

    STATE.drawn_polygons = drawn_polys
    gpu.state.depth_mask_set(True)
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.blend_set('NONE')


# ==============================================================================
# 11. 2D HUD OVERLAY
# ==============================================================================
def draw_2d_rect(x, y, w, h, color):
    verts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    batch_for_shader(SHADER_2D, 'TRI_FAN', {"pos": verts}).draw(SHADER_2D)

def draw_text(font_id, x, y, text, size=13, color=(1.0, 1.0, 1.0, 1.0)):
    try:
        blf.size(font_id, size)
    except TypeError:
        blf.size(font_id, size, 72)
    blf.color(font_id, *color)
    blf.position(font_id, x, y, 0)
    blf.draw(font_id, text)

def draw_callback_2d():
    if not STATE.is_running or not bpy.context.region:
        return
    font_id  = 0
    px       = 18
    panel_h  = 590
    py       = bpy.context.region.height - panel_h - 36
    panel_w  = 335

    gpu.state.blend_set('ALPHA')
    SHADER_2D.bind()
    SHADER_2D.uniform_float("color", (0.06, 0.09, 0.14, 0.90))
    draw_2d_rect(px, py, panel_w, panel_h, (0.06, 0.09, 0.14, 0.90))

    cy = py + panel_h - 28
    draw_text(font_id, px + 14, cy, "Painter's Algorithm Engine",
              size=16, color=(0.30, 0.78, 0.95, 1.0)); cy -= 22
    draw_text(font_id, px + 14, cy,
              f"Scene: {STATE.current_scene_name}",
              size=12, color=(1.0, 0.85, 0.40, 1.0)); cy -= 18

    sort_col = (0.35, 0.92, 0.45, 1.0) if STATE.painter_sort_on else (1.0, 0.35, 0.35, 1.0)
    draw_text(font_id, px + 14, cy,
              f"[Space] CPU Sort    : {'ON (Far-First)' if STATE.painter_sort_on else 'OFF (Scrambled!)'}",
              size=12, color=sort_col); cy -= 18
    zbuf_col = (1.0, 0.78, 0.25, 1.0) if not STATE.z_buffer_on else (0.35, 0.92, 0.45, 1.0)
    draw_text(font_id, px + 14, cy,
              f"[Z] Z-Buffer (GPU) : {'ENABLED' if STATE.z_buffer_on else 'DISABLED (Always)'}",
              size=12, color=zbuf_col); cy -= 18
    draw_text(font_id, px + 14, cy,
              f"[G] Depth shading  : {'ON' if STATE.depth_shading_on else 'off'}",
              size=12); cy -= 18
    draw_text(font_id, px + 14, cy,
              f"[-/=] Draw Prog    : {int(STATE.draw_progress * 100)}%",
              size=12); cy -= 20

    draw_text(font_id, px + 14, cy,
              "MOVEMENT CONTROLS", size=13, color=(0.30, 0.78, 0.95, 1.0)); cy -= 18
    draw_text(font_id, px + 14, cy,
              "WASD: Fly  Q/E: Down/Up",
              size=11, color=(0.9, 0.9, 0.6, 1.0)); cy -= 16
    draw_text(font_id, px + 14, cy,
              "Mid Mouse Hold+Drag: Look",
              size=11, color=(0.9, 0.9, 0.6, 1.0)); cy -= 16
    draw_text(font_id, px + 14, cy,
              "[1-6] Scene Presets | ESC: Stop",
              size=11, color=(0.9, 0.9, 0.6, 1.0)); cy -= 22

    draw_text(font_id, px + 14, cy,
              f"Polys: {STATE.total_polygons} | Sorted: {STATE.objects_sorted}",
              size=11, color=(0.6, 0.6, 0.7, 1.0)); cy -= 16
    draw_text(font_id, px + 14, cy,
              f"Sort: {STATE.sort_time_ms:.2f}ms",
              size=11, color=(0.6, 0.6, 0.7, 1.0)); cy -= 26

    draw_text(font_id, px + 14, cy,
              "Object depth (z, metres)", size=15,
              color=(0.30, 0.78, 0.95, 1.0)); cy -= 20
    for lm in STATE.sorted_landmarks:
        label = lm["name"].replace("_", " ")[:26]
        draw_text(font_id, px + 14, cy, label, size=12)
        dist_str = "999.0" if lm["dist"] > 90000 else f"{lm['dist']:5.2f}"
        draw_text(font_id, px + panel_w - 62, cy, dist_str,
                  size=12, color=(0.30, 0.78, 0.95, 1.0)); cy -= 18

    gpu.state.blend_set('NONE')


# ==============================================================================
# 12. SCENE PRESET CAMERAS (Keys 1-6)  -  rotations fixed (2/3/4 used to look straight down)
# ==============================================================================
def _look(yaw_deg, pitch_deg=90.0):
    """Blender viewport rotation: pitch 90 = horizontal, yaw 0 looks toward +Y, 180 toward -Y."""
    return (Quaternion(Vector((0.0, 0.0, 1.0)), math.radians(yaw_deg)) @
            Quaternion(Vector((1.0, 0.0, 0.0)), math.radians(pitch_deg)))

SCENE_PRESETS = {
    '1': {"name": "Entrance (Front)",
          "location": Vector((0.0, -52.0, 5.0)), "rotation": _look(0.0, 88.0)},
    '2': {"name": "Inside Hall -> Ganesha",
          "location": Vector((0.0, -6.5, PL + 1.8)), "rotation": _look(0.0, 90.0)},
    '3': {"name": "Ganesha Close-Up",
          "location": Vector((0.0, 1.6, PL + 2.8)), "rotation": _look(0.0, 86.0)},
    '4': {"name": "Ganesha -> Entrance (Looking Outside)",
          "location": Vector((0.0, 3.4, PL + 2.4)), "rotation": _look(180.0, 90.0)},
    '5': {"name": "Aerial Top-Down",
          "location": Vector((0.0, 5.5, 95.0)), "rotation": Quaternion((1.0, 0.0, 0.0, 0.0))},
    '6': {"name": "Rear of Building",
          "location": Vector((0.0, 62.0, 7.0)), "rotation": _look(180.0, 88.0)},
}

def apply_scene_preset(r3d, key_str, context):
    preset = SCENE_PRESETS.get(key_str)
    if not preset:
        return
    r3d.view_location = preset["location"].copy()
    r3d.view_rotation = preset["rotation"].normalized()
    r3d.view_distance = 0.1
    STATE.current_scene_name = preset["name"]
    if context.area:
        context.area.tag_redraw()


# ==============================================================================
# 13. INTERACTIVE MODAL OPERATOR (WASD + Mouse Look)
# ==============================================================================
class VIEW3D_OT_alliance_painter_controller(bpy.types.Operator):
    bl_idname = "view3d.alliance_painter_controller"
    bl_label  = "Painter's Algorithm Controller"

    def _finish(self, context):
        try:
            context.window_manager.event_timer_remove(self._timer)
        except Exception:
            pass

    def modal(self, context, event):
        if not STATE.is_running:
            self._finish(context)
            return {'FINISHED'}

        r3d = None
        if context.space_data and context.space_data.type == 'VIEW_3D':
            r3d = context.space_data.region_3d

        if event.type == 'MIDDLEMOUSE':
            if event.value == 'PRESS':
                self.mouse_look_active = True
                self.last_mouse_x = event.mouse_x
                self.last_mouse_y = event.mouse_y
            elif event.value == 'RELEASE':
                self.mouse_look_active = False
            return {'RUNNING_MODAL'}

        if event.type == 'MOUSEMOVE' and self.mouse_look_active and r3d:
            dx = event.mouse_x - self.last_mouse_x
            dy = event.mouse_y - self.last_mouse_y
            self.last_mouse_x = event.mouse_x
            self.last_mouse_y = event.mouse_y
            sensitivity = 0.003
            world_up = Vector((0.0, 0.0, 1.0))
            yaw   = Quaternion(world_up, -dx * sensitivity)
            right = r3d.view_rotation @ Vector((1.0, 0.0, 0.0))
            pitch = Quaternion(right, dy * sensitivity)
            r3d.view_rotation = (yaw @ pitch @ r3d.view_rotation).normalized()
            if context.area:
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        if event.type in {'W', 'A', 'S', 'D', 'Q', 'E'}:
            if event.value == 'PRESS':
                self.keys[event.type] = True
            elif event.value == 'RELEASE':
                self.keys[event.type] = False
            return {'RUNNING_MODAL'}

        if event.type == 'TIMER' and r3d:
            speed = 0.35
            move  = Vector((0.0, 0.0, 0.0))
            if self.keys.get('W', False): move.z -= speed
            if self.keys.get('S', False): move.z += speed
            if self.keys.get('A', False): move.x -= speed
            if self.keys.get('D', False): move.x += speed
            if move.length > 0:
                r3d.view_location += r3d.view_rotation @ move
            if self.keys.get('E', False):
                r3d.view_location.z += speed
            if self.keys.get('Q', False):
                r3d.view_location.z -= speed
            if move.length > 0 or self.keys.get('E', False) or self.keys.get('Q', False):
                if context.area:
                    context.area.tag_redraw()
            return {'PASS_THROUGH'}

        if event.value == 'PRESS':
            key = event.type
            scene_key_map = {
                'ONE': '1', 'TWO': '2', 'THREE': '3',
                'FOUR': '4', 'FIVE': '5', 'SIX': '6',
                'NUMPAD_1': '1', 'NUMPAD_2': '2', 'NUMPAD_3': '3',
                'NUMPAD_4': '4', 'NUMPAD_5': '5', 'NUMPAD_6': '6',
            }
            if key in scene_key_map and r3d:
                apply_scene_preset(r3d, scene_key_map[key], context)
                return {'RUNNING_MODAL'}

            if key in {'SPACE', 'P'}:
                STATE.painter_sort_on = not STATE.painter_sort_on
            elif key == 'Z':
                STATE.z_buffer_on = not STATE.z_buffer_on
            elif key == 'G':
                STATE.depth_shading_on = not STATE.depth_shading_on
            elif key == 'L':
                STATE.labels_on = not STATE.labels_on
            elif key in {'MINUS', 'NUMPAD_MINUS'}:
                STATE.draw_progress = max(0.05, round(STATE.draw_progress - 0.05, 2))
            elif key in {'EQUAL', 'PLUS', 'NUMPAD_PLUS'}:
                STATE.draw_progress = min(1.0, round(STATE.draw_progress + 0.05, 2))
            elif key == 'ESC':
                stop_painter_engine()
                self._finish(context)
                return {'FINISHED'}

            if context.area:
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        stop_painter_engine()
        cache_scene_batches_for_painter()
        STATE.is_running = True
        STATE.current_scene_name = "Free Fly"
        STATE.handle_3d = bpy.types.SpaceView3D.draw_handler_add(
            draw_callback_3d, (), 'WINDOW', 'POST_VIEW')
        STATE.handle_2d = bpy.types.SpaceView3D.draw_handler_add(
            draw_callback_2d, (), 'WINDOW', 'POST_PIXEL')
        self.keys = {'W': False, 'A': False, 'S': False, 'D': False, 'Q': False, 'E': False}
        self.mouse_look_active = False
        self.last_mouse_x = 0
        self.last_mouse_y = 0
        self._timer = context.window_manager.event_timer_add(0.016, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}


def stop_painter_engine():
    STATE.is_running = False
    if STATE.handle_3d:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(STATE.handle_3d, 'WINDOW')
        except Exception:
            pass
    if STATE.handle_2d:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(STATE.handle_2d, 'WINDOW')
        except Exception:
            pass
    STATE.handle_3d = None
    STATE.handle_2d = None


# ==============================================================================
# 14. VIEWPORT SETUP & AUTO-LAUNCH
# ==============================================================================
def setup_viewport_and_force_fullscreen():
    try:
        bpy.utils.register_class(VIEW3D_OT_alliance_painter_controller)
    except Exception:
        pass

    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type  = 'SOLID'
                        space.shading.light = 'FLAT'
                        space.overlay.show_floor   = False
                        space.overlay.show_axis_x  = False
                        space.overlay.show_axis_y  = False
                        if space.region_3d:
                            space.region_3d.view_location = SCENE_PRESETS['1']["location"].copy()
                            space.region_3d.view_rotation = SCENE_PRESETS['1']["rotation"].copy()
                            space.region_3d.view_distance = 0.1

                ctx = bpy.context.copy()
                ctx['window'] = window
                ctx['screen'] = window.screen
                ctx['area']   = area
                ctx['region'] = area.regions[-1]
                with bpy.context.temp_override(**ctx):
                    bpy.ops.screen.screen_full_area(use_hide_panels=True)
                    bpy.ops.view3d.alliance_painter_controller('INVOKE_DEFAULT')
                return


# ==============================================================================
if __name__ == "__main__":
    build_alliance_admin_block()
    setup_viewport_and_force_fullscreen()
