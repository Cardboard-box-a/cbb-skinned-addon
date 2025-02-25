import bpy
import traceback
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.types import Context, Event, Operator
from bpy.props import CollectionProperty, StringProperty, BoolProperty
from mathutils import Vector, Quaternion, Matrix
from utils import Utils
Serializer = Utils.Serializer
CoordinatesConverter = Utils.CoordinatesConverter
from pathlib import Path
from ..core.skeleton_core import SkeletonData, import_skeleton
from ..ui.ui_properties import LuniaProperties


# Very small bones get deleted automatically by Blender, so we need a minimum length to ensure bones aren't deleted while importing.


class CBB_OT_SkeletonImporter(Operator, ImportHelper):
    bl_idname = "cbb.skeleton_importer"
    bl_label = "Import Skeleton"
    bl_options = {"PRESET", "UNDO"}

    filename_ext = ".Skeleton"

    filter_glob: StringProperty(default=f"*.{filename_ext}", options={"HIDDEN"}) # type: ignore

    files: CollectionProperty(
        type=bpy.types.OperatorFileListElement,
        options={"HIDDEN", "SKIP_SAVE"}
    ) # type: ignore

    directory: StringProperty(subtype="FILE_PATH") # type: ignore

    debug: BoolProperty(
        name="Debug import",
        description="Enabling this option will make the importer print debug data to console",
        default=False
    ) # type: ignore

    def execute(self, context):
        return_value = {"CANCELLED"}
        for file in self.files:
            result = import_skeleton(self.debug, file.name, self.directory, operator=self)
            if result == {"FINISHED"}:
                return_value = {"FINISHED"}
        return return_value

    def invoke(self, context: Context, event: Event):
        if self.directory:
            return context.window_manager.invoke_props_dialog(self)
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

class CBB_OT_SkeletonImportLoaded(Operator):
    bl_idname = "cbb.skeleton_import_from_panel"
    bl_label = "Import Skeleton"
    bl_options = {"UNDO"}

    debug: BoolProperty(
        name="Debug import",
        description="Enabling this option will make the importer print debug data to console",
        default=False
    ) # type: ignore

    def execute(self, context):
        props: LuniaProperties = context.scene.lunia_props
        
        return import_skeleton(self.debug, props.skeleton_file_name, props.main_directory, operator=self)


class CBB_FH_SkeletonImporter(bpy.types.FileHandler):
    bl_idname = "CBB_FH_skeleton_importer"
    bl_label = "File handler for skeleton imports"
    bl_import_operator = CBB_OT_SkeletonImporter.bl_idname
    bl_file_extensions = CBB_OT_SkeletonImporter.filename_ext

    @classmethod
    def poll_drop(cls, context):
        return (context.area and context.area.type == "VIEW_3D")

class CBB_OT_SkeletonExporter(Operator, ExportHelper):
    bl_idname = "cbb.skeleton_exporter"
    bl_label = "Export Skeleton"
    bl_options = {"PRESET"}

    filename_ext = CBB_OT_SkeletonImporter.filename_ext

    filter_glob: StringProperty(default=f"*{filename_ext}",options={"HIDDEN"}) # type: ignore

    directory: StringProperty(subtype="FILE_PATH") # type: ignore

    debug: BoolProperty(
        name="Debug export",
        description="Enabling this option will make the exporter print debug data to console",
        default=False
    ) # type: ignore

    reassign_missing_armature_ids: BoolProperty(
        name="Reassign missing armature bone IDs",
        description="Enabling this option will rebuild any missing IDs in any bone in the armature",
        default=False
    ) # type: ignore
    
    export_only_selected: BoolProperty(
        name="Export only selected",
        description="Leave this option checked if you wish export only skeletons among currently selected objects",
        default=False
    ) # type: ignore
    
    only_deform_bones: BoolProperty(
        name="Consider only deform bones (Recommended)",
        description="Leave this option checked if you wish to consider only deform bones in armatures. Recommended in case you are using rigged armatures that have non-deforming bones",
        default=True
    ) # type: ignore

    def execute(self, context):
        return self.export_skeletons(context, self.directory)

    def export_skeletons(self: "CBB_OT_SkeletonExporter", context: bpy.types.Context, directory: str):
        objects_for_exportation = None
        if self.export_only_selected == True:
            objects_for_exportation: list[bpy.types.Object] = [obj for obj in context.selected_objects if obj.type == "ARMATURE"]
        else:
            objects_for_exportation = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]

        if not objects_for_exportation:
            if self.export_only_selected == True:
                self.report({"ERROR"}, f"There are no objects of type ARMATURE among currently selected objects. Aborting exportation.")
            else:
                self.report({"ERROR"}, f"There are no objects of type ARMATURE among scene objects. Aborting exportation.")
            return {"CANCELLED"}
        
        msg_handler = Utils.MessageHandler(self.debug, self.report)
        
        for armature_object_export in objects_for_exportation:
            def export_skeleton(armature_object: bpy.types.Armature):
                filepath: str = Path(directory + armature_object.name).with_suffix(self.filename_ext)
                
                msg_handler.debug_print(f"Exporting armature [{armature_object.name}] to file at [{filepath}]")

                    
                if self.reassign_missing_armature_ids:
                    rebuilding_result = Utils.rebuild_armature_bone_ids(self, armature_object, self.only_deform_bones, msg_handler)
                    if rebuilding_result == False:
                        return
                    
                skeleton_data = SkeletonData.build_skeleton_from_armature(armature_object, self.only_deform_bones, True, msg_handler)
                
                if skeleton_data is None:
                    return
                
                try:
                    # Write the skeleton data to the file
                    SkeletonData.write_skeleton_data(filepath, skeleton_data, msg_handler)
                except Exception as e:
                    self.report({"ERROR"}, f"Failed to export skeleton: {e}")
                    traceback.print_exc()
                    return
            
            export_skeleton(armature_object_export)


        return {"FINISHED"}

class CBB_OT_ArmatureValidator(Operator):
    bl_idname = "cbb.armature_validator"
    bl_label = "Check If Armature Is Valid"
    bl_description = "Validates if the currently active object is an armature and is valid"
    bl_options = {'REGISTER'}

    debug: BoolProperty(
        name="Debug operation",
        description="Enabling this option will make the id rebuilder print debug data to console",
        default=False
    ) # type: ignore
    
    only_deform_bones: BoolProperty(
        name="Consider only deform bones (Recommended)",
        description="Leave this option checked if you wish to consider only deform bones in armatures",
        default=True
    ) # type: ignore
    
    check_for_exportation: BoolProperty(
        name="Check for exportation",
        description="Enabling this option will make the validator check if the armature is valid for exportation. Only for importation if false",
        default=True
    ) # type: ignore

    def execute(self, context):
        object = context.active_object
        if object is not None:
            if object.type == "ARMATURE":
                msg_handler = Utils.MessageHandler(self.debug, self.report)
                validation_skeleton_data = SkeletonData.build_skeleton_from_armature(object, self.only_deform_bones, self.check_for_exportation, msg_handler)
                is_valid = True if validation_skeleton_data is not None else False
                self.report({'INFO'}, f"[{context.active_object.name}] validation result: {is_valid}")
                return {'FINISHED'}
            else:
                self.report({'INFO'}, f"[{context.active_object.name}] is not an armature, there is no validation to be made.")
        return {'CANCELLED'}
    
    def invoke(self, context: Context, event: Event):
        return context.window_manager.invoke_props_dialog(self)

class CBB_OT_ArmatureBoneIDRebuilder(Operator):
    bl_idname = "cbb.armature_bone_id_rebuild"
    bl_label = "Rebuild Bone IDs for Armature"
    bl_description = "As long as the armature has a root or base bone with a bone_id of 0, this function rebuilds all invalid bone_ids."
    bl_options = {'REGISTER', "UNDO"}

    only_deform_bones: BoolProperty(
        name="Consider only deform bones (Recommended)",
        description="Leave this option checked if you wish to consider only deform bones in armatures",
        default=True
    ) # type: ignore
    
    debug: BoolProperty(
        name="Debug operation",
        description="Enabling this option will make the id rebuilder print debug data to console",
        default=False
    ) # type: ignore
    
    def execute(self, context):
        if context.active_object is not None:
            debugger = Utils.MessageHandler(self.debug)
            
            if context.active_object.type == "ARMATURE":
                rebuild_result = Utils.rebuild_armature_bone_ids(self, context.active_object, self.only_deform_bones, debugger)
                self.report({'INFO'}, f"[{context.active_object.name}] bone_id rebuilding result: {rebuild_result}")
                return {'FINISHED'}
            else:
                self.report({'INFO'}, f"[{context.active_object.name}] is not an armature, there is no validation to be made.")
        return {'CANCELLED'}
    
    def invoke(self, context: Context, event: Event):
        return context.window_manager.invoke_props_dialog(self)
    
class CBB_OT_MeshWeightRetargeter(Operator):
    bl_idname = "cbb.mesh_weight_retargeter"
    bl_label = "Retarget meshes weights to skeleton"
    bl_description = "If any mesh within selected meshes have vertex groups with numbers as their names, retarget these groups to the respective bone within an armature. Also adds an armature modifier if there are none and checks if the target armature is correct"
    bl_options = {'REGISTER', "UNDO"}

    only_deform_bones: BoolProperty(
        name="Consider only deform bones (Recommended)",
        description="Leave this option checked if you wish to consider only deform bones in armatures",
        default=True
    ) # type: ignore
    
    debug: BoolProperty(
        name="Debug operation",
        description="Enabling this option will make the weight retargeter print debug data to console",
        default=False
    ) # type: ignore
    
    def execute(self, context):
        selected_objects = context.selected_objects
        
        # Check for armature
        armatures = [obj for obj in selected_objects if obj.type == 'ARMATURE']
        if len(armatures) == 0:
            self.report({"ERROR"}, "No armature found among selected objects.")
            return {'CANCELLED'}
        elif len(armatures) > 1:
            self.report({"ERROR"}, "Multiple armatures found among selected objects. Please select only one armature.")
            return {'CANCELLED'}
        armature = armatures[0]
        msg_handler = Utils.MessageHandler(self.debug, self.report)
        skeleton_data = SkeletonData.build_skeleton_from_armature(armature, self.only_deform_bones, False, msg_handler)
        if skeleton_data is None:
            self.report({"ERROR"}, f"Armature [{armature.name}] is not valid for retargeting.")
            return {'CANCELLED'}
        
        meshes = [obj for obj in selected_objects if obj.type == 'MESH']
        if not meshes:
            self.report({"ERROR"}, "No mesh objects found among selected objects.")
            return {'CANCELLED'}
        
        # Process each mesh
        for mesh in meshes:
            existing_modifier = None
            for mod in mesh.modifiers:
                if mod.type == "ARMATURE":
                    existing_modifier = mod
                    break
            
            if not existing_modifier:
                existing_modifier = mesh.modifiers.new(name="Armature", type="ARMATURE")
                existing_modifier.object = armature
            else:
                if mod.object != armature:
                    mod.object = armature
            
            for vertex_group in mesh.vertex_groups:
                try:
                    vertex_group_id = int(vertex_group.name)
                except ValueError:
                    continue  
                
                if vertex_group_id < skeleton_data.bone_count:
                    vertex_group.name = skeleton_data.bone_names[vertex_group_id]
                    Utils.debug_print(self.debug, f"Vertex group {vertex_group_id} in mesh {mesh.name} renamed to {skeleton_data.bone_names[vertex_group_id]}.")
        
        self.report({"INFO"}, "Mesh weights retargeting completed.")
        return {'FINISHED'}

    
    def invoke(self, context: Context, event: Event):
        return context.window_manager.invoke_props_dialog(self)

class CBB_MT_UtilsMenu(bpy.types.Menu):
    bl_label = "CBB Tools"
    bl_idname = "CBB_MT_UtilsMenu"

    def draw(self, context):
        layout = self.layout
        layout.operator("cbb.armature_validator")
        layout.operator("cbb.armature_bone_id_rebuild")
        layout.operator("cbb.mesh_weight_retargeter")
        
def draw_custom_menu(self, context):
    layout = self.layout
    layout.separator()
    layout.menu(CBB_MT_UtilsMenu.bl_idname)

def menu_func_import(self, context):
    self.layout.operator(CBB_OT_SkeletonImporter.bl_idname, text="Skeleton (.Skeleton)")

def menu_func_export(self, context):
    self.layout.operator(CBB_OT_SkeletonExporter.bl_idname, text="Skeleton (.Skeleton)")

classes = (
    CBB_OT_SkeletonImporter,
    CBB_FH_SkeletonImporter,
    CBB_OT_SkeletonExporter,
    CBB_OT_ArmatureValidator,
    CBB_OT_ArmatureBoneIDRebuilder,
    CBB_MT_UtilsMenu,
    CBB_OT_MeshWeightRetargeter,
    CBB_OT_SkeletonImportLoaded
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_object.append(draw_custom_menu)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    bpy.types.VIEW3D_MT_object.remove(draw_custom_menu)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

if __name__ == "__main__":
    register()
