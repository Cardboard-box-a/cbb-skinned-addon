import bpy
import struct
import traceback
from bpy.types import Operator
from mathutils import Vector, Quaternion, Matrix
from utils import Utils, CoordsSys
Serializer = Utils.Serializer
CoordinatesConverter = Utils.CoordinatesConverter
from typing import Optional
import os
from pathlib import Path

MIN_BONE_LENGTH = 0.05

def import_skeleton(debug: bool, file_name: str, directory: str, operator: Operator = None):
    context = bpy.context
    msg_handler = Utils.MessageHandler(debug=debug, report_function=operator.report)
    
    return_value = {"CANCELLED"}
    
    old_active_object = context.view_layer.objects.active
    old_active_selected = None
    old_active_mode = None
    if old_active_object is not None:
        old_active_selected = context.view_layer.objects.active.select_get()
        old_active_mode = context.view_layer.objects.active.mode
    old_selection = [obj for obj in context.selected_objects]
    try:
        if file_name.casefold().endswith(".skeleton"):
            file_path = Path(directory) / file_name

            msg_handler.debug_print(f"Importing skeleton from: {file_path}")
            
            skeleton_data = SkeletonData.read_skeleton_data(file_path, msg_handler)
            
            # Invalid skeleton, abort import
            if skeleton_data is None:
                return return_value
            
            return_value = {"FINISHED"}
            
            # Create armature and enter edit mode
            armature = bpy.data.armatures.new(file_path.stem)
            armature_obj = bpy.data.objects.new(file_path.stem, armature)
            context.collection.objects.link(armature_obj)
            context.view_layer.objects.active = armature_obj
            bpy.ops.object.mode_set(mode="EDIT")

            edit_bones = armature_obj.data.edit_bones
            bones = []
            bone_lengths: float = []
            bone_local_matrices: Matrix = []
            bone_world_matrices: Matrix = []
            
            
            # Create bones and map indices
            for i in range(skeleton_data.bone_count):
                bone = edit_bones.new(skeleton_data.bone_names[i])
                bone["bone_id"] = i
                bones.append(bone)
                ## Initialized to 9999 to indicate errors.
                bone_lengths.append (9999)
                bone_local_matrices.append(Matrix.Identity(4))
                bone_world_matrices.append(Matrix.Identity(4))
            
            msg_handler.debug_print(f"Created [{len(edit_bones)}] bones in Blender armature.")
            
            def _process_bone(bone_id):
                position = skeleton_data.bone_absolute_positions[bone_id]

                rotation = skeleton_data.bone_absolute_rotations[bone_id]

                # Calculate bone matrices
                if skeleton_data.bone_parent_ids[bone_id] == SkeletonData.NO_PARENT:
                    bone_world_matrices[bone_id] = Matrix.Identity(4) @ Matrix.Translation(position) @ rotation.to_matrix().to_4x4()
                    bone_local_matrices[bone_id] = bone_world_matrices[bone_id]
                else:
                    parent_world_matrix = bone_world_matrices[skeleton_data.bone_parent_ids[bone_id]]
                    bone_world_matrices[bone_id] = Matrix.Identity(4) @ Matrix.Translation(position) @ rotation.to_matrix().to_4x4()
                    bone_local_matrices[bone_id] = parent_world_matrix.inverted() @ bone_world_matrices[bone_id]

                # Process children
                for child_id in [idx for idx, pid in enumerate(skeleton_data.bone_parent_ids) if pid == bone_id]:
                    _process_bone(child_id)

            # Find root bones and process recursively
            root_bones = [i for i in range(skeleton_data.bone_count) if skeleton_data.bone_parent_ids[i] == SkeletonData.NO_PARENT]
            for root_bone_id in root_bones:
                _process_bone(root_bone_id)

            def __calculate_bone_length(cur_bone_id):
                def pick_bone_length():
                    child_locs = []
                    for child_id in [idx for idx, pid in enumerate(skeleton_data.bone_parent_ids) if pid == cur_bone_id]:
                        child_locs.append(bone_local_matrices[child_id].to_translation())
                    # If the bone has children, return the min of the children's position length
                    if child_locs:
                        min_length = min((loc.length for loc in child_locs))
                        if min_length > MIN_BONE_LENGTH:
                            return min_length
                        else:
                            return MIN_BONE_LENGTH
                        
                    # If the bone is not a root bone and has no children, return the parent's length
                    if skeleton_data.bone_parent_ids[cur_bone_id] != SkeletonData.NO_PARENT:
                        parent_bone_length = bone_lengths[skeleton_data.bone_parent_ids[cur_bone_id]]
                        if parent_bone_length > MIN_BONE_LENGTH:
                            return parent_bone_length
                        else:
                            return MIN_BONE_LENGTH

                    return 1
                
                bone_lengths[cur_bone_id] = pick_bone_length()
                for child_id in [idx for idx, pid in enumerate(skeleton_data.bone_parent_ids) if pid == cur_bone_id]:
                    __calculate_bone_length(child_id)

            for root_bone_id in root_bones:
                __calculate_bone_length(root_bone_id)
            
            for i in range(skeleton_data.bone_count):
                bones[i].length = bone_lengths[i]
                edit_bone = armature_obj.data.edit_bones[skeleton_data.bone_names[i]]
                edit_bone.matrix = bone_world_matrices[i]
                
                msg_handler.debug_print(f"Bone [{bones[i].name}] matrix rotation: [{bone_world_matrices[i].to_quaternion()}]")
                msg_handler.debug_print(f"Bone [{bones[i].name}] as edit_bone matrix rotation: [{edit_bone.matrix.to_quaternion()}]")
                
                if skeleton_data.bone_parent_ids[i] != SkeletonData.NO_PARENT and i != 0:
                    # These bones are manually overriden in the game to have no parent and their animations are given in world coordinates, so we fix these cases manually.
                    if bones[i].name.casefold() != "staffjoint2" and bones[i].name.casefold() != "r_handend1" and bones[i].name.casefold() != "l_handend1":
                        bones[i].parent = bones[skeleton_data.bone_parent_ids[i]]
                
                msg_handler.debug_print(f"Length of bone [{bones[i].name}]: {bones[i].length}")

            context.view_layer.update()
            bpy.ops.object.mode_set(mode="OBJECT")
        else:
            msg_handler.report("ERROR", f"File [{file_name}] does not have the skeleton extension.")
    except Exception as e:
        msg_handler.report("ERROR", f"Failed to import skeleton: {e} \n{traceback.format_exc()}")
    finally:
        bpy.ops.object.select_all(action='DESELECT')
        if old_active_object is not None:
            bpy.context.view_layer.objects.active = old_active_object
            bpy.context.view_layer.objects.active.select_set(old_active_selected)
            bpy.ops.object.mode_set(mode=old_active_mode)
        elif bpy.context.view_layer.objects.active is not None:
            bpy.ops.object.mode_set(mode="OBJECT")
        
        for obj in old_selection:
            obj.select_set(True)
        
    
    return return_value

class SkeletonData:
    """
    Class that holds convenient skeleton information. Do note that absolute in the name of transform variables refers to them being 
    referent to the armature only, as if the armature transform was the center of the world.
    """
    
    NO_PARENT: int = -1
    
    def __init__(self):
        self.skeleton_name: str = ""
        self.bone_name_to_id = {}
        self.bone_count: int = 0
        self.bone_names: str = []
        self.bone_parent_ids: list[int] = []
        self.bone_absolute_positions: list[Vector] = []
        self.bone_absolute_scales: list[Vector]= []
        self.bone_absolute_rotations: list[Quaternion] = []
        self.bone_local_positions: list[Vector] = []
        self.bone_local_rotations: list[Quaternion] = []
    
    @staticmethod
    def read_skeleton_data(filepath: str, msg_handler: Utils.MessageHandler) -> Optional["SkeletonData"]:
        skeletonData = SkeletonData()
        try:
            with open(filepath, "rb") as opened_file:
                co_conv = CoordinatesConverter(CoordsSys.Unity, CoordsSys.Blender)
                reader: Serializer = Serializer(opened_file, Serializer.Endianness.Little, Serializer.Quaternion_Order.XYZW, Serializer.Matrix_Order.RowMajor, co_conv)
                
                # Skip irrelevant data
                opened_file.seek(280, 0)

                skeletonData.bone_count = reader.read_uint()
                
                opened_file.seek(24, 1)
                
                msg_handler.debug_print(f"Bone count from source skeleton: {skeletonData.bone_count}")

                for _ in range(skeletonData.bone_count):
                    bone_name = reader.read_fixed_string(128, "ascii")
                    skeletonData.bone_names.append(bone_name)

                opened_file.seek(12, 1)
                
                skeletonData.bone_parent_ids = list(reader.read_values(f"{skeletonData.bone_count}i", 4 * skeletonData.bone_count))

                # Some skeletons have the first bone, which is the root bone, with a parent to itself. That's obviously wrong, so we fix it manually.
                # The first bone is also usually treated as the root bone and ignores any attempts of parenting. That's why it's important to always have
                # the root bone of the skeleton with a bone_id 0 property when exporting.
                skeletonData.bone_parent_ids[0] = SkeletonData.NO_PARENT

                opened_file.seek(12, 1)

                for _ in range(skeletonData.bone_count):
                    msg_handler.debug_print(f"Bone name: [{skeletonData.bone_names[_]}]. ID and parent ID: [{_}] | [{skeletonData.bone_parent_ids[_]}]")
                    
                    bone_position = reader.read_converted_vector3f()
                    bone_scale = reader.read_vector3f()
                    bone_rotation = reader.read_converted_quaternion()
                    
                    msg_handler.debug_print(f"Bone position (after conversion): [{bone_position}]")
                    msg_handler.debug_print(f"Bone scale (no conversion is done): [{bone_scale}]")
                    msg_handler.debug_print(f"Bone rotation (after conversion): [{bone_rotation}]")
                    
                    skeletonData.bone_absolute_positions.append(bone_position)
                    skeletonData.bone_absolute_scales.append(bone_scale)
                    skeletonData.bone_absolute_rotations.append(bone_rotation)
                
                for bone_id in range(skeletonData.bone_count):
                    msg_handler.debug_print(f"Bone name: [{skeletonData.bone_names[bone_id]}], local data:")
                    
                    if skeletonData.bone_parent_ids[bone_id] != SkeletonData.NO_PARENT:
                        parent_bone_id = skeletonData.bone_parent_ids[bone_id]
                        skeletonData.bone_local_positions.append(Utils.get_local_position(skeletonData.bone_absolute_positions[parent_bone_id], skeletonData.bone_absolute_rotations[parent_bone_id], skeletonData.bone_absolute_positions[bone_id]))
                        skeletonData.bone_local_rotations.append(Utils.get_local_rotation(skeletonData.bone_absolute_rotations[parent_bone_id], skeletonData.bone_absolute_rotations[bone_id]))
                    else:
                        skeletonData.bone_local_positions.append(skeletonData.bone_absolute_positions[bone_id])
                        skeletonData.bone_local_rotations.append(skeletonData.bone_absolute_rotations[bone_id])
                    msg_handler.debug_print(f"Local position: [{skeletonData.bone_local_positions[bone_id]}]")
                    msg_handler.debug_print(f"Local rotation: [{skeletonData.bone_local_rotations[bone_id]}]")

        except Exception as e:
            msg_handler.report("ERROR", f"Failed to read file to read skeleton data: {e}")
            traceback.print_exc()
            return None
        
        return skeletonData
    
    @staticmethod
    def write_skeleton_data(filepath: str, skeleton_data: "SkeletonData", msg_handler: Utils.MessageHandler) -> bool:
        try:
            co_conv = CoordinatesConverter(CoordsSys.Blender, CoordsSys.Unity)
            with open(filepath, "wb") as opened_file:
                writer = Serializer(opened_file, Serializer.Endianness.Little, Serializer.Quaternion_Order.XYZW, Serializer.Matrix_Order.RowMajor, co_conv)
                try:
                    writer.write_uint(1979)
                    writer.write_uint(0)
                    writer.write_uint(50331648)
                    writer.write_uint(0xFFFFFFFF)
                    writer.write_uint(276)
                    writer.write_uint(3)
                    opened_file.write(bytearray(256))
                    writer.write_uint(skeleton_data.bone_count)
                    writer.write_uint(0)
                    writer.write_uint(0)
                    writer.write_float(30.0)
                    writer.write_uint(50332160)
                    writer.write_uint(128 * skeleton_data.bone_count)
                    writer.write_uint(0xFFFFFFFF)
                    
                    for name in skeleton_data.bone_names:
                        writer.write_fixed_string(128, "ascii", name)
                    
                    writer.write_uint(50332672)
                    writer.write_uint(4 * skeleton_data.bone_count)
                    writer.write_uint(0xFFFFFFFF)
                    
                    for parent_id in skeleton_data.bone_parent_ids:
                        writer.write_int(parent_id)
                    
                    writer.write_uint(50331904)
                    writer.write_uint(40 * skeleton_data.bone_count)
                    writer.write_uint(0xFFFFFFF)
                    
                    for pos, scale, rot in zip(skeleton_data.bone_absolute_positions, skeleton_data.bone_absolute_scales, skeleton_data.bone_absolute_rotations):
                        writer.write_converted_vector3f(pos)
                        writer.write_vector3f(scale)
                        writer.write_converted_quaternion(rot)
                    
                    writer.write_uint(50332416)
                    writer.write_uint(0)
                    writer.write_uint(0xFFFFFFFF)
                    
                except Exception as e:
                    opened_file.close()
                    os.remove(filepath)
                    msg_handler.report("ERROR", f"Exception while writing to file at [{filepath}]: {e}")
                    traceback.print_exc()
                    return False
        except Exception as e:
            msg_handler.report("ERROR", f"Could not open file for writing at [{filepath}]: {e}")
            traceback.print_exc()
            return False
        
        msg_handler.debug_print(f"Skeleton written successfully to: [{filepath}]")
        return True
    
    
    @staticmethod 
    def build_skeleton_from_armature(armature_object: bpy.types.Object, only_deform_bones: bool, check_for_exportation: bool, msg_handler: Utils.MessageHandler) -> "SkeletonData":
        """
            Function returns a SkeletonData class built from a Blender armature. It also performs checks to see if the given armature is valid, since the information in this class is used to do any import/export operation.
        """
        
        bones: list[bpy.types.Bone] = None
        if only_deform_bones:
            bones = [bone for bone in armature_object.data.bones if bone.use_deform]
        else:
            bones = armature_object.data.bones
        
        msg_handler.debug_print(f"Validating armature: {armature_object.name}. Checking for exportation: {check_for_exportation}")
        msg_handler.debug_print(f"Amount of bones: {len(bones)}")
        
        if len(bones) == 0:
            msg_handler.report("ERROR", f"Armature [{armature_object.name}] has no bones in it.")
            return
        if len(bones) > 256:
            msg_handler.report("ERROR", f"Armature [{armature_object.name}] has more than 256 bones.")
            return
        
        existing_bone_names: list[str] = []
        has_Head_bone = False
        
        skeleton_data = SkeletonData()
        skeleton_data.skeleton_name = armature_object.name
        skeleton_data.bone_count = len(bones)
        skeleton_data.bone_names = [""] * skeleton_data.bone_count
        skeleton_data.bone_parent_ids = [SkeletonData.NO_PARENT] * skeleton_data.bone_count
        skeleton_data.bone_absolute_positions = [Vector((0.0, 0.0, 0.0))] * skeleton_data.bone_count
        skeleton_data.bone_absolute_scales = [Vector((0.0, 0.0, 0.0))] * skeleton_data.bone_count
        skeleton_data.bone_absolute_rotations = [Quaternion((0.0, 0.0, 0.0, 0.0))] * skeleton_data.bone_count
        skeleton_data.bone_local_positions = [Vector((0.0, 0.0, 0.0))] * skeleton_data.bone_count
        skeleton_data.bone_local_rotations = [Quaternion((0.0, 0.0, 0.0, 0.0))] * skeleton_data.bone_count
        
        existing_bone_ids = set()
        
        base_bone_id = None
        for bone in bones:
            bone_name = bone.name
            msg_handler.debug_print(f"Information for bone: {bone_name}")
            
            msg_handler.debug_print(f" name length: {len(bone_name)}")
            if len(bone_name) > 128:
                msg_handler.report("ERROR", f"Bone name {bone_name} exceeds 128 characters.")
                return
            
            try:
                bone_name.encode('ascii')
            except UnicodeEncodeError:
                msg_handler.report("ERROR", f"Bone [{bone_name}] of armature [{armature_object.name}] contains non-ASCII characters.")
                return
            
            if bone_name not in existing_bone_names:
                existing_bone_names.append(bone_name)
                if bone_name == "Head":
                    has_Head_bone = True
            else:
                msg_handler.report("ERROR", f"Armature [{armature_object.name}] has bones with equal names.")
                return
            
            # Check for invalid bone_id values
            bone_id = bone.get("bone_id")
            msg_handler.debug_print(f" bone_id: {bone_id}")
            if bone_id is not None:
                if bone_id < 0 or bone_id >= len(bones):
                    msg_handler.report("ERROR", f"Bone [{bone_name}] of armature [{armature_object.name}] has an invalid id(id<0 or id>=number_of_bones_in_armature(this number will be the amount of deform bones in case the consider only deform bones has been checked)), offending bone_id: [{bone_id}].")
                    return
            else:
                msg_handler.report("ERROR", f"Bone [{bone_name}] of armature [{armature_object.name}] is missing the bone_id property.")
                return
            
            if bone_id in existing_bone_ids:
                msg_handler.report("ERROR", f"Bone [{bone_name}] of armature [{armature_object.name}] has the same bone_id of another bone. Other bone with the same bone_id: {skeleton_data.bone_names[bone_id]}")
                return
            
            existing_bone_ids.add(bone_id)
            
            skeleton_data.bone_names[bone_id] = bone_name
            skeleton_data.bone_name_to_id[bone_name] = bone_id
            edit_bone_position , edit_bone_rotation = Utils.decompose_blender_matrix_position_rotation(bone.matrix_local)
            skeleton_data.bone_absolute_positions[bone_id] = edit_bone_position
            skeleton_data.bone_absolute_rotations[bone_id] = edit_bone_rotation
            skeleton_data.bone_absolute_scales[bone_id] = Vector((1.0, 1.0, 1.0))
            bone_parent = None
            if only_deform_bones:
                def recursively_get_deform_parent(bone):
                    if bone.parent is None:
                        return None
                    elif bone.parent in bones:
                        return bone.parent
                    else:
                        return recursively_get_deform_parent(bone.parent)
                bone_parent = recursively_get_deform_parent(bone)
            else:
                bone_parent = bone.parent
            msg_handler.debug_print(f" edit position: {edit_bone_position}")
            msg_handler.debug_print(f" edit rotation: {edit_bone_rotation}")
            msg_handler.debug_print(f" parent: {bone_parent}")
            if base_bone_id is None:
                if bone_name.casefold() in {"base", "root"}:
                    base_bone_id = bone_id
            
            if bone_parent is not None:
                parent_edit_bone_position , parent_edit_bone_rotation = Utils.decompose_blender_matrix_position_rotation(bone_parent.matrix_local)
                skeleton_data.bone_local_positions[bone_id] = Utils.get_local_position(parent_edit_bone_position, parent_edit_bone_rotation, edit_bone_position)
                skeleton_data.bone_local_rotations[bone_id] = Utils.get_local_rotation(parent_edit_bone_rotation, edit_bone_rotation)
                msg_handler.debug_print(f" local position: {skeleton_data.bone_local_positions[bone_id]}")
                msg_handler.debug_print(f" local rotation: {skeleton_data.bone_local_rotations[bone_id]}")
                
                skeleton_data.bone_parent_ids[bone_id] = bone_parent["bone_id"]
            else:
                skeleton_data.bone_local_positions[bone_id] = edit_bone_position
                skeleton_data.bone_local_rotations[bone_id] = edit_bone_rotation
                skeleton_data.bone_parent_ids[bone_id] = SkeletonData.NO_PARENT
                
        msg_handler.debug_print(f" has head bone: {has_Head_bone}")
        msg_handler.debug_print(f" base bone id: {base_bone_id}")
        if check_for_exportation:
            if not has_Head_bone:
                msg_handler.report("ERROR", f"Armature [{armature_object.name}] is missing a bone named 'Head'(case considered), which is necessary for exportation.")
                return
            
            if base_bone_id is None:
                msg_handler.report("ERROR", f"Armature [{armature_object.name}] is missing a bone named 'Base'(case not considered) or 'Root'(case not considered), which is necessary for exportation.")
                return
            if skeleton_data.bone_parent_ids[base_bone_id] != SkeletonData.NO_PARENT:
                msg_handler.report("ERROR", f"Bone [{skeleton_data.bone_names[base_bone_id]}] of armature [{armature_object.name}] is marked as the root bone but has a parent, which should not happen.")
                return
        return skeleton_data
                

    @staticmethod
    def float_to_hex(f):
        string = str(hex(struct.unpack("<I", struct.pack("<f", f))[0])).lstrip("0x0").zfill(8)
        reversed_hex_string = "".join(reversed([string[i:i+2] for i in range(0, len(string), 2)]))
        return reversed_hex_string
    
    def print_positions_as_hex(self):
        hex_data_string = ""
        for position in self.bone_absolute_positions:
            hex_data = "{0}{1}{2}".format(SkeletonData.float_to_hex(position[0]), SkeletonData.float_to_hex(position[1]), SkeletonData.float_to_hex(position[2]))
            hex_data_string += hex_data
        hex_data_string += "\n"
        print(hex_data_string)
        
    def print_rotations_as_hex(self):
        hex_data_string = ""
        for rotation in self.bone_absolute_rotations:
            hex_data = "{0}{1}{2}{3}".format(SkeletonData.float_to_hex(rotation[0]), SkeletonData.float_to_hex(rotation[1]), SkeletonData.float_to_hex(rotation[2]), SkeletonData.float_to_hex(rotation[3]))
            hex_data_string += hex_data
        hex_data_string += "\n"
        print(hex_data_string)
