"""
Kimodo Blender Bridge — Retarget (prototype)
=============================================
Blender-native Mixamo <-> SOMA retarget.

Covers the full loop the user asked for (Mixamo -> SOMA -> Mixamo):

  Mixamo -> SOMA  : pose a Mixamo rig, convert to Kimodo fullbody constraint
                    (see `soma_joint_rots_mixamo_aware`, used by constraints.py)
  SOMA -> Mixamo  : bake Kimodo_Source BVH motion onto a Mixamo character
                    (see `KIMODO_OT_RetargetSomaToMixamo`)

Limitations (prototype):
  - SOMA 30-joint only. Neck2 / Jaw / Eyes / finger ends have no Mixamo
    counterpart and are dropped (identity).
  - Assumes armatures roughly upright; root scale estimated from
    Hips->Head rest distance.
  - Only Hips location is transferred (scaled); other bones rotation-only.
"""

from __future__ import annotations

import math

import bpy
import mathutils
from bpy.props import BoolProperty, IntProperty, StringProperty
from bpy.types import Object, Operator, Panel


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------

def _norm(name: str) -> str:
    """Normalize a bone name for comparison: lowercase, strip namespace,
    drop _, -, spaces."""
    n = name.lower()
    if ":" in n:
        n = n.split(":")[-1]
    for ch in ("_", "-", " ", "."):
        n = n.replace(ch, "")
    return n


# SOMA (30-joint, see constraints.SOMA_JOINT_ORDER) -> Mixamo candidate names
# (normalized form, without prefix). First match wins.
SOMA_TO_MIXAMO_CANDIDATES: dict[str, list[str]] = {
    "hips":          ["hips", "hip", "pelvis"],
    "spine1":        ["spine"],
    "spine2":        ["spine1"],
    "chest":         ["spine2", "chest"],
    "neck1":         ["neck", "neck1"],
    # "neck2" intentionally unmapped (Mixamo has a single Neck)
    "head":          ["head"],
    "leftshoulder":  ["leftshoulder", "leftclavicle", "leftcollar"],
    "leftarm":       ["leftarm", "leftupperarm"],
    "leftforearm":   ["leftforearm", "leftelbow", "leftlowerarm"],
    "lefthand":      ["lefthand", "leftwrist", "lefthandwrist"],
    "rightshoulder": ["rightshoulder", "rightclavicle", "rightcollar"],
    "rightarm":      ["rightarm", "rightupperarm"],
    "rightforearm":  ["rightforearm", "rightelbow", "rightlowerarm"],
    "righthand":     ["righthand", "rightwrist"],
    "leftleg":       ["leftupleg", "leftthigh", "lefthip", "leftupperleg"],
    "leftshin":      ["leftleg", "leftshin", "leftknee", "leftcalf", "leftlowerleg"],
    "leftfoot":      ["leftfoot", "leftankle"],
    "lefttoebase":   ["lefttoebase", "lefttoe", "lefttoes", "leftball"],
    "rightleg":      ["rightupleg", "rightthigh", "righthip", "rightupperleg"],
    "rightshin":     ["rightleg", "rightshin", "rightknee", "rightcalf", "rightlowerleg"],
    "rightfoot":     ["rightfoot", "rightankle"],
    "righttoebase":  ["righttoebase", "righttoe", "righttoes", "rightball"],
}

# SOMA joints with no Mixamo counterpart -> baked as identity / skipped.
SOMA_UNMAPPED = {
    "neck2", "jaw", "lefteye", "righteye",
    "lefthandthumbend", "lefthandmiddleend",
    "righthandthumbend", "righthandmiddleend",
}


def _name_index(arm: Object) -> dict[str, str]:
    """normalized bone name -> actual pose bone name (first wins)."""
    idx: dict[str, str] = {}
    for pb in arm.pose.bones:
        n = _norm(pb.name)
        if n not in idx:
            idx[n] = pb.name
    return idx


def find_mixamo_bone(target_arm: Object, soma_key: str):
    """Return the target pose bone matching a SOMA joint key, or None."""
    cands = SOMA_TO_MIXAMO_CANDIDATES.get(soma_key.lower())
    if not cands:
        return None
    idx = _name_index(target_arm)
    for c in cands:
        if c in idx:
            return target_arm.pose.bones.get(idx[c])
    return None


def find_soma_bone_for_mixamo(source_arm: Object, soma_key: str):
    """Return the source (SOMA) pose bone for a SOMA joint key, or None."""
    # SOMA bones are named exactly ("Hips", "Spine1", ...) but match
    # case-insensitively to be safe.
    want = _norm(soma_key)
    idx = _name_index(source_arm)
    if want in idx:
        return source_arm.pose.bones.get(idx[want])
    return None


def is_mixamo_armature(arm: Object) -> bool:
    if arm is None or arm.type != 'ARMATURE':
        return False
    idx = _name_index(arm)
    return "leftupleg" in idx and "spine" in idx


def is_soma_armature(arm: Object) -> bool:
    if arm is None or arm.type != 'ARMATURE':
        return False
    idx = _name_index(arm)
    return "spine1" in idx and "leftshin" in idx and "leftupleg" not in idx


def detect_rig(arm: Object) -> str:
    if arm is None or arm.type != 'ARMATURE':
        return "none"
    if is_soma_armature(arm):
        return "soma"
    if is_mixamo_armature(arm):
        return "mixamo"
    return "unknown"


def build_pairs(source_arm: Object, target_arm: Object):
    """List of (soma_key, src_pb, tgt_pb) for every mappable joint."""
    pairs = []
    for soma_key in SOMA_TO_MIXAMO_CANDIDATES:
        src_pb = find_soma_bone_for_mixamo(source_arm, soma_key)
        tgt_pb = find_mixamo_bone(target_arm, soma_key)
        if src_pb is not None and tgt_pb is not None:
            pairs.append((soma_key, src_pb, tgt_pb))
    return pairs


# ---------------------------------------------------------------------------
# Mixamo -> SOMA (for fullbody constraints)
# ---------------------------------------------------------------------------

def _blender_delta_arm_3x3(arm: Object, pb) -> mathutils.Matrix:
    """Pose-vs-rest delta rotation in armature space (3x3).

    Rest-invariant: independent of how the BVH importer oriented bones.
    Same formulation as constraints.get_armature_joint_rots.
    """
    rest_arm = pb.bone.matrix_local.to_3x3()
    pose_arm = pb.matrix.to_3x3()
    return pose_arm @ rest_arm.transposed()


def soma_joint_rots_mixamo_aware(armature_obj: Object, joint_order, joint_parents):
    """SOMA local joint rotations (Kimodo axis-angle) from any armature.

    Tries the exact SOMA bone name first; falls back to the Mixamo
    counterpart via SOMA_TO_MIXAMO_CANDIDATES. Unmapped joints -> identity.
    World deltas are re-parented through the SOMA hierarchy so the result
    plugs straight into the existing fullbody constraint path.
    """
    M_BK = mathutils.Matrix(((1, 0, 0), (0, 0, 1), (0, -1, 0)))
    M_KB = M_BK.transposed()

    idx = _name_index(armature_obj)
    G_kimodo: dict[str, mathutils.Matrix] = {}

    for soma_name in joint_order:
        key = _norm(soma_name)
        pb = None
        if key in idx:
            pb = armature_obj.pose.bones.get(idx[key])
        else:
            cands = SOMA_TO_MIXAMO_CANDIDATES.get(key, [])
            for c in cands:
                if c in idx:
                    pb = armature_obj.pose.bones.get(idx[c])
                    break
        if pb is None:
            G_kimodo[soma_name] = mathutils.Matrix.Identity(3)
            continue
        delta_arm = _blender_delta_arm_3x3(armature_obj, pb)
        G_kimodo[soma_name] = M_BK @ delta_arm @ M_KB

    # Local rotations through SOMA parents (mirrors constraints.py).
    out: list[list[float]] = []
    for i, name in enumerate(joint_order):
        G_i = G_kimodo.get(name, mathutils.Matrix.Identity(3))
        pidx = joint_parents[i] if i < len(joint_parents) else -1
        if pidx < 0:
            R_local = G_i
        else:
            G_parent = G_kimodo.get(joint_order[pidx], mathutils.Matrix.Identity(3))
            R_local = G_parent.transposed() @ G_i
        out.append(_mat3_to_axis_angle(R_local))
    return out


def _mat3_to_axis_angle(m: mathutils.Matrix) -> list[float]:
    q = m.to_quaternion().normalized()
    angle = 2.0 * math.acos(max(-1.0, min(1.0, q.w)))
    s = math.sqrt(max(0.0, 1.0 - q.w * q.w))
    if s < 1e-6:
        return [0.0, 0.0, 0.0]
    return [q.x / s * angle, q.y / s * angle, q.z / s * angle]


# ---------------------------------------------------------------------------
# SOMA -> Mixamo bake
# ---------------------------------------------------------------------------

def _rest_world(arm: Object, bone_name: str) -> mathutils.Matrix:
    bone = arm.data.bones.get(bone_name)
    return arm.matrix_world @ bone.matrix_local


def _pose_world(arm: Object, pb) -> mathutils.Matrix:
    return arm.matrix_world @ pb.matrix


def estimate_scale(source_arm: Object, target_arm: Object) -> float:
    """Height proxy: Hips->Head rest distance ratio (tgt/src)."""
    try:
        def _hips_head(arm):
            idx = _name_index(arm)
            hips_n = idx.get("hips")
            # SOMA "head", Mixamo "head" — both normalize to "head"
            head_n = idx.get("head")
            if not hips_n or not head_n:
                return None
            hw = (arm.matrix_world @ arm.data.bones[hips_n].matrix_local).translation
            ew = (arm.matrix_world @ arm.data.bones[head_n].matrix_local).translation
            return (ew - hw).length
        s = _hips_head(source_arm)
        t = _hips_head(target_arm)
        if s and t and s > 1e-4:
            return t / s
    except Exception:
        pass
    return 1.0


def _target_depth(tgt_pb) -> int:
    d, b = 0, tgt_pb
    while b.parent is not None:
        d += 1
        b = b.parent
    return d


def retarget_bake(source_arm: Object, target_arm: Object,
                  frame_start: int, frame_end: int,
                  scale: float = 0.0, do_location: bool = True,
                  progress_cb=None) -> dict:
    """Bake SOMA motion onto Mixamo rig. Returns stats dict.

    Must run in OBJECT mode (we set it). Keyframes QUATERNION (+ LOCATION
    on the mapped Hips only). Target bones are set to QUATERNION mode.
    """
    scene = bpy.context.scene
    pairs = build_pairs(source_arm, target_arm)
    if not pairs:
        raise RuntimeError("No SOMA<->Mixamo bone pairs matched — check rig names.")

    if scale <= 1e-6:
        scale = estimate_scale(source_arm, target_arm)

    # Parent-first order so parent desired-world is ready for children.
    pairs_sorted = sorted(pairs, key=lambda p: _target_depth(p[2]))

    # Identify root pair (soma hips).
    root_pair = next((p for p in pairs_sorted if p[0] == "hips"), None)

    # Force quaternion mode on mapped targets.
    for _, _, tgt_pb in pairs_sorted:
        try:
            tgt_pb.rotation_mode = 'QUATERNION'
        except Exception:
            pass

    saved_frame = scene.frame_current
    try:
        for f in range(frame_start, frame_end + 1):
            scene.frame_set(f)
            bpy.context.view_layer.update()

            # 1. Source world rotation deltas for this frame (rest-invariant:
            # pose-vs-rest in world space). Same formulation as the reference
            # FBX script (t_rot = s_rot * offset).
            src_delta: dict[str, mathutils.Matrix] = {}
            src_pose_w: dict[str, mathutils.Matrix] = {}
            src_rest_w: dict[str, mathutils.Matrix] = {}
            for soma_key, src_pb, _tgt_pb in pairs_sorted:
                rw = _rest_world(source_arm, src_pb.name)
                pw = _pose_world(source_arm, src_pb)
                src_rest_w[soma_key] = rw
                src_pose_w[soma_key] = pw
                src_delta[soma_key] = pw.to_3x3() @ rw.to_3x3().inverted()

            # 2. Desired target world matrices, parent-first.
            desired_w: dict[str, mathutils.Matrix] = {}
            for soma_key, _src_pb, tgt_pb in pairs_sorted:
                tgt_rest_w = _rest_world(target_arm, tgt_pb.name)
                # Desired world rotation = src delta applied to tgt rest.
                R_des = src_delta[soma_key] @ tgt_rest_w.to_3x3()
                R_des4 = R_des.to_4x4()

                # Translation: only root follows source (scaled delta).
                if root_pair is not None and soma_key == root_pair[0] and do_location:
                    s_rw = src_rest_w[soma_key].translation
                    s_pw = src_pose_w[soma_key].translation
                    t_rw = tgt_rest_w.translation
                    t_des = t_rw + (s_pw - s_rw) * scale
                else:
                    # Keep rest translation; rotation drives the pose.
                    # (World translation of children follows from parents.)
                    t_des = tgt_rest_w.translation

                W = mathutils.Matrix.Translation(t_des) @ R_des4
                desired_w[tgt_pb.name] = W

            # 3. Convert desired-world -> pose-basis and key.
            for soma_key, _src_pb, tgt_pb in pairs_sorted:
                W = desired_w[tgt_pb.name]
                arm_w = target_arm.matrix_world
                # Desired armature-space matrix.
                A = arm_w.inverted() @ W

                bone = tgt_pb.bone
                rest_arm = bone.matrix_local
                parent = tgt_pb.parent

                if parent is None:
                    parent_pose_arm = mathutils.Matrix.Identity(4)
                    parent_rest_arm = mathutils.Matrix.Identity(4)
                else:
                    # Parent desired armature-space (already computed if
                    # parent was mapped, else live pose which is rest).
                    if parent.name in desired_w:
                        parent_world = desired_w[parent.name]
                        parent_pose_arm = arm_w.inverted() @ parent_world
                    else:
                        parent_pose_arm = parent.matrix
                    parent_rest_arm = target_arm.data.bones[parent.name].matrix_local

                # rest_local = parent_rest_inv * rest
                rest_local = parent_rest_arm.inverted() @ rest_arm
                # A = parent_pose * rest_local * Basis  =>
                # Basis = rest_local^-1 * parent_pose^-1 * A
                # (ORDER MATTERS: matrices don't commute; the reversed
                #  order mirrored limbs front-to-back on Mixamo targets.)
                M = rest_local.inverted() @ parent_pose_arm.inverted() @ A
                # Strip any uniform import scale (FBX 0.01) before quat.
                M3 = M.to_3x3()
                try:
                    s = (M3.col[0].length + M3.col[1].length + M3.col[2].length) / 3.0
                    if s > 1e-8:
                        M3 = M3 / s
                except Exception:
                    pass
                q = M3.to_quaternion().normalized()
                tgt_pb.rotation_quaternion = q

                if root_pair is not None and soma_key == root_pair[0] and do_location:
                    # Location basis: A_trans = R_rest * T_b + T_rest
                    # (with parent chain folded into parent_pose/rest_local;
                    #  for root, parent terms are identity so this is exact;
                    #  for safety only root uses location.)
                    R_rest = rest_arm.to_3x3()
                    T_rest = rest_arm.translation
                    T_des_arm = A.translation
                    try:
                        T_b = R_rest.inverted() @ (T_des_arm - T_rest)
                    except Exception:
                        T_b = T_des_arm - T_rest
                    tgt_pb.location = T_b
                    tgt_pb.keyframe_insert(data_path="location", frame=f)
                tgt_pb.keyframe_insert(data_path="rotation_quaternion", frame=f)

            if progress_cb and (f - frame_start) % 10 == 0:
                progress_cb(f, frame_end)
    finally:
        scene.frame_set(saved_frame)
        bpy.context.view_layer.update()

    return {"pairs": len(pairs_sorted), "scale": scale,
            "frames": frame_end - frame_start + 1}


def find_kimodo_source_armature(scene) -> Object | None:
    cands = [o for o in scene.objects
             if o.type == 'ARMATURE' and o.get("kimodo_source")]
    if not cands:
        return None
    return max(cands, key=lambda o: o.get("kimodo_creation_time", 0.0))


# ---------------------------------------------------------------------------
# Operator + Panel
# ---------------------------------------------------------------------------

class KIMODO_OT_RetargetSomaToMixamo(Operator):
    """Bake Kimodo SOMA motion onto the active Mixamo rig (prototype)"""
    bl_idname = "kimodo.retarget_soma_to_mixamo"
    bl_label = "Retarget SOMA → Mixamo"
    bl_options = {'REGISTER', 'UNDO'}

    source_name: StringProperty(
        name="Source", default="",
        description="SOMA source armature (blank = latest Kimodo_Source)",
    )
    target_name: StringProperty(
        name="Target", default="",
        description="Mixamo target armature (blank = active object)",
    )
    frame_start: IntProperty(name="Start", default=-1)
    frame_end: IntProperty(name="End", default=-1)
    do_location: BoolProperty(name="Copy Root Motion", default=True)

    def execute(self, context):
        scene = context.scene
        src = None
        if self.source_name:
            src = scene.objects.get(self.source_name)
        if src is None:
            src = find_kimodo_source_armature(scene)
        tgt = None
        if self.target_name:
            tgt = scene.objects.get(self.target_name)
        if tgt is None:
            a = context.active_object
            if a and a.type == 'ARMATURE' and a != src:
                tgt = a
        if src is None or src.type != 'ARMATURE':
            self.report({'ERROR'}, "No SOMA source found (generate motion first).")
            return {'CANCELLED'}
        if tgt is None or tgt.type != 'ARMATURE':
            self.report({'ERROR'}, "Select your Mixamo armature (make it active).")
            return {'CANCELLED'}

        fs = self.frame_start if self.frame_start >= 0 else scene.frame_start
        fe = self.frame_end if self.frame_end >= 0 else scene.frame_end
        if fe < fs:
            fs, fe = fe, fs

        # Bake needs OBJECT mode.
        try:
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass
        bpy.ops.object.select_all(action='DESELECT')
        tgt.select_set(True)
        context.view_layer.objects.active = tgt

        try:
            stats = retarget_bake(src, tgt, fs, fe, do_location=self.do_location)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"Retarget failed: {exc}")
            return {'CANCELLED'}

        self.report({'INFO'},
                    f"Retargeted {stats['pairs']} bones, {stats['frames']}f "
                    f"(scale {stats['scale']:.3f}): {src.name} → {tgt.name}")
        return {'FINISHED'}


class KIMODO_PT_Retarget(Panel):
    bl_label = "Retarget (Mixamo prototype)"
    bl_idname = "KIMODO_PT_Retarget"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Kimodo'
    bl_order = 30
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        src = find_kimodo_source_armature(scene)
        a = context.active_object
        tgt = a if (a and a.type == 'ARMATURE' and a != src) else None

        box = layout.box()
        box.label(text=f"Source: {src.name if src else '— generate first —'} "
                       f"({detect_rig(src) if src else 'none'})", icon='ARMATURE_DATA')
        box.label(text=f"Target: {tgt.name if tgt else '— select Mixamo rig —'} "
                       f"({detect_rig(tgt) if tgt else 'none'})", icon='ARMATURE_DATA')
        if src and tgt:
            n = len(build_pairs(src, tgt))
            box.label(text=f"{n} bone pairs mapped", icon='CHECKMARK' if n >= 15 else 'ERROR')

        op = layout.operator("kimodo.retarget_soma_to_mixamo", icon='PLAY')
        op.source_name = src.name if src else ""
        op.target_name = tgt.name if tgt else ""

        layout.label(text="Loop: pose Mixamo → Full-Body constraint → Generate → Retarget back.",
                     icon='INFO')


_classes = [
    KIMODO_OT_RetargetSomaToMixamo,
    KIMODO_PT_Retarget,
]


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
