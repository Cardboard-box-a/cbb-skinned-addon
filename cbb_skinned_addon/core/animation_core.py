import bpy
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.types import Context, Event, Operator, ActionFCurves, FCurve, Action
from bpy_extras.io_utils import ImportHelper
import mathutils
import math
import traceback
from utils import Utils, CoordsSys
import xml.etree.ElementTree as ET
from ..core.skeleton_core import SkeletonData
Serializer = Utils.Serializer
CoordinatesConverter = Utils.CoordinatesConverter
from pathlib import Path
from .mesh_core import try_get_skeleton_name_for_mesh

def import_animation_from_files(debug: bool, file_name: str, directory: str, apply_to_armature_in_selected: bool, skeleton_name = "", operator: Operator = None):
    msg_handler = Utils.MessageHandler(debug, operator.report)
    
    return_value = {"CANCELLED"}
    
    if file_name.casefold().endswith(".skinnedanim"):
        filepath: Path = Path(directory) / file_name

        anim_bone_amount = 0
        total_frames = 0
        are_positions_relative_to_parent = False
        number_of_bone_rotations_animated = 0
        number_of_bone_positions_animated = 0
        number_of_bone_rotations_fixed = 0
        number_of_bone_positions_fixed = 0
        animated_rotations_by_bone = []
        animated_positions_by_bone = []
        fixed_positions_by_bone = []
        fixed_rotations_by_bone = []
        dynamic_pos_bones = []
        dynamic_rot_bones = []
        static_pos_bones = []
        static_rot_bones = []
        is_bone_fixed_pos = []
        is_bone_fixed_rot = []
        
        # Input: bone_id, output: dynamic/static id of bone in dynamic/static arrays
        inverse_dynamic_pos_bones_map = []
        inverse_dynamic_rot_bones_map = []
        inverse_static_pos_bones_map = []
        inverse_static_rot_bones_map = []

        skeleton_data = SkeletonData()

        target_armature = None
        
        if apply_to_armature_in_selected == False:# Automatic suitable armature search
            if skeleton_name == "":
                skeleton_name = try_get_skeleton_name_for_animation(filepath, directory, msg_handler)
                msg_handler.debug_print(f"Skeleton_name found: [{skeleton_name}]")
            
            if skeleton_name != "":
                for obj in bpy.context.scene.objects:
                    if obj.name.casefold() == skeleton_name.casefold() and obj.type == "ARMATURE":
                        target_armature = obj
                        break
        else: # Choose the armature available along the selection, as long as there is only one armature.
            for obj in bpy.context.selected_objects:
                if obj.type == "ARMATURE":
                    if target_armature is None:
                        target_armature = obj
                    else:
                        msg_handler.report("ERROR", f"More than one armature has been found in the current selection. The imported animation can only be assigned to one armature at a time.")
                        return return_value

    
        if not target_armature:
            msg_handler.report("ERROR", "No armature found in the scene for animation to import to.")
            return return_value
        else:
            skeleton_data = SkeletonData.build_skeleton_from_armature(target_armature, False, False, msg_handler)
            if skeleton_data is None:
                msg_handler.report("ERROR", f"Armature [{target_armature}] which is the target of the imported animation has been found not valid. Aborting.")
                return return_value
            
        co_conv = CoordinatesConverter(CoordsSys.Unity, CoordsSys.Blender)
        
        try:
            with open(filepath, "rb") as opened_file:
                reader = Serializer(opened_file, Serializer.Endianness.Little, Serializer.Quaternion_Order.XYZW, Serializer.Matrix_Order.RowMajor, co_conv)
                # Read and skip headers
                opened_file.seek(124, 0)  # Skip initial headers

                # Read boneAmount
                opened_file.seek(8, 1)  # Skip boneAmountHeader
                anim_bone_amount = reader.read_uint()
                
                print("bone_amount:", anim_bone_amount)
                
                # Read totalFrames
                opened_file.seek(8, 1)  # Skip frameNumberHeader
                total_frames = reader.read_uint()
                
                print("total_frames:", total_frames)
                
                opened_file.seek(8, 1)  # Skip IsRelativeToParent header + data
                are_positions_relative_to_parent = reader.read_bool()
                
                # Read numberOfBoneRotationsAnimated
                opened_file.seek(8, 1)  # Skip numberOfBoneRotationsAnimatedHeader
                number_of_bone_rotations_animated = reader.read_uint()

                # Read numberOfBonePositionsAnimated
                opened_file.seek(8, 1)  # Skip numberOfBonePositionsAnimatedHeader
                number_of_bone_positions_animated = reader.read_uint()

                # Read numberOfBoneRotationsFixed
                opened_file.seek(8, 1)  # Skip numberOfBoneRotationsFixedHeader
                number_of_bone_rotations_fixed = reader.read_uint()

                # Read numberOfBonePositionsFixed
                opened_file.seek(8, 1)  # Skip numberOfBonePositionsFixedHeader
                number_of_bone_positions_fixed = reader.read_uint()

                # Read animatedRotationsByBone
                opened_file.seek(4, 1)  # Skip animatedRotationsByBoneHeader
                dynamic_bone_rotation_data_size = reader.read_uint()
                
                for _ in range(int(dynamic_bone_rotation_data_size/16)):
                    animated_rotations_by_bone.append(reader.read_converted_quaternion())

                # Read animatedPositionsByBone
                opened_file.seek(4, 1)  # Skip animatedPositionsByBoneHeader
                dynamic_bone_position_data_size = reader.read_uint()
                for _ in range(int(dynamic_bone_position_data_size/12)):
                    animated_positions_by_bone.append(reader.read_converted_vector3f())

                # Read fixedPositionsByBone
                opened_file.seek(4, 1)  # Skip fixedPositionsByBoneHeader
                static_bone_position_data_size = reader.read_uint()
                for _ in range(int(static_bone_position_data_size/12)):
                    fixed_positions_by_bone.append(reader.read_converted_vector3f())

                # Read fixedRotationsByBone
                opened_file.seek(4, 1)  # Skip fixedRotationsByBoneHeader
                static_bone_rotation_data_size = reader.read_uint()
                for _ in range(int(static_bone_rotation_data_size/16)):
                    fixed_rotations_by_bone.append(reader.read_converted_quaternion())

                for i in range(anim_bone_amount):
                    inverse_dynamic_pos_bones_map.append(SkeletonData.NO_PARENT)
                    inverse_dynamic_rot_bones_map.append(SkeletonData.NO_PARENT)
                    inverse_static_pos_bones_map.append(SkeletonData.NO_PARENT)
                    inverse_static_rot_bones_map.append(SkeletonData.NO_PARENT)
                # Read BoneMapping
                opened_file.seek(8, 1)  # Skip BoneMapHeader
                for i in range(anim_bone_amount):
                    bone_id_for_pos, used_in_frames_pos, bone_id_for_rot, used_in_frames_rot = reader.read_values("4B", 4)
                    if used_in_frames_pos == 0xF0:
                        inverse_dynamic_pos_bones_map[i] = len(dynamic_pos_bones)
                        dynamic_pos_bones.append(i)
                        is_bone_fixed_pos.append(False)
                    else:
                        inverse_static_pos_bones_map[i] = len(static_pos_bones)
                        static_pos_bones.append(i)
                        is_bone_fixed_pos.append(True)
                    if used_in_frames_rot == 0xF0:
                        inverse_dynamic_rot_bones_map[i] = len(dynamic_rot_bones)
                        dynamic_rot_bones.append(i)
                        is_bone_fixed_rot.append(False)
                    else:
                        inverse_static_rot_bones_map[i] = len(static_rot_bones)
                        static_rot_bones.append(i)
                        is_bone_fixed_rot.append(True)

        except Exception as e:
            msg_handler.report("ERROR", f"Failed to read file at [{filepath}]: {e}")
            traceback.print_exc()
            return return_value

        if skeleton_data.bone_count != anim_bone_amount:
            msg_handler.report("ERROR", f"Target armature and animation don't have the same amount of bones (Target has: [{skeleton_data.bone_count}]. Animation has: [{anim_bone_amount}]). Aborting importation.")
            return return_value

        msg_handler.debug_print(f"[Animation Data: ]")
        msg_handler.debug_print(f"anim_bone_amount: {anim_bone_amount}")
        msg_handler.debug_print(f"total_frames: {total_frames}")
        msg_handler.debug_print(f"are_positions_relative_to_parent: {are_positions_relative_to_parent}")
        msg_handler.debug_print(f"number_of_bone_rotations_animated: {number_of_bone_rotations_animated}")
        msg_handler.debug_print(f"number_of_bone_positions_animated: {number_of_bone_positions_animated}")
        msg_handler.debug_print(f"number_of_bone_rotations_fixed: {number_of_bone_rotations_fixed}")
        msg_handler.debug_print(f"number_of_bone_positions_fixed: {number_of_bone_positions_fixed}")
        
        return_value = {"FINISHED"}
        
        try:
            # Create animation action
            action_name = filepath.stem
            action = bpy.data.actions.new(name=action_name)

            target_armature.animation_data_create().action = action
            # target_armature.animation_data.action = action

            # Create keyframes
            def cor_bone_pos(bone_id, frame):
                if is_bone_fixed_pos[bone_id] == True:
                    return fixed_positions_by_bone[inverse_static_pos_bones_map[bone_id]]
                else:
                    dynamic_bone_id = inverse_dynamic_pos_bones_map[bone_id]
                    return animated_positions_by_bone[frame * number_of_bone_positions_animated + dynamic_bone_id]
                
            def cor_bone_rot(bone_id, frame):
                if is_bone_fixed_rot[bone_id] == True:
                    return fixed_rotations_by_bone[inverse_static_rot_bones_map[bone_id]]
                else:
                    dynamic_bone_id = inverse_dynamic_rot_bones_map[bone_id]
                    return animated_rotations_by_bone[frame * number_of_bone_rotations_animated + dynamic_bone_id]
            
            if number_of_bone_positions_fixed > 0:
                for iterator, bone_id in enumerate(static_pos_bones):
                    # Assign position for static bones first
                    current_bone_name = skeleton_data.bone_names[bone_id]
                    parentboneid = skeleton_data.bone_parent_ids[bone_id]
                    loc = mathutils.Vector((0.0, 0.0, 0.0))
                    if parentboneid == SkeletonData.NO_PARENT or bone_id == 0:
                        loc = Utils.get_local_position(
                            skeleton_data.bone_absolute_positions[bone_id],
                            skeleton_data.bone_absolute_rotations[bone_id],
                            fixed_positions_by_bone[iterator])
                    else:
                        if are_positions_relative_to_parent == True:
                            # Get position of animation relative to bind local pose
                            loc = Utils.get_local_position(skeleton_data.bone_local_positions[bone_id], skeleton_data.bone_local_rotations[bone_id], fixed_positions_by_bone[iterator])
                        else:
                            # Get local position of world animation relative to bind local pose
                            local_animation_position = Utils.get_local_position(cor_bone_pos(parentboneid, 0), cor_bone_rot(parentboneid, 0), fixed_positions_by_bone[iterator])
                            loc = Utils.get_local_position(skeleton_data.bone_local_positions[bone_id], skeleton_data.bone_local_rotations[bone_id], local_animation_position)

                    target_armature.pose.bones[current_bone_name].location = loc
                    target_armature.pose.bones[current_bone_name].keyframe_insert(data_path="location", frame=0)
            
            if number_of_bone_rotations_fixed > 0:
                for iterator, bone_id in enumerate(static_rot_bones):
                    # Assign rotation for static bones
                    current_bone_name = skeleton_data.bone_names[bone_id]
                    parentboneid = skeleton_data.bone_parent_ids[bone_id]
                    rot = mathutils.Quaternion((1,0,0,0))
                    if parentboneid == SkeletonData.NO_PARENT or bone_id == 0:
                        rot = skeleton_data.bone_absolute_rotations[bone_id].conjugated() @ fixed_rotations_by_bone[iterator]
                    else:
                        if are_positions_relative_to_parent == True:
                            rot = skeleton_data.bone_local_rotations[bone_id].conjugated() @ fixed_rotations_by_bone[iterator]
                        else:
                            local_animation_rotation = Utils.get_local_rotation(cor_bone_rot(parentboneid, 0), fixed_rotations_by_bone[iterator])
                            rot = skeleton_data.bone_local_rotations[bone_id].conjugated() @ local_animation_rotation

                    target_armature.pose.bones[current_bone_name].rotation_quaternion = rot
                    target_armature.pose.bones[current_bone_name].keyframe_insert(data_path="rotation_quaternion", frame=0)
            
            for frame in range(total_frames):
                if number_of_bone_positions_animated > 0:
                    for iterator, bone_id in enumerate(dynamic_pos_bones):
                        # Assign position for dynamic position bones for each frame
                        current_bone_name = skeleton_data.bone_names[bone_id]
                        parentboneid = skeleton_data.bone_parent_ids[bone_id]
                        idx = frame * number_of_bone_positions_animated + iterator
                        loc = mathutils.Vector((0.0, 0.0, 0.0))
                        if parentboneid == SkeletonData.NO_PARENT or bone_id == 0:
                            loc = Utils.get_local_position(
                            skeleton_data.bone_absolute_positions[bone_id] ,
                            skeleton_data.bone_absolute_rotations[bone_id],
                            animated_positions_by_bone[idx])
                        else:
                            if are_positions_relative_to_parent == True:
                                loc = Utils.get_local_position(skeleton_data.bone_local_positions[bone_id], skeleton_data.bone_local_rotations[bone_id], animated_positions_by_bone[idx])
                            else:
                                local_animation_position = Utils.get_local_position(cor_bone_pos(parentboneid, frame), cor_bone_rot(parentboneid, frame), animated_positions_by_bone[idx])
                                loc = Utils.get_local_position(skeleton_data.bone_local_positions[bone_id], skeleton_data.bone_local_rotations[bone_id], local_animation_position)

                        target_armature.pose.bones[current_bone_name].location = loc
                        target_armature.pose.bones[current_bone_name].keyframe_insert(data_path="location", frame=frame)
                if number_of_bone_rotations_animated > 0:
                    for iterator, bone_id in enumerate(dynamic_rot_bones):
                        # Assign rotation for dynamic rotation bones for each frame
                        current_bone_name = skeleton_data.bone_names[bone_id]
                        parentboneid = skeleton_data.bone_parent_ids[bone_id]
                        rot = mathutils.Quaternion((1,0,0,0))
                        idx = frame * number_of_bone_rotations_animated + iterator

                        if parentboneid == SkeletonData.NO_PARENT or bone_id == 0:
                            rot = skeleton_data.bone_absolute_rotations[bone_id].conjugated() @ animated_rotations_by_bone[idx]
                        else:
                            if are_positions_relative_to_parent == True:
                                rot = skeleton_data.bone_local_rotations[bone_id].conjugated() @ animated_rotations_by_bone[idx]
                            else:
                                local_animation_rotation = Utils.get_local_rotation(cor_bone_rot(parentboneid, frame), animated_rotations_by_bone[idx])
                                rot = skeleton_data.bone_local_rotations[bone_id].conjugated() @ local_animation_rotation

                        target_armature.pose.bones[current_bone_name].rotation_quaternion = rot
                        target_armature.pose.bones[current_bone_name].keyframe_insert(data_path="rotation_quaternion", frame=frame)
                
            

            # Set animation frames range
            action.frame_range = (0, total_frames)

        except Exception as e:
            animation_name = filepath.stem
            msg_handler.report("ERROR", f"Failed to create animation {animation_name}: {e}")
            traceback.print_exc()
            return return_value
    else:
        msg_handler.report("ERROR", f"File [{file_name}] does not have the skinnedanim extension.")
    return return_value

def try_get_skeleton_name_for_animation(file_path: Path, directory: str, msg_handler: Utils.MessageHandler):
    mesh_animation_file_name: str = ""

    msg_handler.debug_print("[get_skeleton_name] method")
    msg_handler.debug_print(f"File_path used: {file_path}")

    def get_animation_file_and_name(xml_root_element: ET.Element):
        if xml_root_element is not None:
            animation_element = xml_root_element.find(".//Animation")
            if animation_element is not None:
                return animation_element.get("value", "").lstrip("/").split("|")[0]
            else:
                msg_handler.debug_print(f"Animation element could not be found inside a .xml source file.")
        return ""
    
    for file in Utils.find_single_xml_files(directory):
        msg_handler.debug_print(f"Trying to find .animation.xml in the file {file}")
        filepath: str = Path(directory) / file
        mesh_animation_file_name = get_animation_file_and_name(Utils.read_xml_file(msg_handler, filepath, f"Error while trying to read source .xml file at [{filepath}]"))
        
        if mesh_animation_file_name == "":
            continue
        
        animation_xml_root = Utils.read_xml_file(msg_handler, Path(directory) / mesh_animation_file_name, f"Error while trying to read  .animation.xml file at [{Path(directory) / mesh_animation_file_name}]")

        if animation_xml_root is not None:
            for animation_element in animation_xml_root.iterfind(".//animation"):
                for clip_element in animation_element.findall(".//clip"):
                    clip_is_present = clip_element.find(".//file").get("value", "").lstrip("/").casefold() == file_path.name.casefold() if clip_element.find(".//file") is not None else False
                    if clip_is_present == True:
                        skeleton_element = animation_element.find(".//skeleton")
                        if skeleton_element is not None:
                            skeleton_attribute: str = skeleton_element.get("value")
                            if skeleton_attribute is not None:
                                return str(Path(skeleton_attribute.lstrip("/")).stem)


    if mesh_animation_file_name == "":
        msg_handler.report("INFO", f"File [{file_path.name}]: .animation.xml file for this file mesh was not found in any source .xml in the file directory.")

    


    return ""