import bpy
import struct
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.types import Context, Event, Operator, ActionFCurves, FCurve, Action
from bpy.props import CollectionProperty, StringProperty, BoolProperty
from bpy_extras.io_utils import ImportHelper
import ntpath
import mathutils
import math
import traceback
from import_utils import ImportUtils
import xml.etree.ElementTree as ET
from mathutils import Vector, Quaternion, Matrix
from .skeleton import SkeletonData

class ImportSkinnedAnim(Operator, ImportHelper):
    bl_idname = "cbb.skinnedanim_import"
    bl_label = "Import SkinnedAnim"
    bl_options = {"PRESET", "UNDO"}

    filename_ext = ".SkinnedAnim"

    filter_glob: StringProperty(default="*.SkinnedAnim", options={"HIDDEN"})

    files: CollectionProperty(
        type=bpy.types.OperatorFileListElement,
        options={"HIDDEN", "SKIP_SAVE"}
    )

    directory: StringProperty(subtype="FILE_PATH")

    apply_to_armature_in_selected: BoolProperty(
        name="Apply to armature in selected",
        description="Enabling this option will make the import of the animation to target any armature present between currently selected objects",
        default=False
    )

    debug: BoolProperty(
        name="Debug import",
        description="Enabling this option will make the importer print debug data to console",
        default=False
    )

    z_minus_is_forward: BoolProperty(
        name="Z- is forward",
        description="Leave this option checked if you wish to work with Z- being the forward direction in Blender. If false, Z+ is considered forward",
        default=True
    )

    @staticmethod
    def get_skeleton_name(file_path, self):
        skeleton_name = ""
        animation_name: str = ntpath.basename(file_path)

        ImportUtils.debug_print(self.debug, "[get_skeleton_name] method")
        ImportUtils.debug_print(self.debug, f"File_path used: {file_path}")

        def get_animation_file_and_name(xml_root_element: ET.Element):
            if xml_root_element is not None:
                animation_element = xml_root_element.find(".//Animation")
                if animation_element is not None:
                    animation_attribute = animation_element.get("value")
                    if animation_attribute is not None:
                        mesh_animation_file_name = animation_attribute.lstrip("/").split("|")[0]
                        mesh_animation_name = animation_attribute.lstrip("/").split("|")[1]
                        return mesh_animation_file_name, mesh_animation_name
            return "", ""
        
        for file in ImportUtils.find_single_xml_files(self.directory):
            ImportUtils.debug_print(self.debug, f"Trying to find .animation.xml in the file {ntpath.basename(file)}")
            filepath: str = self.directory + ntpath.basename(file)
            anim_animation_file_name, anim_animation_name = get_animation_file_and_name(ImportUtils.read_xml_file(self, filepath, f"Error while trying to read source .xml file at [{filepath}]"))
            if anim_animation_file_name != "":
                animation_xml_root = ImportUtils.read_xml_file(self, self.directory + anim_animation_file_name, f"Error while trying to read  .animation.xml file at [{self.directory + anim_animation_file_name}]")
                temporary_skeleton_name = ""
                if animation_xml_root is not None:
                    for animation_element in animation_xml_root.iterfind(".//animation"):
                        skeleton_element = animation_element.find(".//skeleton")
                        if skeleton_element is not None:
                            skeleton_attribute: str = skeleton_element.get("value")
                            if skeleton_attribute is not None:
                                temporary_skeleton_name = skeleton_attribute.lstrip("/").split(".")[0]

                        if temporary_skeleton_name != "":
                            for file_tag in animation_element.iterfind(".//file"):
                                file_attribute = file_tag.get("value")
                                if file_attribute is not None:
                                    current_animation_name = file_attribute.lstrip("/")
                                    if current_animation_name.casefold() == animation_name.casefold():
                                        return temporary_skeleton_name

                else:
                    return ""


        return skeleton_name

    def execute(self, context):
        return self.import_animations_from_files(context)

    def import_animations_from_files(self, context):
        for file in self.files:
            if file.name.casefold().endswith(".SkinnedAnim".casefold()):
                filepath: str = self.directory + file.name

                animation_target_base_name = ntpath.basename(self.directory + file.name).rsplit(".", 1)[0].split("_")[0]

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
                if self.apply_to_armature_in_selected == False:
                    for obj in bpy.context.scene.objects:
                        if obj.name.casefold() == animation_target_base_name.casefold() and obj.type == "ARMATURE":
                            target_armature = obj
                            break
                    if target_armature is None:
                        skeleton_name = ImportSkinnedAnim.get_skeleton_name(filepath, self)
                        ImportUtils.debug_print(self.debug, f"Skeleton_name found: [{skeleton_name}]")
                        if skeleton_name != "":
                            for obj in bpy.context.scene.objects:
                                if obj.name.casefold() == skeleton_name.casefold() and obj.type == "ARMATURE":
                                    target_armature = obj
                                    break
                else:
                    for obj in bpy.context.selected_objects:
                        if obj.type == "ARMATURE":
                            if target_armature is None:
                                target_armature = obj
                            else:
                                self.report({"ERROR"}, f"More than one armature has been found in the current selection. The imported animation can only be assigned to one armature at a time.")

                if not target_armature:
                    self.report({"ERROR"}, "No armature found in the scene for animation to import to.")
                    return {"CANCELLED"}
                else:
                    skeleton_data = SkeletonData.build_skeleton_from_armature(self, target_armature, False, False)
                    if skeleton_data is None:
                        self.report({"ERROR"}, f"Armature [{target_armature}] which is the target of the imported animation has been found not valid. Aborting.")
                        return {"CANCELLED"}

                try:
                    with open(self.directory + file.name, "rb") as f:
                        # Read and skip headers
                        f.seek(124, 0)  # Skip initial headers

                        # Read boneAmount
                        f.seek(8, 1)  # Skip boneAmountHeader
                        anim_bone_amount = struct.unpack("<I", f.read(4))[0]
                        print("bone_amount:", anim_bone_amount)
                        # Read totalFrames
                        f.seek(8, 1)  # Skip frameNumberHeader
                        total_frames = struct.unpack("<I", f.read(4))[0]
                        print("total_frames:", total_frames)
                        
                        f.seek(8, 1)  # Skip IsRelativeToParent header + data
                        are_positions_relative_to_parent = struct.unpack("<?", f.read(1))[0]
                        
                        # Read numberOfBoneRotationsAnimated
                        f.seek(8, 1)  # Skip numberOfBoneRotationsAnimatedHeader
                        number_of_bone_rotations_animated = struct.unpack("<I", f.read(4))[0]

                        # Read numberOfBonePositionsAnimated
                        f.seek(8, 1)  # Skip numberOfBonePositionsAnimatedHeader
                        number_of_bone_positions_animated = struct.unpack("<I", f.read(4))[0]

                        # Read numberOfBoneRotationsFixed
                        f.seek(8, 1)  # Skip numberOfBoneRotationsFixedHeader
                        number_of_bone_rotations_fixed = struct.unpack("<I", f.read(4))[0]

                        # Read numberOfBonePositionsFixed
                        f.seek(8, 1)  # Skip numberOfBonePositionsFixedHeader
                        number_of_bone_positions_fixed = struct.unpack("<I", f.read(4))[0]

                        # Read animatedRotationsByBone
                        f.seek(4, 1)  # Skip animatedRotationsByBoneHeader
                        dynamic_bone_rotation_data_size = struct.unpack("<I", f.read(4))[0]
                        for _ in range(int(dynamic_bone_rotation_data_size/16)):
                            x = struct.unpack("<f", f.read(4))[0]
                            y = struct.unpack("<f", f.read(4))[0]
                            z = struct.unpack("<f", f.read(4))[0]
                            w = struct.unpack("<f", f.read(4))[0]
                            animated_rotations_by_bone.append(ImportUtils.convert_quaternion_unity_to_blender(x, y, z, w, self.z_minus_is_forward))

                        # Read animatedPositionsByBone
                        f.seek(4, 1)  # Skip animatedPositionsByBoneHeader
                        dynamic_bone_position_data_size = struct.unpack("<I", f.read(4))[0]
                        for _ in range(int(dynamic_bone_position_data_size/12)):
                            x = struct.unpack("<f", f.read(4))[0]
                            y = struct.unpack("<f", f.read(4))[0]
                            z = struct.unpack("<f", f.read(4))[0]
                            animated_positions_by_bone.append(ImportUtils.convert_position_unity_to_blender(x, y, z, self.z_minus_is_forward))

                        # Read fixedPositionsByBone
                        f.seek(4, 1)  # Skip fixedPositionsByBoneHeader
                        static_bone_position_data_size = struct.unpack("<I", f.read(4))[0]
                        for _ in range(int(static_bone_position_data_size/12)):
                            x = struct.unpack("<f", f.read(4))[0]
                            y = struct.unpack("<f", f.read(4))[0]
                            z = struct.unpack("<f", f.read(4))[0]
                            fixed_positions_by_bone.append(ImportUtils.convert_position_unity_to_blender(x, y, z, self.z_minus_is_forward))

                        # Read fixedRotationsByBone
                        f.seek(4, 1)  # Skip fixedRotationsByBoneHeader
                        static_bone_rotation_data_size = struct.unpack("<I", f.read(4))[0]
                        for _ in range(int(static_bone_rotation_data_size/16)):
                            x = struct.unpack("<f", f.read(4))[0]
                            y = struct.unpack("<f", f.read(4))[0]
                            z = struct.unpack("<f", f.read(4))[0]
                            w = struct.unpack("<f", f.read(4))[0]
                            fixed_rotations_by_bone.append(ImportUtils.convert_quaternion_unity_to_blender(x, y, z, w, self.z_minus_is_forward))

                        for i in range(anim_bone_amount):
                            inverse_dynamic_pos_bones_map.append(-1)
                            inverse_dynamic_rot_bones_map.append(-1)
                            inverse_static_pos_bones_map.append(-1)
                            inverse_static_rot_bones_map.append(-1)
                        # Read BoneMapping
                        f.seek(8, 1)  # Skip BoneMapHeader
                        for i in range(anim_bone_amount):
                            bone_id_for_pos, used_in_frames_pos, bone_id_for_rot, used_in_frames_rot = struct.unpack("<4B", f.read(4))
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
                    self.report({"ERROR"}, f"Failed to read file at [{self.directory + file.name}]: {e}")
                    traceback.print_exc()
                    return {"CANCELLED"}

                if skeleton_data.bone_count != anim_bone_amount:
                    self.report({"ERROR"}, f"Target armature and animation don't have the same amount of bones (Target has: [{skeleton_data.bone_count}]. Animation has: [{anim_bone_amount}]). Aborting importation.")
                    return {"CANCELLED"}

                ImportUtils.debug_print(self.debug, f"[Animation Data: ]")
                ImportUtils.debug_print(self.debug, f"anim_bone_amount: {anim_bone_amount}")
                ImportUtils.debug_print(self.debug, f"total_frames: {total_frames}")
                ImportUtils.debug_print(self.debug, f"are_positions_relative_to_parent: {are_positions_relative_to_parent}")
                ImportUtils.debug_print(self.debug, f"number_of_bone_rotations_animated: {number_of_bone_rotations_animated}")
                ImportUtils.debug_print(self.debug, f"number_of_bone_positions_animated: {number_of_bone_positions_animated}")
                ImportUtils.debug_print(self.debug, f"number_of_bone_rotations_fixed: {number_of_bone_rotations_fixed}")
                ImportUtils.debug_print(self.debug, f"number_of_bone_positions_fixed: {number_of_bone_positions_fixed}")
                try:
                    # Create animation action
                    action_name = ntpath.basename(self.directory + file.name).rsplit(".", 1)[0]
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
                        iterator = 0
                        for bone_id in static_pos_bones:
                            # Assign position for static bones first
                            current_bone_name = skeleton_data.bone_names[bone_id]
                            parentboneid = skeleton_data.bone_parent_ids[bone_id]
                            loc = mathutils.Vector((0.0, 0.0, 0.0))
                            if parentboneid == 0xFFFFFFFF or bone_id == 0:
                                loc = ImportUtils.get_local_position(
                                    skeleton_data.bone_absolute_positions[bone_id],
                                    skeleton_data.bone_absolute_rotations[bone_id],
                                    fixed_positions_by_bone[iterator])
                            else:
                                if are_positions_relative_to_parent == True:
                                    # Get position of animation relative to bind local pose
                                    loc = ImportUtils.get_local_position(skeleton_data.bone_local_positions[bone_id], skeleton_data.bone_local_rotations[bone_id], fixed_positions_by_bone[iterator])
                                else:
                                    # Get local position of world animation relative to bind local pose
                                    local_animation_position = ImportUtils.get_local_position(cor_bone_pos(parentboneid, 0), cor_bone_rot(parentboneid, 0), fixed_positions_by_bone[iterator])
                                    loc = ImportUtils.get_local_position(skeleton_data.bone_local_positions[bone_id], skeleton_data.bone_local_rotations[bone_id], local_animation_position)

                            target_armature.pose.bones[current_bone_name].location = loc
                            target_armature.pose.bones[current_bone_name].keyframe_insert(data_path="location", frame=0)
                            iterator += 1
                    
                    if number_of_bone_rotations_fixed > 0:
                        iterator = 0
                        for bone_id in static_rot_bones:
                            # bone_name = armature_obj.pose.bones[bone_id].name

                            # Assign rotation for static bones
                            current_bone_name = skeleton_data.bone_names[bone_id]
                            parentboneid = skeleton_data.bone_parent_ids[bone_id]
                            rot = mathutils.Quaternion((1,0,0,0))
                            if parentboneid == 0xFFFFFFFF or bone_id == 0:
                                rot = skeleton_data.bone_absolute_rotations[bone_id].conjugated() @ fixed_rotations_by_bone[iterator]
                            else:
                                if are_positions_relative_to_parent == True:
                                    rot = skeleton_data.bone_local_rotations[bone_id].conjugated() @ fixed_rotations_by_bone[iterator]
                                else:
                                    local_animation_rotation = ImportUtils.get_local_rotation(cor_bone_rot(parentboneid, 0), fixed_rotations_by_bone[iterator])
                                    rot = skeleton_data.bone_local_rotations[bone_id].conjugated() @ local_animation_rotation

                            target_armature.pose.bones[current_bone_name].rotation_quaternion = rot
                            target_armature.pose.bones[current_bone_name].keyframe_insert(data_path="rotation_quaternion", frame=0)
                            iterator += 1
                    
                    for frame in range(total_frames):
                        if number_of_bone_positions_animated > 0:
                            iterator = 0
                            for bone_id in dynamic_pos_bones:
                                # Assign position for dynamic position bones for each frame
                                current_bone_name = skeleton_data.bone_names[bone_id]
                                parentboneid = skeleton_data.bone_parent_ids[bone_id]
                                idx = frame * number_of_bone_positions_animated + iterator
                                loc = mathutils.Vector((0.0, 0.0, 0.0))
                                if parentboneid == 0xFFFFFFFF or bone_id == 0:
                                    loc = ImportUtils.get_local_position(
                                    skeleton_data.bone_absolute_positions[bone_id] ,
                                    skeleton_data.bone_absolute_rotations[bone_id],
                                    animated_positions_by_bone[idx])
                                else:
                                    if are_positions_relative_to_parent == True:
                                        loc = ImportUtils.get_local_position(skeleton_data.bone_local_positions[bone_id], skeleton_data.bone_local_rotations[bone_id], animated_positions_by_bone[idx])
                                    else:
                                        local_animation_position = ImportUtils.get_local_position(cor_bone_pos(parentboneid, frame), cor_bone_rot(parentboneid, frame), animated_positions_by_bone[idx])
                                        loc = ImportUtils.get_local_position(skeleton_data.bone_local_positions[bone_id], skeleton_data.bone_local_rotations[bone_id], local_animation_position)

                                target_armature.pose.bones[current_bone_name].location = loc
                                target_armature.pose.bones[current_bone_name].keyframe_insert(data_path="location", frame=frame)
                                iterator += 1
                        if number_of_bone_rotations_animated > 0:
                            iterator = 0
                            for bone_id in dynamic_rot_bones:
                                # Assign rotation for dynamic rotation bones for each frame
                                current_bone_name = skeleton_data.bone_names[bone_id]
                                parentboneid = skeleton_data.bone_parent_ids[bone_id]
                                rot = mathutils.Quaternion((1,0,0,0))
                                idx = frame * number_of_bone_rotations_animated + iterator

                                if parentboneid == 0xFFFFFFFF or bone_id == 0:
                                    rot = skeleton_data.bone_absolute_rotations[bone_id].conjugated() @ animated_rotations_by_bone[idx]
                                else:
                                    if are_positions_relative_to_parent == True:
                                        rot = skeleton_data.bone_local_rotations[bone_id].conjugated() @ animated_rotations_by_bone[idx]
                                    else:
                                        local_animation_rotation = ImportUtils.get_local_rotation(cor_bone_rot(parentboneid, frame), animated_rotations_by_bone[idx])
                                        rot = skeleton_data.bone_local_rotations[bone_id].conjugated() @ local_animation_rotation

                                target_armature.pose.bones[current_bone_name].rotation_quaternion = rot
                                target_armature.pose.bones[current_bone_name].keyframe_insert(data_path="rotation_quaternion", frame=frame)
                                iterator += 1
                        
                    

                    # Set animation frames range
                    action.frame_range = (0, total_frames)

                except Exception as e:
                    animation_name = ntpath.basename(self.directory + file.name).rsplit(".", 1)[0]
                    self.report({"ERROR"}, f"Failed to create animation {animation_name}: {e}")
                    traceback.print_exc()
                    return {"CANCELLED"}
                
        
        return {"FINISHED"}

    def invoke(self, context: Context, event: Event):
        if self.directory:
            return context.window_manager.invoke_props_dialog(self)
            # return self.execute(context)
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

class CBB_FH_ImportSkinnedAnim(bpy.types.FileHandler):
    bl_idname = "CBB_FH_skinnedanim_import"
    bl_label = "File handler for skinnedanim imports"
    bl_import_operator = ImportSkinnedAnim.bl_idname
    bl_file_extensions = ImportSkinnedAnim.filename_ext

    @classmethod
    def poll_drop(cls, context):
        return (context.area and context.area.type == "VIEW_3D")

class ExportSkinnedAnim(Operator, ExportHelper):
    bl_idname = "cbb.skinnedanim_export"
    bl_label = "Export SkinnedAnim"
    bl_options = {"PRESET"}

    filename_ext = ".SkinnedAnim"

    filter_glob: StringProperty(default="*.SkinnedAnim", options={"HIDDEN"})

    directory: StringProperty(subtype="FILE_PATH")

    export_all_actions: BoolProperty(
        name="Export all actions in armatures",
        description="Enabling this option will make the exporter export all actions. Otherwise, only the current active action will be exported.",
        default=False
    )
    
    export_only_selected: BoolProperty(
        name="Export only in selected",
        description="Leave this option checked if you wish to export animations only among currently selected armatures",
        default=False
    )

    debug: BoolProperty(
        name="Debug export",
        description="Enabling this option will make the exporter print debug data to console.",
        default=False
    )

    z_minus_is_forward: BoolProperty(
        name="Z- is forward",
        description="Leave this option checked if you wish to work with Z- being the forward direction in Blender. If false, Z+ is considered forward.",
        default=True
    )
    
    only_deform_bones: BoolProperty(
        name="Consider only deform bones (Recommended)",
        description="Leave this option checked if you wish to consider only deform bones in armatures. Recommended in case you are using rigged armatures that have non-deforming bones",
        default=True
    )

    def execute(self, context):
        return self.export_animations(context, self.directory)
    
    def export_animations(self, context, directory):
        armatures_for_exportation = None
        if self.export_only_selected == True:
            armatures_for_exportation: list[bpy.types.Object] = [obj for obj in context.selected_objects if obj.type == "ARMATURE"]
        else:
            armatures_for_exportation = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]

        if not armatures_for_exportation:
            if self.export_only_selected == True:
                self.report({"ERROR"}, f"There are no objects of type ARMATURE among currently selected objects. Aborting exportation.")
            else:
                self.report({"ERROR"}, f"There are no objects of type ARMATURE among scene objects. Aborting exportation.")
            return {"CANCELLED"}
        
        
        
        for armature in armatures_for_exportation:
            skeleton_data = SkeletonData.build_skeleton_from_armature(self, armature, self.only_deform_bones, True)
            if not skeleton_data:
                print(f"Validation failed for armature: {armature.name}. Skipping.")
                continue
            
            actions = ExportSkinnedAnim.get_actions(armature, self.export_all_actions)
            for action in actions:
                ExportSkinnedAnim.export_action(self, armature, action, directory, self.filename_ext, self.only_deform_bones)
                
        return {"FINISHED"}

    def get_actions(armature, export_all_actions):
        if export_all_actions:
            return [action for action in bpy.data.actions if action.id_root == 'OBJECT']
        else:
            return [armature.animation_data.action] if armature.animation_data and armature.animation_data.action else []
        
    @staticmethod
    def export_action(self: "ExportSkinnedAnim", armature, action: Action, directory: str, filename_ext: str, only_deform_bones: bool):
        print(f"Exporting action {action.name} for armature {armature.name}")
        old_active_object = bpy.context.view_layer.objects.active
        old_selection = bpy.context.view_layer.objects.active.select_get()
        
        for fcurve in action.fcurves:
            for kp in fcurve.keyframe_points:
                ImportUtils.debug_print(self.debug,f"Fcurve data [{fcurve.data_path}][{fcurve.array_index}]: kp[{(kp.co[0])}] data: [{kp.co[1]}]")

        filepath = bpy.path.ensure_ext(directory + "/" + action.name, filename_ext)
        
        bpy.context.view_layer.objects.active = armature
        old_object_mode = bpy.context.view_layer.objects.active.mode
        
        bpy.ops.object.mode_set(mode='POSE')
        bpy.context.view_layer.update()
        
        bones: list[bpy.types.Bone] = []
        if only_deform_bones:
            bones = sorted([bone for bone in armature.data.bones if bone.use_deform], key=lambda bone: bone["bone_id"])
        else:
            bones: list[bpy.types.Bone] = sorted(armature.data.bones, key=lambda bone: bone["bone_id"])
        
        pose_bones: list[bpy.types.PoseBone] = []
        for bone in bones:
            pose_bones.append(armature.pose.bones[bone.name])

        animation_bone_amount = len(pose_bones)
        total_frames = int(action.frame_range[1] - action.frame_range[0])
        
        skeleton_data = SkeletonData.build_skeleton_from_armature(self, armature, only_deform_bones, True)
        """
        vec3_bone_local_positions = [mathutils.Vector((0,0,0))] * animation_bone_amount
        quat_bone_local_rotations = [mathutils.Quaternion.identity] * animation_bone_amount
        for bone in bones:
            bone_id = bone["bone_id"]
            edit_bone_position , edit_bone_rotation = ImportUtils.decompose_blender_matrix_position_rotation(bone.matrix_local)

            if bone.parent is not None:
                parent_edit_bone_position , parent_edit_bone_rotation = ImportUtils.decompose_blender_matrix_position_rotation(bone.parent.matrix_local)
                vec3_bone_local_positions[bone_id] = ImportUtils.get_local_position(parent_edit_bone_position, parent_edit_bone_rotation, edit_bone_position)
                quat_bone_local_rotations[bone_id] = ImportUtils.get_local_rotation(parent_edit_bone_rotation, edit_bone_rotation)
            else:
                vec3_bone_local_positions[bone_id] = edit_bone_position
                quat_bone_local_rotations[bone_id] = edit_bone_rotation
        """
        dynamic_position_bones: list[int] = []
        static_position_bones: list[int] = []
        dynamic_rotation_bones: list[int] = []
        static_rotation_bones: list[int] = []
        used_in_frames_positions_flag: list[int] = []
        used_in_frames_rotations_flag: list[int] = []

        for bone in bones:
            bone_id: int = bone["bone_id"]
            bone_path = f'pose.bones["{bone.name}"]'
            has_position_keys: bool = any(
                fcurve.data_path == f'{bone_path}.location' and any(kp.co[0] != 0 for kp in fcurve.keyframe_points)
                for fcurve in action.fcurves
            )
            has_rotation_keys: bool = any(
                fcurve.data_path == f'{bone_path}.rotation_quaternion' and any(kp.co[0] != 0 for kp in fcurve.keyframe_points)
                for fcurve in action.fcurves
            )
            position_keys_at_zero: bool = any(
                fcurve.data_path == f'{bone_path}.location' and any(kp.co[0] == 0 for kp in fcurve.keyframe_points)
                for fcurve in action.fcurves
            )
            rotation_keys_at_zero: bool = any(
                fcurve.data_path == f'{bone_path}.rotation_quaternion' and any(kp.co[0] == 0 for kp in fcurve.keyframe_points)
                for fcurve in action.fcurves
            )

            if has_position_keys and position_keys_at_zero:
                dynamic_position_bones.append(bone_id)
                used_in_frames_positions_flag.append(0xF0)
            else:
                static_position_bones.append(bone_id)
                used_in_frames_positions_flag.append(0)

            if has_rotation_keys and rotation_keys_at_zero:
                dynamic_rotation_bones.append(bone_id)
                used_in_frames_rotations_flag.append(0xF0)
            else:
                static_rotation_bones.append(bone_id)
                used_in_frames_rotations_flag.append(0)
        

        fixed_positions_by_bone: list[bpy.types.Vector] = []
        fixed_rotations_by_bone: list[bpy.types.Quaternion] = []
        bpy.context.scene.frame_set(0)
        for bone_id in static_position_bones:
            pose_bone = pose_bones[bone_id]
            pose_bone_position = ImportUtils.get_pose_bone_location_at_frame_fast(armature, pose_bone.name)
            correct_animated_position = ImportUtils.get_world_position(skeleton_data.bone_local_positions[bone_id], skeleton_data.bone_local_rotations[bone_id], pose_bone_position)
            fixed_positions_by_bone.append(ImportUtils.convert_position_blender_to_unity_vector(correct_animated_position, self.z_minus_is_forward))
        
        for bone_id in static_rotation_bones:
            pose_bone = pose_bones[bone_id]
            pose_bone_rotation = ImportUtils.get_pose_bone_rotation_at_frame_fast(armature, pose_bone.name)
            correct_animated_rotation = ImportUtils.get_world_rotation(skeleton_data.bone_local_rotations[bone_id], pose_bone_rotation)
            fixed_rotations_by_bone.append(ImportUtils.convert_quaternion_blender_to_unity_quaternion(correct_animated_rotation, self.z_minus_is_forward))
        
        animated_positions_by_bone: list[bpy.types.Vector] = []
        animated_rotations_by_bone: list[bpy.types.Quaternion] = []
        
        for frame in range(int(action.frame_range[0]), int(action.frame_range[1])):
            print(f"Assigning transforms for frame {frame}")
            
            bpy.context.scene.frame_set(int(frame))
            for bone_id in dynamic_position_bones:
                pose_bone = pose_bones[bone_id]
                pose_bone_position = ImportUtils.get_pose_bone_location_at_frame_fast(armature, pose_bone.name)
                correct_animated_position = ImportUtils.get_world_position(skeleton_data.bone_local_positions[bone_id], skeleton_data.bone_local_rotations[bone_id], pose_bone_position)
                animated_positions_by_bone.append(ImportUtils.convert_position_blender_to_unity_vector(correct_animated_position, self.z_minus_is_forward))
            
            for bone_id in dynamic_rotation_bones:
                pose_bone = pose_bones[bone_id]
                pose_bone_rotation = ImportUtils.get_pose_bone_rotation_at_frame_fast(armature, pose_bone.name)
                correct_animated_rotation = ImportUtils.get_world_rotation(skeleton_data.bone_local_rotations[bone_id], pose_bone_rotation)
                animated_rotations_by_bone.append(ImportUtils.convert_quaternion_blender_to_unity_quaternion(correct_animated_rotation, self.z_minus_is_forward))
        
        ImportUtils.debug_print(self.debug, f"Animation Data Collected:")
        ImportUtils.debug_print(self.debug, f"Animated Rotations By Bone:\n{animated_rotations_by_bone}")
        ImportUtils.debug_print(self.debug, f"Animated Positions By Bone:\n{animated_positions_by_bone}")
        ImportUtils.debug_print(self.debug, f"Fixed Positions By Bone:\n{fixed_positions_by_bone}")
        ImportUtils.debug_print(self.debug, f"Fixed Rotations By Bone:\n{fixed_rotations_by_bone}")
        ImportUtils.debug_print(self.debug, f"Bone Maps:")
        ImportUtils.debug_print(self.debug, f"Dynamic Position Bones:\n{dynamic_position_bones}")
        ImportUtils.debug_print(self.debug, f"Static Position Bones:\n{static_position_bones}")
        ImportUtils.debug_print(self.debug, f"Dynamic Rotation Bones:\n{dynamic_rotation_bones}")
        ImportUtils.debug_print(self.debug, f"Static Rotation Bones:\n{static_rotation_bones}")
        ImportUtils.debug_print(self.debug, f"Used In Frames Positions Flag:\n{used_in_frames_positions_flag}")
        ImportUtils.debug_print(self.debug, f"Used In Frames Rotations Flag:\n{used_in_frames_rotations_flag}")

        with open(filepath, 'wb') as file:
            # Helper function to write an integer
            def write_int(value):
                file.write(value.to_bytes(4, byteorder='little', signed=False))
            
            # Helper function to write a float
            def write_float(value):
                file.write(bytearray(struct.pack('f', value)))

            def write_byte(value: int):
                file.write(value.to_bytes(1, byteorder='little', signed=False))
            
            # Writing static header data
            write_int(1040676)
            write_int(8246869)
            file_size_position = file.tell()
            write_int(0)  # Placeholder for total size
            write_int(163761)
            write_int(0)
            write_int(1)
            write_int(34231528)
            write_int(52)
            write_int(34231528)
            write_int(0)
            write_int(0)
            write_int(35741130)
            write_int(12)
            for _ in range(3): write_float(0.0)
            write_int(57751914)
            write_int(12)
            for _ in range(3): write_float(10.0)
            write_int(4831592)
            write_int(12)
            for _ in range(3): write_float(5.0)
            write_int(56946838)
            write_int(12)
            for _ in range(3): write_float(10.0)
            write_int(977004)
            write_int(4)
            write_int(animation_bone_amount)
            write_int(45797634)
            write_int(4)
            write_int(total_frames)
            write_int(4364479)
            write_int(1)
            file.write(bytearray([1]))  # bool true as a single byte
            write_int(7986641)
            write_int(4)
            write_int(len(dynamic_rotation_bones))
            write_int(33191686)
            write_int(4)
            write_int(len(dynamic_position_bones))
            write_int(61737251)
            write_int(4)
            write_int(len(static_rotation_bones))
            write_int(22942296)
            write_int(4)
            write_int(len(static_position_bones))

            # Writing animated rotations
            write_int(18854571)
            write_int(len(animated_rotations_by_bone) * 16)
            for quat in animated_rotations_by_bone:
                for component in quat:
                    write_float(component)

            # Writing animated positions
            write_int(36183766)
            write_int(len(animated_positions_by_bone) * 12)
            for vec in animated_positions_by_bone:
                for component in vec:
                    write_float(component)

            # Writing fixed positions
            write_int(27595076)
            write_int(len(fixed_positions_by_bone) * 12)
            for vec in fixed_positions_by_bone:
                for component in vec:
                    write_float(component)

            # Writing fixed rotations
            write_int(10265881)
            write_int(len(fixed_rotations_by_bone) * 16)
            for quat in fixed_rotations_by_bone:
                for component in quat:
                    write_float(component)

            write_int(30362205)
            write_int(animation_bone_amount * 4)

            # Preparing bone usage collections
            used_in_frames_positions = []
            not_used_in_frames_positions = []
            used_in_frames_rotations = []
            not_used_in_frames_rotations = []

            for i in range(animation_bone_amount):
                if used_in_frames_positions_flag[i] == 0xF0:
                    used_in_frames_positions.append(len(used_in_frames_positions))
                else:
                    not_used_in_frames_positions.append(len(not_used_in_frames_positions))

                if used_in_frames_rotations_flag[i] == 0xF0:
                    used_in_frames_rotations.append(len(used_in_frames_rotations))
                else:
                    not_used_in_frames_rotations.append(len(not_used_in_frames_rotations))

            # Writing the bone map structure
            for i in range(animation_bone_amount):
                if used_in_frames_positions_flag[i] == 0xF0:
                    write_byte(used_in_frames_positions.pop(0))
                else:
                    write_byte(not_used_in_frames_positions.pop(0))
                write_byte(used_in_frames_positions_flag[i])

                if used_in_frames_rotations_flag[i] == 0xF0:
                    write_byte(used_in_frames_rotations.pop(0))
                else:
                    write_byte(not_used_in_frames_rotations.pop(0))
                write_byte(used_in_frames_rotations_flag[i])

            # Writing the total size of the file
            file_size = file.tell()
            file.seek(file_size_position)
            write_int(file_size - 12)
            file.seek(0, 2)  # Go back to the end of the file
            
        bpy.context.view_layer.objects.active.select_set(old_selection)
        bpy.ops.object.mode_set(mode=old_object_mode)
        bpy.context.view_layer.objects.active = old_active_object

    
        


def menu_func_import(self, context):
    self.layout.operator(ImportSkinnedAnim.bl_idname, text="SkinnedAnim (.SkinnedAnim)")

def menu_func_export(self, context):
    self.layout.operator(ExportSkinnedAnim.bl_idname, text="SkinnedAnim (.SkinnedAnim)")



def register():
    bpy.utils.register_class(ImportSkinnedAnim)
    bpy.utils.register_class(CBB_FH_ImportSkinnedAnim)
    bpy.utils.register_class(ExportSkinnedAnim)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.utils.unregister_class(ImportSkinnedAnim)
    bpy.utils.unregister_class(CBB_FH_ImportSkinnedAnim)
    bpy.utils.unregister_class(ExportSkinnedAnim)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

if __name__ == "__main__":
    register()
