import bpy
import struct
import ntpath
import traceback
import mathutils
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.types import Context, Event, Operator
from bpy.props import CollectionProperty, StringProperty, BoolProperty
from mathutils import Vector, Quaternion, Matrix
import math
from import_utils import ImportUtils

MIN_BONE_LENGTH = 0.05

class ImportSkeleton(Operator, ImportHelper):
    bl_idname = "cbb.skeleton_import"
    bl_label = "Import Skeleton"
    bl_options = {"PRESET", "UNDO"}

    filename_ext = ".Skeleton"

    filter_glob: StringProperty(default="*.Skeleton", options={"HIDDEN"})

    files: CollectionProperty(
        type=bpy.types.OperatorFileListElement,
        options={"HIDDEN", "SKIP_SAVE"}
    )

    directory: StringProperty(subtype="FILE_PATH")

    debug: BoolProperty(
        name="Debug import",
        description="Enabling this option will make the importer print debug data to console.",
        default=False
    )

    z_minus_is_forward: BoolProperty(
        name="Z- is forward",
        description="Leave this option checked if you wish to work with Z- being the forward direction in Blender. If false, Z+ is considered forward.",
        default=True
    )

    def execute(self, context):
        return self.import_skeletons_from_files(context)

    def import_skeletons_from_files(self: "ImportSkeleton", context: bpy.types.Context):
        for file in self.files:
            if file.name.casefold().endswith(".Skeleton".casefold()):
                filepath = self.directory + file.name

                ImportUtils.debug_print(self.debug, f"Importing skeleton from: {filepath}")

                skeleton_data = SkeletonData.read_skeleton_data(self, filepath)
                try:
                    # Create armature and enter edit mode
                    armature = bpy.data.armatures.new(ntpath.basename(filepath).rsplit(".", 1)[0])
                    armature_obj = bpy.data.objects.new(ntpath.basename(filepath).rsplit(".", 1)[0], armature)
                    bpy.context.collection.objects.link(armature_obj)
                    bpy.context.view_layer.objects.active = armature_obj
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
                    
                    ImportUtils.debug_print(self.debug, f"Created [{len(edit_bones)}] bones in Blender armature.")
                    
                    def _process_bone(bone_id):
                        position = skeleton_data.bone_absolute_positions[bone_id]

                        rotation = skeleton_data.bone_absolute_rotations[bone_id]

                        # Calculate bone matrices
                        if skeleton_data.bone_parent_ids[bone_id] == 0xFFFFFFFF:
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
                    root_bones = [i for i in range(skeleton_data.bone_count) if skeleton_data.bone_parent_ids[i] == 0xFFFFFFFF]
                    for root_bone_id in root_bones:
                        _process_bone(root_bone_id)

                    def _calculate_bone_length(cur_bone_id):
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
                            # If the bone is not a root bone, return the parent's length
                            if skeleton_data.bone_parent_ids[cur_bone_id] != 0xFFFFFFFF:
                                parent_bone_length = bone_lengths[skeleton_data.bone_parent_ids[cur_bone_id]]
                                if parent_bone_length > MIN_BONE_LENGTH:
                                    return parent_bone_length
                                else:
                                    return MIN_BONE_LENGTH

                            return 1
                        
                        bone_lengths[cur_bone_id] = pick_bone_length()
                        for child_id in [idx for idx, pid in enumerate(skeleton_data.bone_parent_ids) if pid == cur_bone_id]:
                            _calculate_bone_length(child_id)

                    for root_bone_id in root_bones:
                        _calculate_bone_length(root_bone_id)
                    
                    for i in range(skeleton_data.bone_count):
                        bones[i].length = bone_lengths[i]
                        edit_bone = armature_obj.data.edit_bones[skeleton_data.bone_names[i]]
                        edit_bone.matrix = bone_world_matrices[i]
                        ImportUtils.debug_print(self.debug, f"Bone [{bones[i].name}] matrix rotation: [{bone_world_matrices[i].to_quaternion()}]")
                        ImportUtils.debug_print(self.debug, f"Bone [{bones[i].name}] as edit_bone matrix rotation: [{edit_bone.matrix.to_quaternion()}]")
                        
                        if skeleton_data.bone_parent_ids[i] != 0xFFFFFFFF and i != 0:
                            # These bones are manually overriden in the original code to have no parent and their animations are given in world coordinates, so we fix these cases manually.
                            if bones[i].name.casefold() != "staffjoint2" and bones[i].name.casefold() != "r_handend1" and bones[i].name.casefold() != "l_handend1":
                                bones[i].parent = bones[skeleton_data.bone_parent_ids[i]]
                        ImportUtils.debug_print(self.debug, f"Length of bone [{bones[i].name}]: {bones[i].length}")

                    bpy.context.view_layer.update()
                    bpy.ops.object.mode_set(mode="OBJECT")

                except Exception as e:
                    self.report({"ERROR"}, f"Failed to create skeleton: {e}")
                    traceback.print_exc()
                    return {"CANCELLED"}

        return {"FINISHED"}

    def invoke(self, context: Context, event: Event):
        if self.directory:
            return context.window_manager.invoke_props_dialog(self)
            # return self.execute(context)
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

class CBB_FH_ImportSkeleton(bpy.types.FileHandler):
    bl_idname = "CBB_FH_skeleton_import"
    bl_label = "File handler for skeleton imports"
    bl_import_operator = ImportSkeleton.bl_idname
    bl_file_extensions = ImportSkeleton.filename_ext

    @classmethod
    def poll_drop(cls, context):
        return (context.area and context.area.type == "VIEW_3D")

class ExportSkeleton(Operator, ExportHelper):
    bl_idname = "cbb.skeleton_export"
    bl_label = "Export Skeleton"
    bl_options = {"PRESET"}

    filename_ext = ".Skeleton"

    filter_glob: StringProperty(default="*.Skeleton", options={"HIDDEN"})

    directory: StringProperty(subtype="FILE_PATH")

    debug: BoolProperty(
        name="Debug export",
        description="Enabling this option will make the exporter print debug data to console.",
        default=False
    )

    reassign_missing_armature_ids: BoolProperty(
        name="Reassign missing armature bone IDs",
        description="Enabling this option will rebuild any missing IDs in any bone in the armature.",
        default=False
    )

    z_minus_is_forward: BoolProperty(
        name="Z- is forward",
        description="Leave this option checked if you wish to work with Z- being the forward direction in Blender. If false, Z+ is considered forward.",
        default=True
    )

    def execute(self, context):
        return self.export_skeletons(context, self.directory)

    def export_skeletons(self: "ExportSkeleton", context: bpy.types.Context, directory: str):
        selected_objects: list[bpy.types.Object] = [obj for obj in context.selected_objects if obj.type == "ARMATURE"]
        if not selected_objects:
            selected_objects = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]

        if not selected_objects:
            self.report({"ERROR"}, f"There are no selected objects or objects in the scene with armatures. Aborting exportation.")
            return
        
        for scene_armature in selected_objects:
            def export_skeleton(armature_object: bpy.types.Armature):
                filepath: str = bpy.path.ensure_ext(directory + armature_object.name, self.filename_ext)
                ImportUtils.debug_print(self.debug, f"Exporting armature [{armature_object.name}] to file at [{filepath}]")

                if ImportUtils.is_armature_valid(self, armature_object, True) == False:
                    return
                
                if self.reassign_missing_armature_ids:
                    ImportUtils.rebuild_armature_bone_ids(self, armature_object)

                skeleton_data = SkeletonData()
                try:
                    bones: list[bpy.types.Bone] = armature_object.data.bones

                    # Initialize SkeletonData arrays with placeholders
                    bone_count: int = len(bones)
                    
                    skeleton_data.bone_count = bone_count
                    skeleton_data.bone_names = [""] * bone_count
                    skeleton_data.bone_parent_ids = [0] * bone_count
                    skeleton_data.bone_absolute_positions = [(0, 0, 0)] * bone_count
                    skeleton_data.bone_absolute_scales = [(1, 1, 1)] * bone_count
                    skeleton_data.bone_absolute_rotations = [(0, 0, 0, 1)] * bone_count


                    for bone in bones:
                        bone_id = bone.get("bone_id")
                        bone_matrix: Matrix = bone.matrix_local
                        
                        skeleton_data.bone_names[bone_id] = bone.name
                        skeleton_data.bone_parent_ids[bone_id] = bone.parent.get("bone_id") if bone.parent else 0xFFFFFFFF
                        skeleton_data.bone_absolute_positions[bone_id] = bone_matrix.to_translation()
                        skeleton_data.bone_absolute_scales[bone_id] = bone_matrix.to_scale()
                        skeleton_data.bone_absolute_rotations[bone_id] = bone_matrix.to_quaternion()

                    # Write the skeleton data to the file
                    SkeletonData.write_skeleton_data(self, filepath, skeleton_data)
                except Exception as e:
                    self.report({"ERROR"}, f"Failed to export skeleton: {e}")
                    traceback.print_exc()
                    return
            
            export_skeleton(scene_armature)


        return {"FINISHED"}


class SkeletonData:
    """
    Class that holds convenient skeleton information. Do note that absolute in the name of transform variables refers to them being 
    referent to the armature only, as if the armature transform was the center of the world.
    """
    def __init__(self):
        self.bone_count: int = 0
        self.bone_names: str = []
        self.bone_parent_ids: list[int] = []
        self.bone_absolute_positions: list[Vector] = []
        self.bone_absolute_scales: list[Vector]= []
        self.bone_absolute_rotations: list[Quaternion] = []
        self.bone_local_positions: list[Vector] = []
        self.bone_local_rotations: list[Quaternion] = []
    
    @staticmethod
    def read_skeleton_data(self: Operator, filepath: str) -> "SkeletonData":
        skeletonData = SkeletonData()
        try:
            with open(filepath, "rb") as f:
                # Skip irrelevant data
                f.seek(280, 0)

                skeletonData.bone_count = struct.unpack("<I", f.read(4))[0]
                f.seek(24, 1)
                ImportUtils.debug_print(self.debug, f"Bone count from source skeleton: {skeletonData.bone_count}")

                for _ in range(skeletonData.bone_count):
                    bone_name_bytes = f.read(128)
                    bone_name = bone_name_bytes.rstrip(b"\x00").decode("ascii", "ignore")
                    skeletonData.bone_names.append(bone_name)

                f.seek(12, 1)

                skeletonData.bone_parent_ids = list(struct.unpack("<{}I".format(skeletonData.bone_count), f.read(4 * skeletonData.bone_count)))

                # Some skeletons have the first bone, which is the root bone, with a parent to itself. That's obviously wrong, so we fix it manually.
                # The first bone is also usually treated as the root bone and ignores any attempts of parenting. The root bone should also have it's
                # rotation set to identity, otherwise the whole orientation of the skeleton might become weird when exporting(not exactly all the time, weird).
                skeletonData.bone_parent_ids[0] = 0xFFFFFFFF

                f.seek(12, 1)

                for _ in range(skeletonData.bone_count):
                    ImportUtils.debug_print(self.debug, f"Bone name: [{skeletonData.bone_names[_]}]. ID and parent ID: [{_}] | [{skeletonData.bone_parent_ids[_]}]")
                    bone_position: tuple[float, float, float] = struct.unpack("<3f", f.read(12))
                    bone_scale: tuple[float, float, float] = struct.unpack("<3f", f.read(12))
                    bone_rotation: tuple[float, float, float, float] = struct.unpack("<4f", f.read(16))
                    ImportUtils.debug_print(self.debug, f"Bone position (before conversion): [{bone_position}]")
                    ImportUtils.debug_print(self.debug, f"Bone scale (no conversion is done): [{bone_scale}]")
                    ImportUtils.debug_print(self.debug, f"Bone rotation (before conversion): [{bone_rotation}]")
                    bone_position = ImportUtils.convert_position_unity_to_blender(bone_position[0], bone_position[1], bone_position[2], self.z_minus_is_forward)
                    bone_rotation = ImportUtils.convert_quaternion_unity_to_blender(bone_rotation[0], bone_rotation[1], bone_rotation[2], bone_rotation[3], self.z_minus_is_forward)
                    ImportUtils.debug_print(self.debug, f"Bone position (after conversion): [{bone_position}]")
                    ImportUtils.debug_print(self.debug, f"Bone rotation (after conversion): [{bone_rotation}]")
                    skeletonData.bone_absolute_positions.append(bone_position)
                    skeletonData.bone_absolute_scales.append(mathutils.Vector(bone_scale))
                    skeletonData.bone_absolute_rotations.append(bone_rotation)
                
                for bone_id in range(skeletonData.bone_count):
                    ImportUtils.debug_print(self.debug, f"Bone name: [{skeletonData.bone_names[bone_id]}], local data:")
                    if skeletonData.bone_parent_ids[bone_id] != 0xFFFFFFFF:
                        parent_bone_id = skeletonData.bone_parent_ids[bone_id]
                        skeletonData.bone_local_positions.append(ImportUtils.get_local_position(skeletonData.bone_absolute_positions[parent_bone_id], skeletonData.bone_absolute_rotations[parent_bone_id], skeletonData.bone_absolute_positions[bone_id]))
                        skeletonData.bone_local_rotations.append(ImportUtils.get_local_rotation(skeletonData.bone_absolute_rotations[parent_bone_id], skeletonData.bone_absolute_rotations[bone_id]))
                    else:
                        skeletonData.bone_local_positions.append(skeletonData.bone_absolute_positions[bone_id])
                        skeletonData.bone_local_rotations.append(skeletonData.bone_absolute_rotations[bone_id])
                    ImportUtils.debug_print(self.debug, f"Local position: [{skeletonData.bone_local_positions[bone_id]}]")
                    ImportUtils.debug_print(self.debug, f"Local rotation: [{skeletonData.bone_local_rotations[bone_id]}]")

        except Exception as e:
            self.report({"ERROR"}, f"Failed to read file: {e}")
            traceback.print_exc()
            return
        
        return skeletonData
    
    @staticmethod
    def write_skeleton_data(self: Operator, filepath: str, skeleton_data: "SkeletonData") -> bool:
        try:
            with open(filepath, "wb") as file:
                file.write(struct.pack('I', 1979))
                file.write(struct.pack('I', 0))
                file.write(struct.pack('I', 50331648))
                file.write(struct.pack('I', 0xFFFFFFFF))
                file.write(struct.pack('I', 276))
                file.write(struct.pack('I', 3))
                file.write(bytearray(256))
                file.write(struct.pack('I', skeleton_data.bone_count))
                file.write(struct.pack('I', 0))
                file.write(struct.pack('I', 0))
                file.write(struct.pack('f', 30.0))
                file.write(struct.pack('I', 50332160))
                file.write(struct.pack("I", 128 * skeleton_data.bone_count))
                file.write(struct.pack('I', 0xFFFFFFFF))
                
                for name in skeleton_data.bone_names:
                    if len(name) > 128:
                        self.report({"ERROR"}, f"Bone name {name} exceeds 128 bytes.")
                        return False
                    file.write(name.encode('ascii').ljust(128, b'\x00'))
                
                file.write(struct.pack('I', 50332672))
                file.write(struct.pack('I', 4 * skeleton_data.bone_count))
                file.write(struct.pack('I', 0xFFFFFFFF))
                
                for parent_id in skeleton_data.bone_parent_ids:
                    file.write(struct.pack('I', parent_id))
                
                file.write(struct.pack('I', 50331904))
                file.write(struct.pack('I', 40 * skeleton_data.bone_count))
                file.write(struct.pack('I', 0xFFFFFFFF))
                
                for pos, scale, rot in zip(skeleton_data.bone_absolute_positions, skeleton_data.bone_absolute_scales, skeleton_data.bone_absolute_rotations):
                    file.write(struct.pack('3f', *ImportUtils.convert_position_blender_to_unity_vector(pos, self.z_minus_is_forward)))
                    file.write(struct.pack('3f', *scale))
                    file.write(struct.pack('4f', *ImportUtils.convert_quaternion_blender_to_unity_quaternion(rot, self.z_minus_is_forward)))
                
                file.write(struct.pack('I', 50332416))
                file.write(struct.pack('I', 0))
                file.write(struct.pack('I', 0xFFFFFFFF))
                
        except Exception as e:
            self.report({"ERROR"}, f"Failed to write skeleton to file at [{filepath}]: {e}")
            traceback.print_exc()
            return False
        
        ImportUtils.debug_print(self.debug, f"Skeleton written successfully to: [{filepath}]")
        return True
    
    @staticmethod 
    def build_skeleton_from_armature(self: Operator, armature_object: bpy.types.Object) -> "SkeletonData":
        """
            Function returns a SkeletonData class built from a Blender armature. The armature is expected to be valid.
        """
        skeleton_data = SkeletonData()
        skeleton_data.bone_count = len(armature_object.data.bones)
        skeleton_data.bone_names = [""] * skeleton_data.bone_count
        skeleton_data.bone_parent_ids = [-1] * skeleton_data.bone_count
        skeleton_data.bone_absolute_positions = [Vector((0.0, 0.0, 0.0))] * skeleton_data.bone_count
        skeleton_data.bone_absolute_scales = [Vector((0.0, 0.0, 0.0))] * skeleton_data.bone_count
        skeleton_data.bone_absolute_rotations = [Quaternion((0.0, 0.0, 0.0, 0.0))] * skeleton_data.bone_count
        skeleton_data.bone_local_positions = [Vector((0.0, 0.0, 0.0))] * skeleton_data.bone_count
        skeleton_data.bone_local_rotations = [Quaternion((0.0, 0.0, 0.0, 0.0))] * skeleton_data.bone_count
        for bone in armature_object.data.bones:
            bone_id = bone["bone_id"]
            skeleton_data.bone_names[bone_id] = bone.name
            edit_bone_position , edit_bone_rotation = ImportUtils.decompose_blender_matrix_position_rotation(bone.matrix_local)
            skeleton_data.bone_absolute_positions[bone_id] = edit_bone_position
            skeleton_data.bone_absolute_rotations[bone_id] = edit_bone_rotation
            skeleton_data.bone_absolute_scales[bone_id] = Vector((1.0, 1.0, 1.0))

            if bone.parent is not None:
                parent_edit_bone_position , parent_edit_bone_rotation = ImportUtils.decompose_blender_matrix_position_rotation(bone.parent.matrix_local)
                skeleton_data.bone_local_positions[bone_id] = ImportUtils.get_local_position(parent_edit_bone_position, parent_edit_bone_rotation, edit_bone_position)
                skeleton_data.bone_local_rotations[bone_id] = ImportUtils.get_local_rotation(parent_edit_bone_rotation, edit_bone_rotation)
                skeleton_data.bone_parent_ids[bone_id] = bone.parent["bone_id"]
            else:
                skeleton_data.bone_local_positions[bone_id] = edit_bone_position
                skeleton_data.bone_local_rotations[bone_id] = edit_bone_rotation
                skeleton_data.bone_parent_ids[bone_id] = 0xFFFFFFFF
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

def menu_func_import(self, context):
    self.layout.operator(ImportSkeleton.bl_idname, text="Skeleton (.Skeleton)")

def menu_func_export(self, context):
    self.layout.operator(ExportSkeleton.bl_idname, text="Skeleton (.Skeleton)")

def register():
    bpy.utils.register_class(ImportSkeleton)
    bpy.utils.register_class(CBB_FH_ImportSkeleton)
    bpy.utils.register_class(ExportSkeleton)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.utils.unregister_class(ImportSkeleton)
    bpy.utils.unregister_class(CBB_FH_ImportSkeleton)
    bpy.utils.unregister_class(ExportSkeleton)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

if __name__ == "__main__":
    register()
