from __future__ import annotations
import encodings.ascii
import encodings.utf_16
import codecs
import bpy
import struct
import ntpath
import traceback
import mathutils
from bpy_extras.io_utils import ImportHelper
from bpy.types import Operator, Context, Event
from bpy.props import StringProperty
from mathutils import Vector, Quaternion, Matrix, Euler
import math
import xml.etree.ElementTree as ET
import os
from collections import OrderedDict
from bpy.props import CollectionProperty, StringProperty, BoolProperty
from enum import Enum
import io
from typing import NamedTuple, Optional
from pathlib import Path

already_registered = False
class CoordsSys(Enum):
        Blender = 0
        Unity = 1
        _3DSMax = 2
        _3DSMaxInverseY = 3
        
class Utils(Operator):
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
        local_rotation =  Utils.safe_quaternion_multiply(parent_rotation.conjugated(), child_rotation)

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
        world_rotation = Utils.safe_quaternion_multiply(parent_rotation, child_local_rotation)
        return world_rotation
    
    @staticmethod
    def get_pose_bone_location_at_frame(armature: bpy.types.Object, bone_name: str, frame) -> mathutils.Vector:
        """
        Get the location of a pose bone at a specific frame. This version sets the frame for each call.

        :param armature: bpy.types.Object target armature.
        :param bone_name: str name of the bone.
        :param frame: int frame number.
        :return: mathutils.Vector representing the location of the bone at the specified frame.
        """
        bpy.context.scene.frame_set(int(frame))
        pose_bone = armature.pose.bones.get(bone_name)
        if pose_bone:
            return pose_bone.location
        else:
            return None
            
    @staticmethod
    def get_pose_bone_location_at_frame_fast(armature: bpy.types.Object, bone_name: str) -> mathutils.Vector:
        """
        Get the location of a pose bone at a specific frame. This version skips setting the frame.

        :param action: bpy.types.Action containing the animation data.
        :param bone_name: str name of the bone.
        :return: mathutils.Vector representing the location of the bone.
        """
        pose_bone = armature.pose.bones.get(bone_name)
        if pose_bone:
            return pose_bone.location
        else:
            return None
    
    @staticmethod
    def get_pose_bone_rotation_at_frame(armature: bpy.types.Object, bone_name: str, frame) -> mathutils.Quaternion:
        """
        Get the rotation of a pose bone at a specific frame. This version sets the frame for each call.

        :param armature: bpy.types.Object target armature.
        :param bone_name: str name of the bone.
        :param frame: int frame number.
        :return: mathutils.Quaternion representing the rotation of the bone at the specified frame.
        """
        bpy.context.scene.frame_set(int(frame))
        pose_bone = armature.pose.bones.get(bone_name)
        if pose_bone:
            return pose_bone.rotation_quaternion
        else:
            return None
    
    @staticmethod
    def get_pose_bone_rotation_at_frame_fast(armature: bpy.types.Object, bone_name: str) -> mathutils.Quaternion:
        """
        Get the rotation of a pose bone at a specific frame. This version skips setting the frame.

        :param armature: bpy.types.Object target armature.
        :param bone_name: str name of the bone.
        :return: mathutils.Quaternion representing the rotation of the bone at the specified frame.
        """
        pose_bone = armature.pose.bones.get(bone_name)
        if pose_bone:
            return pose_bone.rotation_quaternion
        else:
            return None
        
    @staticmethod
    def get_pose_bone_location_at_frame_fcurves(action: bpy.types.Action, bone_name: str, frame: float) -> mathutils.Vector:
        location_collection = [0.0, 0.0, 0.0]
        for i in range(3):
            data_path = f'pose.bones["{bone_name}"].location'
            fcurve = action.fcurves.find(data_path, index = i)
            if fcurve:
                location_collection[i] = fcurve.evaluate(frame)

        return Vector((location_collection[0], location_collection[1], location_collection[2]))
    
    @staticmethod
    def get_pose_bone_rotation_at_frame_fcurves(action: bpy.types.Action, bone_name: str, frame: float) -> mathutils.Quaternion:
        rotation_collection = [1.0, 0.0, 0.0, 0.0]
        for i in range(4):
            data_path = f'pose.bones["{bone_name}"].rotation_quaternion'
            fcurve = action.fcurves.find(data_path, index = i)
            if fcurve:
                rotation_collection[i] = fcurve.evaluate(frame)

        return Quaternion((rotation_collection[0], rotation_collection[1], rotation_collection[2], rotation_collection[3]))
    
    @staticmethod
    def get_pose_bone_scale_at_frame_fcurves(action: bpy.types.Action, bone_name: str, frame: float) -> mathutils.Vector:
        scale_collection = [1.0, 1.0, 1.0]
        for i in range(3):
            data_path = f'pose.bones["{bone_name}"].scale'
            fcurve = action.fcurves.find(data_path, index = i)
            if fcurve:
                scale_collection[i] = fcurve.evaluate(frame)

        return Vector((scale_collection[0], scale_collection[1], scale_collection[2]))
    
    @staticmethod
    def get_object_location_at_frame_fcurves(action: bpy.types.Action, object_name: str, frame: float) -> mathutils.Vector:
        location_collection = [0.0, 0.0, 0.0]
        for i in range(3):
            data_path = f'objects["{object_name}"].location'
            fcurve = action.fcurves.find(data_path, index = i)
            if fcurve:
                location_collection[i] = fcurve.evaluate(frame)

        return Vector((location_collection[0], location_collection[1], location_collection[2]))
    
    @staticmethod
    def get_object_rotation_at_frame_fcurves(action: bpy.types.Action, object_name: str, frame: float) -> mathutils.Quaternion:
        # Default rotation as identity quaternion
        rotation_collection = [1.0, 0.0, 0.0, 0.0]

        # Determine the rotation mode of the object
        obj = bpy.data.objects.get(object_name)
        if obj is None:
            raise ValueError(f"Object '{object_name}' not found")

        rotation_mode = obj.rotation_mode

        if rotation_mode == 'QUATERNION':
            # Get rotation as quaternion
            for i in range(4):
                data_path = f'objects["{object_name}"].rotation_quaternion'
                fcurve = action.fcurves.find(data_path, index=i)
                if fcurve:
                    rotation_collection[i] = fcurve.evaluate(frame)
            return Quaternion(rotation_collection)

        elif rotation_mode == 'AXIS_ANGLE':
            # Handle rotation as axis-angle
            axis = [0.0, 0.0, 0.0]
            angle = 0.0
            for i in range(3):
                data_path = f'objects["{object_name}"].rotation_axis_angle'
                fcurve = action.fcurves.find(data_path, index=i + 1)  # Indices 1 to 3 for axis
                if fcurve:
                    axis[i] = fcurve.evaluate(frame)
            # Index 0 is the angle
            fcurve = action.fcurves.find(data_path, index=0)
            if fcurve:
                angle = fcurve.evaluate(frame)
            return Quaternion(axis, angle)

        elif rotation_mode in {'XYZ', 'XZY', 'YZX', 'YXZ', 'ZXY', 'ZYX'}:
            # Handle rotation as Euler angles
            euler_angles = [0.0, 0.0, 0.0]
            for i in range(3):
                data_path = f'objects["{object_name}"].rotation_euler'
                fcurve = action.fcurves.find(data_path, index=i)
                if fcurve:
                    euler_angles[i] = fcurve.evaluate(frame)
            euler = Euler(euler_angles, rotation_mode)
            return euler.to_quaternion()

        else:
            raise ValueError(f"Unsupported rotation mode: {rotation_mode}")
    
    @staticmethod
    def get_object_scale_at_frame_fcurves(action: bpy.types.Action, object_name: str, frame: float) -> mathutils.Vector:
        scale_collection = [1.0, 1.0, 1.0]
        for i in range(3):
            data_path = f'objects["{object_name}"].scale'
            fcurve = action.fcurves.find(data_path, index = i)
            if fcurve:
                scale_collection[i] = fcurve.evaluate(frame)

        return Vector((scale_collection[0], scale_collection[1], scale_collection[2]))
    # -----------------------------------UNITY--------------------------------------------------------------
    
    @staticmethod
    def __convert_vector3f_unity_to_blender(pos_x, pos_y, pos_z, y_minus_is_forward) -> Vector:
        if y_minus_is_forward == True:
            return Vector((-pos_x, -pos_z, pos_y))
        else:
            return Vector((pos_x, pos_z, pos_y))
    
    @staticmethod
    def __convert_quaternion_unity_to_blender(quat_x, quat_y, quat_z, quat_w, y_minus_is_forward) -> Quaternion:
        if y_minus_is_forward == True:
            return Quaternion((-quat_w, -quat_x, -quat_z, quat_y))
        else:
            return Quaternion((quat_w, -quat_x, -quat_z, -quat_y))


    @staticmethod
    def __convert_vector3f_blender_to_unity(pos_x, pos_y, pos_z, y_minus_is_forward) -> Vector:
        if y_minus_is_forward == True:
            return Vector((-pos_x, pos_z, -pos_y))
        else:
            return Vector((pos_x, pos_z, pos_y))
    
    @staticmethod
    def __convert_quaternion_blender_to_unity(quat_x, quat_y, quat_z, quat_w, y_minus_is_forward) -> Quaternion:
        if y_minus_is_forward == True:
            return Quaternion((-quat_w, -quat_x, quat_z, -quat_y))
        else:
            return Quaternion((quat_w, -quat_x, -quat_z, -quat_y))
    
    # -----------------------------------3DSMAX--------------------------------------------------------------
    
    @staticmethod
    def __convert_vector3f_3dsmax_to_blender(pos_x, pos_y, pos_z, y_minus_is_forward) -> Vector:
        if y_minus_is_forward == True:
            return Vector((pos_x, pos_y, pos_z))
        else:
            return Vector((-pos_x, -pos_y, pos_z))

    @staticmethod
    def __convert_quaternion_3dsmax_to_blender(quat_x, quat_y, quat_z, quat_w, y_minus_is_forward) -> Quaternion:
        if y_minus_is_forward == True:
            return Quaternion((quat_w, quat_x, quat_y, quat_z))
        else:
            return Quaternion((quat_w, -quat_x, -quat_y, quat_z))

    
    @staticmethod
    def __convert_vector3f_blender_to_3dsmax(pos_x, pos_y, pos_z, y_minus_is_forward) -> Vector:
        if y_minus_is_forward == True:
            return Vector((pos_x, pos_y, pos_z))
        else:
            return Vector((-pos_x, -pos_y, pos_z))
    
    @staticmethod
    def __convert_quaternion_blender_to_3dsmax(quat_x, quat_y, quat_z, quat_w, y_minus_is_forward) -> Quaternion:
        if y_minus_is_forward == True:
            return Quaternion((quat_w, quat_x, quat_y, quat_z))
        else:
            return Quaternion((quat_w, -quat_x, -quat_y, quat_z))
    
    # -----------------------------------3DSMAX INVERSE Y--------------------------------------------------------------
     
    @staticmethod
    def __convert_vector3f_3dsmax_inverse_y_to_blender(pos_x, pos_y, pos_z, y_minus_is_forward) -> Vector:
        if y_minus_is_forward == True:
            return Vector((-pos_x, -pos_y, pos_z))
        else:
            return Vector((pos_x, pos_y, pos_z))

    @staticmethod
    def __convert_quaternion_3dsmax_inverse_y_to_blender(quat_x, quat_y, quat_z, quat_w, y_minus_is_forward) -> Quaternion:
        if y_minus_is_forward == True:
            return Quaternion((quat_w, -quat_x, -quat_y, quat_z))
            
        else:
            return Quaternion((quat_w, quat_x, quat_y, quat_z))

    
    @staticmethod
    def __convert_vector3f_blender_to_3dsmax_inverse_y(pos_x, pos_y, pos_z, y_minus_is_forward) -> Vector:
        if y_minus_is_forward == True:
            return Vector((-pos_x, -pos_y, pos_z))
        else:
            return Vector((pos_x, pos_y, pos_z))
    
    @staticmethod
    def __convert_quaternion_blender_to_3dsmax_inverse_y(quat_x, quat_y, quat_z, quat_w, y_minus_is_forward) -> Quaternion:
        if y_minus_is_forward == True:
            return Quaternion((quat_w, -quat_x, -quat_y, quat_z))
        else:
            return Quaternion((quat_w, quat_x, quat_y, quat_z))
    
    
    @staticmethod
    def decompose_matrix_position_rotation_scale(matrix: Matrix) -> tuple[Vector, Quaternion, Vector]:
        # Extract position
        position = matrix.to_translation()

        # Extract rotation
        rotation = matrix.to_quaternion()
        
        # Extract scale
        scale = matrix.to_scale()
        return position, rotation, scale
    
    @staticmethod
    def safe_quaternion_multiply(q1: Quaternion, q2: Quaternion):
        dot = q1.dot(q2)
        if dot < 0.0:
            q2 = Quaternion((-q2.w, -q2.x, -q2.y, -q2.z))
        return q1 @ q2
    
    @staticmethod
    def decompose_blender_matrix_position_rotation(matrix: Matrix) -> tuple[Vector, Quaternion]:
        # Extract position
        position = matrix.to_translation()

        # Extract rotation
        rotation = matrix.to_quaternion()
        return position, rotation
    
    @staticmethod
    def compose_matrix_from_position_rotation_scale(position: Vector, rotation: Quaternion, scale: Vector):
        return Matrix.Translation(position) @ rotation.to_matrix().to_4x4() @ Matrix.Diagonal(scale).to_4x4()
    
    vector3f_conversions = {
            (CoordsSys.Unity, CoordsSys.Blender): __convert_vector3f_unity_to_blender,
            (CoordsSys.Blender, CoordsSys.Unity): __convert_vector3f_blender_to_unity,
            (CoordsSys._3DSMax, CoordsSys.Blender): __convert_vector3f_3dsmax_to_blender,
            (CoordsSys.Blender, CoordsSys._3DSMax): __convert_vector3f_blender_to_3dsmax,
            (CoordsSys._3DSMaxInverseY, CoordsSys.Blender): __convert_vector3f_3dsmax_inverse_y_to_blender,
            (CoordsSys.Blender, CoordsSys._3DSMaxInverseY): __convert_vector3f_blender_to_3dsmax_inverse_y,
        }
    
    @staticmethod
    def convert_vector3f(source: CoordsSys, target: CoordsSys, position: Vector,  y_minus_is_forward: bool) -> Vector:
        conversion_function = Utils.vector3f_conversions.get((source, target))
        if conversion_function is None:
            raise ValueError(f"Unsupported conversion from {source} to {target}")

        return conversion_function(position.x, position.y, position.z, y_minus_is_forward)

    rotation_conversions = {
            (CoordsSys.Unity, CoordsSys.Blender): __convert_quaternion_unity_to_blender,
            (CoordsSys.Blender, CoordsSys.Unity): __convert_quaternion_blender_to_unity,
            (CoordsSys._3DSMax, CoordsSys.Blender): __convert_quaternion_3dsmax_to_blender,
            (CoordsSys.Blender, CoordsSys._3DSMax): __convert_quaternion_blender_to_3dsmax,
            (CoordsSys._3DSMaxInverseY, CoordsSys.Blender): __convert_quaternion_3dsmax_inverse_y_to_blender,
            (CoordsSys.Blender, CoordsSys._3DSMaxInverseY): __convert_quaternion_blender_to_3dsmax_inverse_y,
        }
    
    @staticmethod
    def convert_quaternion(source: CoordsSys, target: CoordsSys, rotation: Quaternion, y_minus_is_forward: bool = False) -> Quaternion:
        conversion_function = Utils.rotation_conversions.get((source, target))
        if conversion_function is None:
            raise ValueError(f"Unsupported conversion from {source} to {target}")

        return conversion_function(rotation.x, rotation.y, rotation.z, rotation.w, y_minus_is_forward)
    
    class CoordinatesConverter:
        """
        Class used to make conversion calls more direct and less verbose.
        """
        def __init__(self, source: CoordsSys, target: CoordsSys, y_minus_is_forward: bool = False):
            self.source = source
            self.target = target
            self.y_minus_is_forward = y_minus_is_forward

        def convert_vector3f(self, position: Vector) -> Vector:
            return Utils.convert_vector3f(self.source, self.target, position, self.y_minus_is_forward)

        def convert_quaternion(self, quaternion: Quaternion) -> Quaternion:
            return Utils.convert_quaternion(self.source, self.target, quaternion, self.y_minus_is_forward)
        
        def convert_matrix(self, matrix: Matrix) -> Matrix:
            translation, rotation, scale = Utils.decompose_matrix_position_rotation_scale(matrix)
        
            new_translation = Utils.convert_vector3f(self.source, self.target, translation, self.y_minus_is_forward)
            
            new_rotation = Utils.convert_quaternion(self.source, self.target, rotation, self.y_minus_is_forward)
            
            return Utils.compose_matrix_from_position_rotation_scale(new_translation, new_rotation, scale)
        
    class Serializer:
        """
        Class used to make file read and write calls more direct and less verbose. Some types are converted to Blender ready already, such as Matrix, Vector and Quaternion. Data can be converted by coordinates too if a coordinates_converter is given.
        Calling converted functions without specifying a coordinates_converter will cause an error.
        """
        class Endianness(Enum):
            Little = 0
            Big = 1
            
        class Quaternion_Order(Enum):
            XYZW = 0
            WXYZ = 1
            
        class Matrix_Order(Enum):
            RowMajor = 0
            ColumnMajor = 1
        
        def __init__(self, opened_file: io.BufferedReader, endianness: Endianness, quaternion_order: Quaternion_Order, matrix_order: Matrix_Order, coordinates_converter: Utils.CoordinatesConverter = None):
            self.file = opened_file
            if endianness == Utils.Serializer.Endianness.Little:
                self.endianness = "<"
            else:
                self.endianness = ">"
            self.quaternion_order = quaternion_order
            self.matrix_order = matrix_order
            self.co_conv = coordinates_converter

        def read_vector3f(self) -> Vector:
            return Vector(struct.unpack(f'{self.endianness}3f', self.file.read(12)))
        
        def read_converted_vector3f(self) -> Vector:
            return self.co_conv.convert_vector3f(self.read_vector3f())
        
        def write_vector3f(self, vector3f: Vector):
            self.file.write(struct.pack(f"{self.endianness}3f", *vector3f))
        
        def write_converted_vector3f(self, vector3f: Vector):
            self.write_vector3f(self.co_conv.convert_vector3f(vector3f))

        def read_quaternion(self) -> Quaternion:
            r_quaternion = struct.unpack(f'{self.endianness}4f', self.file.read(16))
            if self.quaternion_order == Utils.Serializer.Quaternion_Order.XYZW:
                return Quaternion((r_quaternion[3], r_quaternion[0], r_quaternion[1], r_quaternion[2]))
            return None
        
        def read_converted_quaternion(self) -> Quaternion:
            return self.co_conv.convert_quaternion(self.read_quaternion())
        
        def write_quaternion(self, quaternion: Quaternion):
            if self.quaternion_order == Utils.Serializer.Quaternion_Order.XYZW:
                quaternion = (quaternion.x, quaternion.y, quaternion.z, quaternion.w)
            self.file.write(struct.pack(f"{self.endianness}4f", *quaternion))
        
        def write_converted_quaternion(self, quaternion: Quaternion):
            self.write_quaternion(self.co_conv.convert_quaternion(quaternion))
        
        def read_matrix(self) -> Matrix:
            matrix_data = struct.unpack('<16f', self.file.read(64))
            if self.matrix_order == Utils.Serializer.Matrix_Order.ColumnMajor:
                matrix_data = (
                    (matrix_data[0], matrix_data[4], matrix_data[8], matrix_data[12]),
                    (matrix_data[1], matrix_data[5], matrix_data[9], matrix_data[13]),
                    (matrix_data[2], matrix_data[6], matrix_data[10], matrix_data[14]),
                    (matrix_data[3], matrix_data[7], matrix_data[11], matrix_data[15])
                )
            return Matrix(matrix_data)
        
        def read_converted_matrix(self) -> Matrix:
            return self.co_conv.convert_matrix(self.read_matrix())
        
        def write_matrix(self, matrix: Matrix) -> Matrix:
            if self.matrix_order == Utils.Serializer.Matrix_Order.ColumnMajor:
                matrix = (
                    matrix[0][0], matrix[1][0], matrix[2][0], matrix[3][0],
                    matrix[0][1], matrix[1][1], matrix[2][1], matrix[3][1],
                    matrix[0][2], matrix[1][2], matrix[2][2], matrix[3][2],
                    matrix[0][3], matrix[1][3], matrix[2][3], matrix[3][3]
                )
            self.file.write(struct.pack(f"{self.endianness}16f", *matrix))
        
        def write_converted_matrix(self, matrix: Matrix) -> Matrix:
            self.write_matrix(self.co_conv.convert_matrix(matrix))
        
        def read_ubyte(self) -> int:
            return struct.unpack(f'{self.endianness}B', self.file.read(1))[0]
        
        def write_ubyte(self, ubyte: int):
            self.file.write(struct.pack(f"{self.endianness}B", ubyte))
        
        def read_byte(self) -> int:
            return struct.unpack(f'{self.endianness}b', self.file.read(1))[0]
        
        def write_byte(self, byte: int):
            self.file.write(struct.pack(f"{self.endianness}b", byte))
            
        def read_ubyte(self) -> int:
            return struct.unpack(f'{self.endianness}B', self.file.read(1))[0]
        
        def write_ubyte(self, byte: int):
            self.file.write(struct.pack(f"{self.endianness}B", byte))
        
        def read_ushort(self) -> int:
            return struct.unpack(f'{self.endianness}H', self.file.read(2))[0]
        
        def write_ushort(self, ushort: int):
            self.file.write(struct.pack(f"{self.endianness}H", ushort))
        
        def read_short(self) -> int:
            return struct.unpack(f'{self.endianness}h', self.file.read(2))[0]
        
        def write_short(self, short: int):
            self.file.write(struct.pack(f"{self.endianness}h", short))
    
        def read_uint(self) -> int:
            return struct.unpack(f'{self.endianness}I', self.file.read(4))[0]
        
        def write_uint(self, uint: int):
            self.file.write(struct.pack(f"{self.endianness}I", uint))
        
        def read_int(self) -> int:
            return struct.unpack(f'{self.endianness}i', self.file.read(4))[0]
        
        def write_int(self, int: int):
            self.file.write(struct.pack(f"{self.endianness}i", int))
        
        def read_float(self) -> float:
            return struct.unpack(f'{self.endianness}f', self.file.read(4))[0]
        
        def write_float(self, float: float):
            self.file.write(struct.pack(f"{self.endianness}f", float))
        
        def read_bool(self) -> bool:
            return struct.unpack(f'{self.endianness}?', self.file.read(1))[0]
        
        def write_bool(self, bool: bool):
            self.file.write(struct.pack(f"{self.endianness}?", bool))
        
        def read_fixed_string(self, length_in_bytes: int, encoding: str) -> str:
            result = []
            bytes_read = 0
            decoder = codecs.getincrementaldecoder(encoding)()
            
            while bytes_read < length_in_bytes:
                byte = self.file.read(1)
                bytes_read += 1
                
                try:
                    char = decoder.decode(byte)
                    
                    if char == '\x00':
                        break
                        
                    if char:
                        result.append(char)
                        
                except UnicodeDecodeError:
                    continue
            
            remaining = length_in_bytes - bytes_read
            if remaining > 0:
                self.file.seek(remaining, 1)
                
            return ''.join(result)
        
        def write_fixed_string(self, length_in_bytes: int, encoding: str, string: str):
            self.file.write(string.encode(encoding).ljust(length_in_bytes, b'\x00'))
        
        def read_value(self, format:str, bytes: int):
            """
            Reads a value and returns the first member of the read tuple from struct.unpack.
            """
            return struct.unpack(f'{self.endianness}{format}', self.file.read(bytes))[0]
        
        def read_values(self, format:str, bytes: int):
            """
            Reads values and returns the whole tuple given by struct.unpack.
            """
            return struct.unpack(f'{self.endianness}{format}', self.file.read(bytes))
        
        def write_value(self, format:str, data):
            """
            Writes a single value to the stored file.
            """
            self.file.write(struct.pack(f"{self.endianness}{format}", data))
        
        def write_values(self, format:str, data):
            """
            Writes multiple values to the stored file. Accepts a tuple that is unpacked to struct.pack.
            """
            self.file.write(struct.pack(f"{self.endianness}{format}", *data))
    
    class MessageHandler:
        def __init__(self, debug: bool, report_function: Optional[callable] = None):
            self.debug = debug
            self.report_function = report_function
        
        def debug_print(self, message: str, separator: str= " ", end: str = "\n", flush: bool = False):
            if(self.debug == True):
                print(message, sep=separator, end=end, flush=flush)
        
        def report(self, severity: str, message: str):
            if self.report_function:
                self.report_function({severity}, message)
            else:
                print(f"{severity}: {message}")
        
    
    # -----------------------------------GENERAL--------------------------------------------------------------
    
    def get_immediate_parent_collection(obj):
        for collection in bpy.data.collections:
            if obj.name in collection.objects:
                return collection
        return None
    
    def find_image_texture_for_input(node, target_input_name):
        """Recursively finds the image texture node connected to a specific input of a shader node."""
        if target_input_name not in node.inputs:
            return None
        
        input_socket = node.inputs[target_input_name]
        
        # Traverse the links backwards from the input socket
        if input_socket.is_linked:
            linked_node = input_socket.links[0].from_node
            
            # If the linked node is an Image Texture, return it
            if linked_node.type == 'TEX_IMAGE':
                return linked_node.image
            
            # Otherwise, recursively check this linked node's inputs
            for input_name in linked_node.inputs.keys():
                result = Utils.find_image_texture_for_input(linked_node, input_name)
                if result:
                    return result
        
        return None
    
    @staticmethod
    def rebuild_armature_bone_ids(operator: Operator, armature: bpy.types.Armature, only_deform_bones: bool, debugger: Utils.MessageHandler):
        bones: list[bpy.types.Bone] = [bone for bone in armature.data.bones if bone.use_deform] if only_deform_bones else armature.data.bones
        
        debugger.debug_print(f"Rebuilding bone ids for armature [{armature.name}]. Only deform bones option: {only_deform_bones}")
        debugger.debug_print(f"Amount of detected bones in armature [{armature.name}]: {len(bones)}")
        
        existing_ids = {bone.get("bone_id") for bone in bones if bone.get("bone_id") is not None}
        for id in existing_ids:
            debugger.debug_print(f"Existing ID: {id}")
        
        # Check for the presence of 'Base' or 'Root' bone and its bone_id
        base_bone = next((bone for bone in bones if bone.name.casefold() in {"base", "root"}), None)
        if not base_bone:
            operator.report({"ERROR"}, f"Armature [{armature.name}] is missing a bone named 'Base'(case not considered) or 'Root'(case not considered), which is necessary for exportation.")
            return False
        base_bone["bone_id"] = 0
        
        processed_bone_ids = set()
        existing_ids.add(0)
        next_id: int = 1
        
        for bone in bones:
            bone_id = bone.get("bone_id")
            debugger.debug_print(f"Bone [{bone.name}] bone_id: {bone_id}")
            if bone_id is None or bone_id < 0 or bone_id >= len(bones) or bone_id in processed_bone_ids:
                while next_id in existing_ids or next_id in processed_bone_ids:
                    next_id += 1
                bone["bone_id"] = next_id
                debugger.debug_print(f"Bone [{bone.name}] got reassigned the id [{next_id}]")
                existing_ids.add(next_id)
                processed_bone_ids.add(next_id)
            else:
                processed_bone_ids.add(bone_id)

        return True
    
    @staticmethod
    def read_xml_file(msg_handler: Utils.MessageHandler, file_path: str | Path, exception_string: str) -> ET.Element:
        file_path = str(file_path)
        try:
            tree = ET.parse(str(file_path).casefold())
            root: ET.Element = tree.getroot()
            return root
        except Exception as e:
            msg_handler.report('ERROR', f"{exception_string}: {e}")
        return
    

    @staticmethod
    def debug_print(should_print, debug_string):
        if should_print == True:
            print(debug_string)
            # self.report({'INFO'}, debug_string)

    @staticmethod
    def find_single_xml_files(directory):
        directory = str(directory)
        all_files: list[str] = os.listdir(directory)
        single_xml_files = [file for file in all_files if file.casefold().endswith('.xml') and file.count('.') == 1]
        return single_xml_files
    
    @staticmethod
    def get_actions_from_nla_tracks(obj):
        nla_actions = set()
        if obj.animation_data and obj.animation_data.nla_tracks:
            for track in obj.animation_data.nla_tracks:
                for strip in track.strips:
                    if strip.action:
                        nla_actions.add(strip.action)
        return nla_actions
    
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
        
        def arrange_nodes_no_context(self, ntree: bpy.types.NodeTree, margin_x: int, margin_y: int):

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

    @staticmethod
    def create_driver_multiple(target, var_names, target_objs, target_props, expression):
        # Check that lengths match
        if not (len(var_names) == len(target_objs) == len(target_props)):
            raise ValueError("Lengths of var_name, target_obj, and target_prop must match")
        
        driver = target.driver_add("default_value").driver
        driver.type = 'SCRIPTED'
        for name, obj, prop in zip(var_names, target_objs, target_props):
            var = driver.variables.new()
            var.type = "SINGLE_PROP"
            var.name = name
            var.targets[0].id_type = "MATERIAL"
            var.targets[0].id = obj
            var.targets[0].data_path = f'{prop}'
        driver.expression = expression
        
    @staticmethod
    def create_driver_single(target, var_name, target_obj, target_prop, expression):
        
        driver = target.driver_add("default_value").driver
        driver.type = 'SCRIPTED'
        var = driver.variables.new()
        var.type = "SINGLE_PROP"
        var.name = var_name
        var.targets[0].id_type = "MATERIAL"
        var.targets[0].id = target_obj
        var.targets[0].data_path = f'{target_prop}'
        driver.expression = expression

# -----------------------------------CUSTOM DATA TYPES--------------------------------------------------------------
    
class Vector3Int(NamedTuple):
    x: int
    y: int
    z: int

# ------------------------------------------------------------------------------------------------------------------

def register():
    global already_registered
    if already_registered == False:
        bpy.utils.register_class(Utils)
        already_registered = True

def unregister():
    global already_registered
    if already_registered == True:
        bpy.utils.unregister_class(Utils)
        already_registered = False

if __name__ == "__main__":
    register()
