import bpy
import struct
import ntpath
import traceback
import mathutils
from bpy_extras.io_utils import ImportHelper
from bpy.types import Operator
from bpy.props import StringProperty
from mathutils import Vector, Quaternion, Matrix
import math
import xml.etree.ElementTree as ET
import os
from collections import OrderedDict

already_registered = False

class ImportUtils(Operator):
    bl_idname = "cbb.import_utils"
    bl_label = "Import Utils"
    bl_options = {'PRESET', 'UNDO'}

    @staticmethod
    def get_local_position(parent_position: Vector, parent_rotation: Quaternion, child_position: Vector) -> Vector:
        """
        Convert the child's world position to local position relative to the parent's position and rotation.

        :param parent_position: mathutils.Vector representing the parent's position.
        :param parent_rotation: mathutils.Quaternion representing the parent's rotation.
        :param child_position: mathutils.Vector representing the child's world position.
        :return: mathutils.Vector representing the child's local position.
        """
        
        # Calculate the relative position
        relative_position = child_position - parent_position

        # Calculate the local position
        local_position = parent_rotation.conjugated() @ relative_position
        return local_position
    
    @staticmethod
    def get_world_position(parent_position: Vector, parent_rotation: Quaternion, child_local_position: Vector) -> Vector:
        """
        Convert the child's local position to world position relative to the parent's position and rotation.

        :param parent_position: mathutils.Vector representing the parent's position.
        :param parent_rotation: mathutils.Quaternion representing the parent's rotation.
        :param child_local_position: mathutils.Vector representing the child's local position.
        :return: mathutils.Vector representing the child's world position.
        """
        # Calculate the world position
        world_position = parent_position + parent_rotation @ child_local_position
        return world_position
    
    @staticmethod
    def get_local_rotation(parent_rotation: Quaternion, child_rotation: Quaternion) -> Quaternion:
        """
        Convert the child's world rotation to local rotation relative to the parent's rotation.

        :param parent_rotation: mathutils.Quaternion representing the parent's rotation.
        :param child_rotation: mathutils.Quaternion representing the child's world rotation.
        :return: mathutils.Quaternion representing the child's local rotation.
        """

        # Calculate the local rotation
        local_rotation =  parent_rotation.conjugated() @ child_rotation

        return local_rotation
    
    @staticmethod
    def get_world_rotation(parent_rotation: Quaternion, child_local_rotation: Quaternion) -> Quaternion:
        """
        Convert the child's local rotation to world rotation relative to the parent's rotation.

        :param parent_rotation: mathutils.Quaternion representing the parent's rotation.
        :param child_local_rotation: mathutils.Quaternion representing the child's local rotation.
        :return: mathutils.Quaternion representing the child's world rotation.
        """
        # Calculate the world rotation
        world_rotation = parent_rotation @ child_local_rotation
        return world_rotation
    
    @staticmethod
    def get_pose_bone_location_at_frame(action: bpy.types.Action, bone_name: str, frame: float) -> mathutils.Vector:
        """
        Get the location of a pose bone at a specific frame.

        :param action: bpy.types.Action containing the animation data.
        :param bone_name: str name of the bone.
        :param frame: int frame number.
        :return: mathutils.Vector representing the location of the bone at the specified frame.
        """
        location_collection = [0.0, 0.0, 0.0]
        for i in range(3):
            data_path = f'pose.bones["{bone_name}"].location'
            fcurve = action.fcurves.find(data_path, index = i)
            if fcurve:
                location_collection[i] = fcurve.evaluate(frame)
        
        return Vector((location_collection[0], location_collection[1], location_collection[2]))
    
    @staticmethod
    def get_pose_bone_rotation_at_frame(action: bpy.types.Action, bone_name: str, frame: float) -> mathutils.Quaternion:
        """
        Get the rotation of a pose bone at a specific frame.

        :param action: bpy.types.Action containing the animation data.
        :param bone_name: str name of the bone.
        :param frame: int frame number.
        :return: mathutils.Quaternion representing the rotation of the bone at the specified frame.
        """
        rotation_collection = [0.0, 0.0, 0.0, 0.0]
        for i in range(4):
            data_path = f'pose.bones["{bone_name}"].rotation_quaternion'
            fcurve = action.fcurves.find(data_path, index = i)
            if fcurve:
                rotation_collection[i] = fcurve.evaluate(frame)
        
        return Quaternion((rotation_collection[0], rotation_collection[1], rotation_collection[2], rotation_collection[3]))
    
    @staticmethod
    def convert_position_unity_to_blender(pos_x, pos_y, pos_z, z_minus_is_forward) -> Vector:
        if z_minus_is_forward == True:
            return ImportUtils.__convert_position_unity_to_blender_z_minus_forward(pos_x, pos_y, pos_z)
        else:
            return ImportUtils.__convert_position_unity_to_blender_z_plus_forward(pos_x, pos_y, pos_z)
    @staticmethod
    def convert_position_unity_to_blender_vector(position: Vector, z_minus_is_forward) -> Vector:
        return ImportUtils.convert_position_unity_to_blender(position.x, position.y, position.z, z_minus_is_forward)
    @staticmethod
    def __convert_position_unity_to_blender_z_plus_forward(pos_x, pos_y, pos_z) -> Vector:
        return Vector((pos_x, pos_z, pos_y))
    @staticmethod
    def __convert_position_unity_to_blender_z_minus_forward(pos_x, pos_y, pos_z) -> Vector:
        return Vector((-pos_x, -pos_z, pos_y))
    

    @staticmethod      
    def convert_quaternion_unity_to_blender(quat_x, quat_y, quat_z, quat_w, z_minus_is_forward) -> Quaternion:
        if z_minus_is_forward == True:
            return ImportUtils.__convert_quaternion_unity_to_blender_z_minus_forward(quat_x, quat_y, quat_z, quat_w)
        else:
            return ImportUtils.__convert_quaternion_unity_to_blender_z_plus_forward(quat_x, quat_y, quat_z, quat_w)
    @staticmethod      
    def __convert_quaternion_unity_to_blender_z_plus_forward(quat_x, quat_y, quat_z, quat_w) -> Quaternion:
        return Quaternion((quat_w, -quat_x, -quat_z, -quat_y))
    @staticmethod      
    def __convert_quaternion_unity_to_blender_z_minus_forward(quat_x, quat_y, quat_z, quat_w) -> Quaternion:
        return Quaternion((-quat_w, -quat_x, -quat_z, quat_y))

    
    @staticmethod
    def convert_position_blender_to_unity(pos_x, pos_y, pos_z, z_minus_is_forward) -> Vector:
        if z_minus_is_forward == True:
            return ImportUtils.__convert_position_blender_to_unity_z_minus_forward(pos_x, pos_y, pos_z)
        else:
            return ImportUtils.__convert_position_blender_to_unity_z_plus_forward(pos_x, pos_y, pos_z)
    @staticmethod
    def convert_position_blender_to_unity_vector(position: Vector, z_minus_is_forward) -> Vector:
        return ImportUtils.convert_position_blender_to_unity(position.x, position.y, position.z, z_minus_is_forward)
    @staticmethod
    def __convert_position_blender_to_unity_z_plus_forward(pos_x, pos_y, pos_z) -> Vector:
        return Vector((pos_x, pos_z, pos_y))
    @staticmethod
    def __convert_position_blender_to_unity_z_minus_forward(pos_x, pos_y, pos_z) -> Vector:
        return Vector((-pos_x, pos_z, -pos_y))
    

    @staticmethod      
    def convert_quaternion_blender_to_unity(quat_x, quat_y, quat_z, quat_w, z_minus_is_forward) -> tuple[float, float, float, float]:
        if z_minus_is_forward == True:
            return ImportUtils.__convert_quaternion_blender_to_unity_z_minus_forward(quat_x, quat_y, quat_z, quat_w)
        else:
            return ImportUtils.__convert_quaternion_blender_to_unity_z_plus_forward(quat_x, quat_y, quat_z, quat_w)
    @staticmethod      
    def convert_quaternion_blender_to_unity_quaternion(rotation: Quaternion, z_minus_is_forward) -> tuple[float, float, float, float]:
        return ImportUtils.convert_quaternion_blender_to_unity(rotation.x, rotation.y, rotation.z, rotation.w, z_minus_is_forward)
    @staticmethod      
    def __convert_quaternion_blender_to_unity_z_plus_forward(quat_x, quat_y, quat_z, quat_w) -> tuple[float, float, float, float]:
        return (-quat_x, -quat_z, -quat_y, quat_w)
    @staticmethod      
    def __convert_quaternion_blender_to_unity_z_minus_forward(quat_x, quat_y, quat_z, quat_w) -> tuple[float, float, float, float]:
        return (-quat_x, quat_z, -quat_y, -quat_w)
    
    
    @staticmethod
    def decompose_blender_matrix_position_scale_rotation(matrix):
                # Extract position
                position = matrix.to_translation()

                # Extract scale
                scale = matrix.to_scale()

                # Extract rotation
                rotation = matrix.to_quaternion()  # Note: Returns a mathutils.Quaternion in order [w, x, y, z]

                return position, scale, rotation
    
    @staticmethod
    def decompose_blender_matrix_position_rotation(matrix) -> tuple[Vector, Quaternion]:
                # Extract position
                position = matrix.to_translation()

                # Extract rotation
                rotation = matrix.to_quaternion()  # Note: Returns a mathutils.Quaternion in order [w, x, y, z]

                return position, rotation
    
    @staticmethod
    def is_armature_valid(self: Operator, armature: bpy.types.Armature, check_for_exportation: bool):
        bones: list[bpy.types.Bone] = armature.data.bones
        if len(bones) == 0:
            self.report({"ERROR"}, f"Armature [{armature.name}] has no bones in it.")
            return False
        if len(bones) > 256:
            self.report({"ERROR"}, f"Armature [{armature.name}] has more than 256 bones.")
            return False
        
        existing_bone_names: list[str] = []
        has_Head_bone = False
        for bone in bones:
            if bone.name not in existing_bone_names:
                existing_bone_names.append(bone.name)
                if bone.name == "Head":
                    has_Head_bone = True
            else:
                self.report({"ERROR"}, f"Armature [{armature.name}] has bones with equal names.")
                return False
            
            # Check for invalid bone_id values
            bone_id = bone.get("bone_id")
            if bone_id is not None:
                if bone_id < 0 or bone_id >= len(bones):
                    self.report({"ERROR"}, f"Bone [{bone.name}] of armature [{armature.name}] has an invalid(id<0 or id>=len(bones)) bone_id [{bone_id}].")
                    return False
            else:
                self.report({"ERROR"}, f"Bone [{bone.name}] of armature [{armature.name}] is missing the bone_id property.")
                return False
            
        if check_for_exportation:
            if not has_Head_bone:
                self.report({"ERROR"}, f"Armature [{armature.name}] is missing a bone named 'Head'(case considered), which is necessary for exportation.")
                return False
            
            base_bone = next((bone for bone in bones if bone.name.casefold() in {"base", "root"}), None)
            if not base_bone:
                self.report({"ERROR"}, f"Armature [{armature.name}] is missing a bone named 'Base'(case not considered) or 'Root'(case not considered), which is necessary for exportation.")
                return False
            if base_bone.get("bone_id") != 0:
                self.report({"ERROR"}, f"Armature [{armature.name}] has a 'Base' or 'Root' bone, but its bone_id is not 0.")
                return False
            if base_bone.parent is not None:
                self.report({"ERROR"}, f"Bone [{base_bone}] of armature [{armature.name}] is marked as the root bone but has a parent, which should not happen.")
                return False

        return True
    @staticmethod
    def rebuild_armature_bone_ids(self: Operator, armature: bpy.types.Armature, print_debug = False):
        bones: list[bpy.types.Bone] = armature.data.bones
        existing_ids = {bone.get("bone_id") for bone in bones if bone.get("bone_id") is not None}

        # Check for the presence of 'Base' or 'Root' bone and its bone_id
        base_bone = next((bone for bone in bones if bone.name.casefold() in {"base", "root"}), None)
        if not base_bone:
            self.report({"ERROR"}, f"Armature [{armature.name}] is missing a bone named 'Base'(case not considered) or 'Root'(case not considered), which is necessary for exportation.")
            return False
        if base_bone.get("bone_id") != 0:
            self.report({"ERROR"}, f"Armature [{armature.name}] has a 'Base' or 'Root' bone, but its bone_id is not 0.")
            return False

        # Check for invalid bone_id values and reassign if necessary
        next_id: int = 0
        for bone in bones:
            bone_id = bone.get("bone_id")
            if bone_id is None or bone_id < 0 or bone_id >= len(bones):
                while next_id in existing_ids:
                    next_id += 1
                bone["bone_id"] = next_id
                ImportUtils.debug_print(print_debug, f"Bone [{bone.name}] got reassigned the id [{next_id}]")
                existing_ids.add(next_id)
            next_id += 1

        return True
    
    @staticmethod
    def read_xml_file(reportable_self, file_path: str, exception_string: str) -> ET.Element:
        try:
            tree = ET.parse(file_path.casefold())
            root: ET.Element = tree.getroot()
            return root
        except Exception as e:
            # print(f"{exception_string}: {e}")
            reportable_self.report({'ERROR'}, f"{exception_string}: {e}")
    

    @staticmethod
    def debug_print(should_print, debug_string):
        if should_print == True:
            print(debug_string)
            # self.report({'INFO'}, debug_string)

    @staticmethod
    def find_single_xml_files(directory):
        all_files = os.listdir(directory)
        single_xml_files = [file for file in all_files if file.endswith('.xml') and file.count('.') == 1]
        return single_xml_files
    
        
    class NodeOrganizer:
        def __init__(self):
            self.average_y = 0
            self.x_last = 0
        
        def arrange_nodes(self, context: bpy.types.Context, ntree: bpy.types.NodeTree, margin_x: int, margin_y: int, fast = False):
            area = context.area
            old_area_ui_type = area.ui_type
            
            # Redraw nodes in the node tree
            if fast == False:
                area.ui_type = 'ShaderNodeTree'
                bpy.ops.wm.redraw_timer(type='DRAW_WIN', iterations=1)

            outputnodes = [node for node in ntree.nodes if not node.outputs and any(input.is_linked for input in node.inputs)]
            
            
            if not outputnodes:
                return None
            
            a = [[] for _ in range(1 + len(outputnodes))]
            a[0].extend(outputnodes)
            
            level = 0
            while a[level]:
                a.append([])
                for node in a[level]:
                    inputlist = [i for i in node.inputs if i.is_linked]
                    if inputlist:
                        for input in inputlist:
                            from_nodes = [nlinks.from_node for nlinks in input.links]
                            a[level + 1].extend(from_nodes)
                level += 1
            
            a = [list(OrderedDict.fromkeys(lst)) for lst in a[:level]]
            top = level-1

            for row1 in range(top, 0, -1):
                for col1 in list(a[row1]):  # Convert to list to avoid modification during iteration
                    for row2 in range(row1 - 1, -1, -1):
                        if col1 in a[row2]:
                            a[row2].remove(col1)
                            break

            levelmax = level
            self.x_last = 0
            
            for level in range(levelmax):
                self.average_y = 0
                nodes = list(a[level])
                self.nodes_arrange(nodes, level, margin_x, margin_y)
            area.ui_type = old_area_ui_type
            return None

        def nodes_arrange(self, nodelist: list[bpy.types.Node], level, margin_x, margin_y,):
            parents = [node.parent for node in nodelist]
            for node in nodelist:
                node.parent = None

            widthmax = max([node.dimensions.x for node in nodelist])

            #widthmax = max(node.dimensions.x for node in nodelist)

            xpos = self.x_last - (widthmax + margin_x) if level != 0 else 0
            self.x_last = xpos
            ypos = 0

            for node in nodelist:
                node_y_dimension = node.dimensions.y
                hidey = (node_y_dimension / 2) - 8 if node.hide else 0

                node.location.y = ypos - hidey
                ypos = ypos-(margin_y + node_y_dimension)  # Correct y position calculation
                node.location.x = xpos

            ypos += margin_y
            center = ypos / 2
            self.average_y = center - self.average_y
            
            for i, node in enumerate(nodelist):
                node.parent = parents[i]
        """
        @staticmethod
        def arrange_shader_nodes():
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.type = 'NODE_EDITOR'
                    area.spaces.active.tree_type = 'ShaderNodeTree'
                    
                    for obj in bpy.data.objects:
                        bpy.context.view_layer.objects.active = obj
                        old_mat = obj.active_material
                        for ms in obj.material_slots:
                            mat = ms.material
                            obj.active_material = mat
                            bpy.ops.wm.redraw_timer(type='DRAW_WIN', iterations=1)
                            NodeOrganizer.arrange_nodes(mat.node_tree)
                        obj.active_material = old_mat
                    
                    area.type = 'VIEW_3D'
        """



class ArmatureExportValidator(Operator):
    bl_idname = "cbb.armature_validator_export"
    bl_label = "Validate Armature For Exportation"
    bl_description = "Validates if the currently active armature is valid for exportation."
    bl_options = {'REGISTER'}


    def execute(self, context):
        if context.active_object is not None:
            if context.active_object.type == "ARMATURE":
                is_valid = ImportUtils.is_armature_valid(self, context.active_object, True)
                self.report({'INFO'}, f"[{context.active_object.name}] validation for export result: {is_valid}")
                return {'FINISHED'}
            else:
                self.report({'INFO'}, f"[{context.active_object.name}] is not an armature, there is no validation to be made.")
        
        return {'CANCELLED'}
        
class ArmatureImportValidator(Operator):
    bl_idname = "cbb.armature_validator_import"
    bl_label = "Validate Armature For Import"
    bl_description = "Validates if the currently active armature is valid for at least importation."
    bl_options = {'REGISTER'}


    def execute(self, context):
        if context.active_object is not None:
            if context.active_object.type == "ARMATURE":
                is_valid = ImportUtils.is_armature_valid(self, context.active_object, False)
                self.report({'INFO'}, f"[{context.active_object.name}] validation for import result: {is_valid}")
                return {'FINISHED'}
            else:
                self.report({'INFO'}, f"[{context.active_object.name}] is not an armature, there is no validation to be made.")
        return {'CANCELLED'}
        
class ArmatureBoneIDRebuilder(Operator):
    bl_idname = "cbb.armature_bone_id_rebuild"
    bl_label = "Rebuild Bone IDs for Armature"
    bl_description = "As long as the armature has a root or base bone with a bone_id of 0, this function rebuilds all invalid bone_ids."
    bl_options = {'REGISTER', "UNDO"}


    def execute(self, context):
        if context.active_object is not None:
            if context.active_object.type == "ARMATURE":
                rebuild_result = ImportUtils.rebuild_armature_bone_ids(self, context.active_object)
                self.report({'INFO'}, f"[{context.active_object.name}] bone_id rebuilding result: {rebuild_result}")
                return {'FINISHED'}
            else:
                self.report({'INFO'}, f"[{context.active_object.name}] is not an armature, there is no validation to be made.")
        return {'CANCELLED'}

class OBJECT_MT_custom_menu(bpy.types.Menu):
    bl_label = "CBB Tools"
    bl_idname = "OBJECT_MT_custom_menu"

    def draw(self, context):
        layout = self.layout
        layout.operator("cbb.armature_validator_export")
        layout.operator("cbb.armature_validator_import")
        layout.operator("cbb.armature_bone_id_rebuild")

def draw_custom_menu(self, context):
    layout = self.layout
    layout.separator()
    layout.menu(OBJECT_MT_custom_menu.bl_idname)

def register():
    global already_registered
    if already_registered == False:
        bpy.utils.register_class(OBJECT_MT_custom_menu)
        bpy.utils.register_class(ImportUtils)
        bpy.utils.register_class(ArmatureExportValidator)
        bpy.utils.register_class(ArmatureImportValidator)
        bpy.utils.register_class(ArmatureBoneIDRebuilder)
        bpy.types.VIEW3D_MT_object.append(draw_custom_menu)
        already_registered = True

def unregister():
    global already_registered
    if already_registered == True:
        bpy.utils.unregister_class(ImportUtils)
        bpy.utils.unregister_class(ArmatureExportValidator)
        bpy.utils.unregister_class(ArmatureImportValidator)
        bpy.utils.unregister_class(ArmatureBoneIDRebuilder)
        bpy.utils.unregister_class(OBJECT_MT_custom_menu)
        bpy.types.VIEW3D_MT_object.remove(draw_custom_menu)
        already_registered = False

if __name__ == "__main__":
    register()
