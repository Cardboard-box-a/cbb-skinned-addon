import bpy
import struct
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.types import Context, Event, Operator, ActionFCurves, FCurve, Action
from bpy.props import CollectionProperty, StringProperty, BoolProperty
from bpy_extras.io_utils import ImportHelper
import traceback
from utils import Utils, CoordsSys
import xml.etree.ElementTree as ET
from ..core.skeleton_core import SkeletonData
Serializer = Utils.Serializer
CoordinatesConverter = Utils.CoordinatesConverter
from pathlib import Path
from ..core.animation_core import import_animation_from_files
from ..ui.ui_properties import LuniaProperties, AnimationProperties

class CBB_OT_SkinnedAnimImporter(Operator, ImportHelper):
    bl_idname = "cbb.skinnedanim_import"
    bl_label = "Import SkinnedAnim"
    bl_options = {"PRESET", "UNDO"}

    filename_ext = ".SkinnedAnim"

    filter_glob: StringProperty(default="*.SkinnedAnim", options={"HIDDEN"}) # type: ignore

    files: CollectionProperty(
        type=bpy.types.OperatorFileListElement,
        options={"HIDDEN", "SKIP_SAVE"}
    ) # type: ignore

    directory: StringProperty(subtype="FILE_PATH") # type: ignore

    apply_to_armature_in_selected: BoolProperty(
        name="Apply to armature in selected",
        description="Enabling this option will make the import of the animation to target any armature present between currently selected objects",
        default=False
    ) # type: ignore

    debug: BoolProperty(
        name="Debug import",
        description="Enabling this option will make the importer print debug data to console",
        default=False
    ) # type: ignore

    def execute(self, context):
        return_value = {"CANCELLED"}
        for file in self.files:
            result = import_animation_from_files(self.debug, file.name, self.directory, self.apply_to_armature_in_selected, operator=self)
            if result == {"FINISHED"}:
                return_value = {"FINISHED"}
        return return_value

    def invoke(self, context: Context, event: Event):
        if self.directory:
            return context.window_manager.invoke_props_dialog(self)
            # return self.execute(context)
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

class CBB_OT_SkinnedAnimImporterLoaded(Operator):
    bl_idname = "cbb.skinnedanim_import_from_panel"
    bl_label = "Import SkinnedAnim"
    bl_options = { "UNDO"}

    apply_to_armature_in_selected: BoolProperty(
        name="Apply to armature in selected",
        description="Enabling this option will make the import of the animation to target any armature present between currently selected objects",
        default=False
    ) # type: ignore

    debug: BoolProperty(
        name="Debug import",
        description="Enabling this option will make the importer print debug data to console",
        default=False
    ) # type: ignore

    def execute(self, context):
        props: LuniaProperties = context.scene.lunia_props
        
        return_value = {"CANCELLED"}
        for animation_data in props.animation_data:
            if animation_data.selected == False:
                continue
            result = import_animation_from_files(self.debug, animation_data.animation_file_path, props.main_directory, self.apply_to_armature_in_selected, str(Path(props.skeleton_file_name).stem), self)
            if result == {"FINISHED"}:
                return_value = {"FINISHED"}
                
        return return_value

class CBB_FH_ImportSkinnedAnim(bpy.types.FileHandler):
    bl_idname = "CBB_FH_skinnedanim_import"
    bl_label = "File handler for skinnedanim imports"
    bl_import_operator = CBB_OT_SkinnedAnimImporter.bl_idname
    bl_file_extensions = CBB_OT_SkinnedAnimImporter.filename_ext

    @classmethod
    def poll_drop(cls, context):
        return (context.area and context.area.type == "VIEW_3D")

class CBB_OT_SkinnedAnimExporter(Operator, ExportHelper):
    bl_idname = "cbb.skinnedanim_export"
    bl_label = "Export SkinnedAnim"
    bl_options = {"PRESET"}

    filename_ext = ".SkinnedAnim"

    filter_glob: StringProperty(default="*.SkinnedAnim", options={"HIDDEN"}) # type: ignore

    directory: StringProperty(subtype="FILE_PATH") # type: ignore

    export_all_actions: BoolProperty(
        name="Export all actions in armatures",
        description="Enabling this option will make the exporter export all actions. Otherwise, only the current active action will be exported.",
        default=False
    ) # type: ignore
    
    export_only_selected: BoolProperty(
        name="Export only in selected",
        description="Leave this option checked if you wish to export animations only among currently selected armatures",
        default=False
    ) # type: ignore

    debug: BoolProperty(
        name="Debug export",
        description="Enabling this option will make the exporter print debug data to console.",
        default=False
    ) # type: ignore
    
    only_deform_bones: BoolProperty(
        name="Consider only deform bones (Recommended)",
        description="Leave this option checked if you wish to consider only deform bones in armatures. Recommended in case you are using rigged armatures that have non-deforming bones",
        default=True
    ) # type: ignore

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
        
        msg_handler = Utils.MessageHandler(self.debug, self.report)
        
        for armature in armatures_for_exportation:
            skeleton_data = SkeletonData.build_skeleton_from_armature(armature, self.only_deform_bones, True, msg_handler)
            if not skeleton_data:
                print(f"Validation failed for armature: {armature.name}. Skipping.")
                continue
            
            actions = CBB_OT_SkinnedAnimExporter.get_actions(armature, self.export_all_actions)
            for action in actions:
                CBB_OT_SkinnedAnimExporter.export_action(self, armature, action, directory, self.filename_ext, self.only_deform_bones, msg_handler)
                
        return {"FINISHED"}

    def get_actions(armature, export_all_actions):
        if export_all_actions:
            return [action for action in bpy.data.actions if action.id_root == 'OBJECT']
        else:
            return [armature.animation_data.action] if armature.animation_data and armature.animation_data.action else []
        
    @staticmethod
    def export_action(self: "CBB_OT_SkinnedAnimExporter", armature: bpy.types.Object, action: Action, directory: str, filename_ext: str, only_deform_bones: bool, msg_handler: Utils.MessageHandler):
        print(f"Exporting action {action.name} for armature {armature.name}")
        
        old_active_object = bpy.context.view_layer.objects.active
        old_active_selected = bpy.context.view_layer.objects.active.select_get()
        old_selection = [obj for obj in bpy.context.selected_objects]
        old_active_action = bpy.context.view_layer.objects.active.animation_data.action
        
        bpy.ops.object.select_all(action='DESELECT')
        
        bpy.context.view_layer.objects.active = armature
        bpy.context.view_layer.objects.active.select_set(True)
        bpy.context.view_layer.objects.active.animation_data.action = action
        
        old_armature_mode = bpy.context.view_layer.objects.active.mode
        
        bpy.ops.nla.bake(
            frame_start=int(action.frame_range[0]),
            frame_end=int(action.frame_range[1]),
            only_selected=False,
            visual_keying=True,
            clear_constraints=False,
            use_current_action=False,
            bake_types={'POSE'}
        )
        
        baked_action = armature.animation_data.action
        
        bpy.ops.object.mode_set(mode='POSE')
        bpy.context.view_layer.update()
        
        
        bones: list[bpy.types.Bone] = []
        if only_deform_bones:
            bones = sorted([bone for bone in armature.data.bones if bone.use_deform], key=lambda bone: bone["bone_id"])
        else:
            bones: list[bpy.types.Bone] = sorted(armature.data.bones, key=lambda bone: bone["bone_id"])
        
        pose_bones = [armature.pose.bones[bone.name] for bone in bones]
        
        
        
        
        
        for fcurve in action.fcurves:
            for kp in fcurve.keyframe_points:
                msg_handler.debug_print(f"Fcurve data [{fcurve.data_path}][{fcurve.array_index}]: kp[{(kp.co[0])}] data: [{kp.co[1]}]")
        
        filepath = (Path(directory) / action.name).with_suffix(filename_ext)
        
        animation_bone_amount = len(pose_bones)
        initial_frame = baked_action.frame_range[0]
        last_frame = baked_action.frame_range[1]
        # +1 to include the last frame
        total_frames = int(last_frame+1 - initial_frame)
        
        skeleton_data = SkeletonData.build_skeleton_from_armature(armature, only_deform_bones, True, msg_handler)
        dynamic_position_bones: list[int] = []
        static_position_bones: list[int] = []
        dynamic_rotation_bones: list[int] = []
        static_rotation_bones: list[int] = []
        used_in_frames_positions_flag: list[int] = []
        used_in_frames_rotations_flag: list[int] = []
        
        for bone in bones:
            bone_id: int = bone["bone_id"]
            bone_path = f'pose.bones["{bone.name}"]'
            
            position_key_values = set(
                kp.co[1]
                for fcurve in baked_action.fcurves
                if fcurve.data_path == f'{bone_path}.location'
                for kp in fcurve.keyframe_points
            )
            has_position_keyframes = len(position_key_values) > 1
            
            rotation_key_values = set(
                kp.co[1]
                for fcurve in baked_action.fcurves
                if fcurve.data_path == f'{bone_path}.rotation_quaternion'
                for kp in fcurve.keyframe_points
            )
            
            has_rotation_keyframes = len(rotation_key_values) > 1
            
            if has_position_keyframes:
                dynamic_position_bones.append(bone_id)
                used_in_frames_positions_flag.append(0xF0)
            else:
                static_position_bones.append(bone_id)
                used_in_frames_positions_flag.append(0)

            if has_rotation_keyframes:
                dynamic_rotation_bones.append(bone_id)
                used_in_frames_rotations_flag.append(0xF0)
            else:
                static_rotation_bones.append(bone_id)
                used_in_frames_rotations_flag.append(0)
        

        fixed_positions_by_bone: list[bpy.types.Vector] = []
        fixed_rotations_by_bone: list[bpy.types.Quaternion] = []
        
        for bone_id in static_position_bones:
            pose_bone = pose_bones[bone_id]
            pose_bone_position = Utils.get_pose_bone_location_at_frame_fcurves(baked_action, pose_bone.name, initial_frame)
            correct_animated_position = Utils.get_world_position(skeleton_data.bone_local_positions[bone_id], skeleton_data.bone_local_rotations[bone_id], pose_bone_position)
            fixed_positions_by_bone.append(correct_animated_position)
        
        for bone_id in static_rotation_bones:
            pose_bone = pose_bones[bone_id]
            pose_bone_rotation = Utils.get_pose_bone_rotation_at_frame_fcurves(baked_action, pose_bone.name, initial_frame)
            correct_animated_rotation = Utils.get_world_rotation(skeleton_data.bone_local_rotations[bone_id], pose_bone_rotation)
            fixed_rotations_by_bone.append(correct_animated_rotation)
        
        animated_positions_by_bone: list[bpy.types.Vector] = []
        animated_rotations_by_bone: list[bpy.types.Quaternion] = []
        
        msg_handler.debug_print(f"Animation [{action.name}] frame range: {int(action.frame_range[0])} - {int(action.frame_range[1])}")
        
        for frame in range(int(action.frame_range[0]), int(action.frame_range[1]+1)):
            print(f"Assigning transforms for frame {frame}")
            
            for bone_id in dynamic_position_bones:
                pose_bone = pose_bones[bone_id]
                pose_bone_position = Utils.get_pose_bone_location_at_frame_fcurves(baked_action, pose_bone.name, frame)
                correct_animated_position = Utils.get_world_position(skeleton_data.bone_local_positions[bone_id], skeleton_data.bone_local_rotations[bone_id], pose_bone_position)
                animated_positions_by_bone.append(correct_animated_position)
            
            for bone_id in dynamic_rotation_bones:
                pose_bone = pose_bones[bone_id]
                pose_bone_rotation = Utils.get_pose_bone_rotation_at_frame_fcurves(baked_action, pose_bone.name, frame)
                correct_animated_rotation = Utils.get_world_rotation(skeleton_data.bone_local_rotations[bone_id], pose_bone_rotation)
                animated_rotations_by_bone.append(correct_animated_rotation)
        
        #debugger.print(f"Animation Data Collected:")
        #debugger.print(f"Animated Rotations By Bone:\n{animated_rotations_by_bone}")
        #debugger.print(f"Animated Positions By Bone:\n{animated_positions_by_bone}")
        #debugger.print(f"Fixed Positions By Bone:\n{fixed_positions_by_bone}")
        #debugger.print(f"Fixed Rotations By Bone:\n{fixed_rotations_by_bone}")
        
        msg_handler.debug_print(f"Bone Maps:")
        msg_handler.debug_print(f"Dynamic Position Bones:\n{dynamic_position_bones}")
        msg_handler.debug_print(f"Static Position Bones:\n{static_position_bones}")
        msg_handler.debug_print(f"Dynamic Rotation Bones:\n{dynamic_rotation_bones}")
        msg_handler.debug_print(f"Static Rotation Bones:\n{static_rotation_bones}")
        msg_handler.debug_print(f"Used In Frames Positions Flag:\n{used_in_frames_positions_flag}")
        msg_handler.debug_print(f"Used In Frames Rotations Flag:\n{used_in_frames_rotations_flag}")
        
        co_conv = CoordinatesConverter(CoordsSys.Blender, CoordsSys.Unity)
        
        with open(filepath, 'wb') as opened_file:
            writer = Serializer(opened_file, Serializer.Endianness.Little, Serializer.Quaternion_Order.XYZW, Serializer.Matrix_Order.RowMajor, co_conv)
            
            # Writing static header data
            writer.write_uint(1040676)
            writer.write_uint(8246869)
            file_size_position = opened_file.tell()
            writer.write_uint(0)  # Placeholder for total size
            writer.write_uint(163761)
            writer.write_uint(0)
            writer.write_uint(1)
            writer.write_uint(34231528)
            writer.write_uint(52)
            writer.write_uint(34231528)
            writer.write_uint(0)
            writer.write_uint(0)
            writer.write_uint(35741130)
            writer.write_uint(12)
            for _ in range(3): writer.write_float(0.0)
            writer.write_uint(57751914)
            writer.write_uint(12)
            for _ in range(3): writer.write_float(10.0)
            writer.write_uint(4831592)
            writer.write_uint(12)
            for _ in range(3): writer.write_float(5.0)
            writer.write_uint(56946838)
            writer.write_uint(12)
            for _ in range(3): writer.write_float(10.0)
            writer.write_uint(977004)
            writer.write_uint(4)
            writer.write_uint(animation_bone_amount)
            writer.write_uint(45797634)
            writer.write_uint(4)
            writer.write_uint(total_frames)
            writer.write_uint(4364479)
            writer.write_uint(1)
            opened_file.write(bytearray([1]))  # bool true as a single byte
            writer.write_uint(7986641)
            writer.write_uint(4)
            writer.write_uint(len(dynamic_rotation_bones))
            writer.write_uint(33191686)
            writer.write_uint(4)
            writer.write_uint(len(dynamic_position_bones))
            writer.write_uint(61737251)
            writer.write_uint(4)
            writer.write_uint(len(static_rotation_bones))
            writer.write_uint(22942296)
            writer.write_uint(4)
            writer.write_uint(len(static_position_bones))

            # Writing animated rotations
            writer.write_uint(18854571)
            writer.write_uint(len(animated_rotations_by_bone) * 16)
            for quat in animated_rotations_by_bone:
                writer.write_converted_quaternion(quat)

            # Writing animated positions
            writer.write_uint(36183766)
            writer.write_uint(len(animated_positions_by_bone) * 12)
            for vec in animated_positions_by_bone:
                writer.write_converted_vector3f(vec)

            # Writing fixed positions
            writer.write_uint(27595076)
            writer.write_uint(len(fixed_positions_by_bone) * 12)
            for vec in fixed_positions_by_bone:
                writer.write_converted_vector3f(vec)

            # Writing fixed rotations
            writer.write_uint(10265881)
            writer.write_uint(len(fixed_rotations_by_bone) * 16)
            for quat in fixed_rotations_by_bone:
                writer.write_converted_quaternion(quat)

            writer.write_uint(30362205)
            writer.write_uint(animation_bone_amount * 4)

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
                    writer.write_ubyte(used_in_frames_positions.pop(0))
                else:
                    writer.write_ubyte(not_used_in_frames_positions.pop(0))
                writer.write_ubyte(used_in_frames_positions_flag[i])

                if used_in_frames_rotations_flag[i] == 0xF0:
                    writer.write_ubyte(used_in_frames_rotations.pop(0))
                else:
                    writer.write_ubyte(not_used_in_frames_rotations.pop(0))
                writer.write_ubyte(used_in_frames_rotations_flag[i])

            # Writing the total size of the file
            file_size = opened_file.tell()
            opened_file.seek(file_size_position)
            writer.write_uint(file_size - 12)
            opened_file.seek(0, 2)  # Go back to the end of the file
        
        bpy.context.view_layer.objects.active.animation_data.action = old_active_action
        
        bpy.data.actions.remove(baked_action, do_unlink=True)
        
        bpy.ops.object.mode_set(mode=old_armature_mode)
        bpy.ops.object.select_all(action='DESELECT')
        
        
        bpy.context.view_layer.objects.active = old_active_object
        bpy.context.view_layer.objects.active.select_set(old_active_selected)
        
        for obj in old_selection:
            obj.select_set(True)


def menu_func_import(self, context):
    self.layout.operator(CBB_OT_SkinnedAnimImporter.bl_idname, text="SkinnedAnim (.SkinnedAnim)")

def menu_func_export(self, context):
    self.layout.operator(CBB_OT_SkinnedAnimExporter.bl_idname, text="SkinnedAnim (.SkinnedAnim)")

classes = (
    CBB_OT_SkinnedAnimImporter,
    CBB_FH_ImportSkinnedAnim,
    CBB_OT_SkinnedAnimExporter,
    CBB_OT_SkinnedAnimImporterLoaded,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

if __name__ == "__main__":
    register()
