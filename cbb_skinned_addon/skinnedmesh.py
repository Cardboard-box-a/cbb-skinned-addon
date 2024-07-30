import bpy
import struct
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.types import Context, Event, Operator
from bpy.props import CollectionProperty, StringProperty, BoolProperty
from bpy_extras.io_utils import ImportHelper
import ntpath
import mathutils
from mathutils import Vector, Quaternion, Matrix
import math
import traceback
from import_utils import ImportUtils
import os
import xml.etree.ElementTree as ET

class ImportSkinnedMesh(Operator, ImportHelper):
    bl_idname = "cbb.skinnedmesh_import"
    bl_label = "Import SkinnedMesh"
    bl_options = {"PRESET", "UNDO"}

    filename_ext = ".SkinnedMesh"

    filter_glob: StringProperty(default="*.SkinnedMesh",options={"HIDDEN"})

    files: CollectionProperty(
        type=bpy.types.OperatorFileListElement,
        options={"HIDDEN", "SKIP_SAVE"}
    )

    directory: StringProperty(subtype="DIR_PATH")

    apply_to_armature_in_selected: BoolProperty(
        name="Apply to armature in selected",
        description="Enabling this option will make the import of the animation to target any armature present between currently selected objects.",
        default=False
    )

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

    def find_target_directory(start_path, target_dir, max_levels):
        if start_path == "":
            return ""
        
        current_path = start_path
        for _ in range(max_levels):
            current_path = os.path.abspath(os.path.join(current_path, os.pardir))
            if os.path.exists(os.path.join(current_path, *target_dir)):
                return os.path.join(current_path, *target_dir)
            
        return None
    
    def find_texture_in_directory(target_directory, mesh_name, possible_extensions=[".png", ".jpg", ".jpeg", ".bmp", ".tga", ".dds"]):
        for root, dirs, files in os.walk(target_directory):
            for file in files:
                for ext in possible_extensions:
                    if file.casefold() == (mesh_name + ext).casefold():
                        return os.path.join(root, file)
        return None
    
    def find_texture_file(mesh_file_path, mesh_name, target_dir, max_levels):
        target_directory = ImportSkinnedMesh.find_target_directory(mesh_file_path, target_dir, max_levels)
        if not target_directory:
            return None

        # Search for the texture file in the target directory and its subdirectories
        texture_path = ImportSkinnedMesh.find_texture_in_directory(target_directory, mesh_name)
        return texture_path
    @staticmethod
    def apply_texture_to_mesh(mesh_obj, texture_path):
        # Create a new material
        mat = bpy.data.materials.new(name=mesh_obj.name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]

        # Load the image texture
        tex_image = mat.node_tree.nodes.new("ShaderNodeTexImage")
        tex_image.image = bpy.data.images.load(texture_path)

        # Connect the image texture to the BSDF shader
        mat.node_tree.links.new(bsdf.inputs["Base Color"], tex_image.outputs["Color"])
        # Set specular value to 0
        specular_value = mat.node_tree.nodes.new(type="ShaderNodeValue")
        mat.node_tree.links.new(specular_value.outputs[0], bsdf.inputs[12])

        # Assign the material to the mesh
        if mesh_obj.data.materials:
            # Assign to first material slot
            mesh_obj.data.materials[0] = mat
        else:
            # Add a new material slot
            mesh_obj.data.materials.append(mat)
    @staticmethod
    def get_texture_directory_and_name(file_path, self):
        mesh_material_file_name: str = ""
        mesh_material_name: str = ""

        ImportUtils.debug_print(self, "[get_texture_directory_and_name] method")
        ImportUtils.debug_print(self, f"File_path used: {file_path}")

        def get_material_file_and_name(xml_root_element):
            if xml_root_element is not None:
                model_element = xml_root_element.find(".//Models")
                for item_element in model_element.iterfind(".//item"):
                    for item_child in item_element:
                        if item_child.tag == "Mesh":
                            mesh_attribute: str = item_child.get("value").lstrip("/")
                            if mesh_attribute is not None:
                                ImportUtils.debug_print(self, f"Compared files: \n {mesh_attribute.casefold()} \n {ntpath.basename(file_path).casefold()}")
                                if mesh_attribute.casefold() == ntpath.basename(file_path).casefold():
                                    ImportUtils.debug_print(self, f"Found match in mesh attribute and file name.")
                                    for item_child_for_mesh in item_element:
                                        if item_child_for_mesh.tag == "Material":
                                            material_attibute = item_child_for_mesh.get("value").lstrip("/")
                                            if material_attibute is not None:
                                                mesh_material_file_name = material_attibute.split("|")[0]
                                                mesh_material_name = material_attibute.split("|")[1]
                                                return mesh_material_file_name, mesh_material_name
                            else:
                                for item_child_for_mesh in item_element:
                                    if item_child_for_mesh.tag == "Name":
                                        material_attibute = item_child_for_mesh.get("value")
                                        if material_attibute is not None:
                                            ImportUtils.debug_print(self, f"Model of name: {material_attibute} failed to give value of Mesh tag.")
            return "", ""
        
        for file in ImportUtils.find_single_xml_files(self.directory):
            ImportUtils.debug_print(self, f"Trying to find .material.xml in the file {ntpath.basename(file)}")
            filepath: str = self.directory + ntpath.basename(file)
            mesh_material_file_name, mesh_material_name = get_material_file_and_name(ImportUtils.read_xml_file(self, filepath, f"Error while trying to read source .xml file at [{filepath}]"))
            if mesh_material_file_name != "":
                break


        if mesh_material_file_name == "":
            self.report({"INFO"}, f"File [{ntpath.basename(file_path)}]: .material.xml file for this file mesh was not found in any source .xml in the file directory.")
            return "", ""
        
        def read_texture_xml(texture_xml_identifier):
            texture_xml_file_name: str = texture_xml_identifier.split("|")[0]
            texture_name_in_xml: str = texture_xml_identifier.split("|")[1]
            texture_xml_root = ImportUtils.read_xml_file(self, self.directory + texture_xml_file_name, f"Error while trying to read .texture.xml file at [{self.directory + texture_xml_file_name}]")
            if texture_xml_root is not None:
                for texture_element in texture_xml_root.iterfind(".//texture"):
                    if texture_element is not None and texture_element.get("name").casefold() == texture_name_in_xml.casefold():
                        for texture_child in texture_element:
                            if texture_child.tag == "source":
                                texture_attibute = texture_child.get("value")
                                if texture_attibute is not None:
                                    target_dir = texture_attibute.split("/")
                                    texture_file_name = target_dir[-1].split(".")[0]
                                    target_dir = target_dir[:-1]
                                    return target_dir, texture_file_name
            else:
                return "", ""

            

        material_xml_root = ImportUtils.read_xml_file(self, self.directory + mesh_material_file_name, f"Error while trying to read  .material.xml file at [{self.directory + mesh_material_file_name}]")

        target_dir = ""
        texture_file_name = ""
        if material_xml_root is not None:
            for material_element in material_xml_root.iterfind(".//material"):
                material_element_attribute = material_element.get("name")
                if material_element_attribute is not None and material_element_attribute.casefold() == mesh_material_name.casefold():
                    for material_child in material_element:
                            if material_child.tag == "diffuse_tex":
                                material_child_attribute = material_child.get("value").lstrip("/")
                                if material_child_attribute is not None:
                                    if material_child_attribute.split("|")[0].split(".")[-1].casefold() != "xml".casefold():
                                        target_dir = material_child_attribute.split("/")
                                        texture_file_name = target_dir[-1].split(".")[0]
                                        target_dir = target_dir[:-1]
                                        return target_dir, texture_file_name
                                    else:
                                        return read_texture_xml(material_child_attribute)
        else:
            return "", ""


        return target_dir, texture_file_name
    @staticmethod
    def get_skeleton_name(file_path, self):
        mesh_animation_file_name: str = ""
        mesh_animation_name: str = ""

        ImportUtils.debug_print(self, "[get_skeleton_name] method")
        ImportUtils.debug_print(self, f"File_path used: {file_path}")

        def get_animation_file_and_name(xml_root_element: ET.Element):
            if xml_root_element is not None:
                model_element = xml_root_element.find(".//Models")
                for item_element in model_element.iterfind(".//item"):
                    for item_child in item_element:
                        if item_child.tag == "Mesh":
                            mesh_attribute: str = item_child.get("value").lstrip("/")
                            if mesh_attribute is not None:
                                ImportUtils.debug_print(self, f"Compared files: \n {mesh_attribute.casefold()} \n {ntpath.basename(file_path).casefold()}")
                                if mesh_attribute.casefold() == ntpath.basename(file_path).casefold():
                                    ImportUtils.debug_print(self, f"Found match in mesh attribute and file name.")
                                    animation_element = xml_root_element.find(".//Animation")
                                    if animation_element is not None:
                                        animation_attribute = animation_element.get("value")
                                        if animation_attribute is not None:
                                            mesh_animation_file_name = animation_attribute.lstrip("/").split("|")[0]
                                            mesh_animation_name = animation_attribute.lstrip("/").split("|")[1]
                                            return mesh_animation_file_name, mesh_animation_name
                                    else:
                                        ImportUtils.debug_print(self, f"Animation element could not be found inside a .xml source file.")
                            else:
                                for item_child_for_mesh in item_element:
                                    if item_child_for_mesh.tag == "Name":
                                        name_attribute = item_child_for_mesh.get("value")
                                        if name_attribute is not None:
                                            ImportUtils.debug_print(self, f"Model of name: {name_attribute} failed to give value of Mesh tag.")
            return "", ""
        
        for file in ImportUtils.find_single_xml_files(self.directory):
            ImportUtils.debug_print(self, f"Trying to find .animation.xml in the file {ntpath.basename(file)}")
            filepath: str = self.directory + ntpath.basename(file)
            mesh_animation_file_name, mesh_animation_name = get_animation_file_and_name(ImportUtils.read_xml_file(self, filepath, f"Error while trying to read source .xml file at [{filepath}]"))
            if mesh_animation_file_name != "":
                break


        if mesh_animation_file_name == "":
            self.report({"INFO"}, f"File [{ntpath.basename(file_path)}]: .animation.xml file for this file mesh was not found in any source .xml in the file directory.")
            return ""

        animation_xml_root = ImportUtils.read_xml_file(self, self.directory + mesh_animation_file_name, f"Error while trying to read  .animation.xml file at [{self.directory + mesh_animation_file_name}]")

        skeleton_name = ""
        if animation_xml_root is not None:
            for animation_element in animation_xml_root.iterfind(".//animation"):
                skeleton_element = animation_element.find(".//skeleton")
                if skeleton_element is not None:
                    skeleton_attribute: str = skeleton_element.get("value")
                    if skeleton_attribute is not None:
                        skeleton_name = skeleton_attribute.lstrip("/").split(".")[0]
        else:
            return ""


        return skeleton_name

    def execute(self, context):
        return self.import_skinnedmeshes(context)

    def import_skinnedmeshes(self, context):
        for file in self.files:
            if file.name.casefold().endswith(".SkinnedMesh".casefold()):
                def import_skinnedmesh(file):
                    filepath: str = self.directory + file.name
                    pure_file_name: str = ntpath.basename(filepath).split(".")[0]
                    file_base_name: str = ntpath.basename(file.name).rsplit(".", 1)[0].split("_")[0]
                    ImportUtils.debug_print(self, f"Directory: {self.directory} \n File name: {file.name} \n Pure file name: {pure_file_name} \n File base name: {file_base_name}")
                    skeleton_name = ""
                    target_armature: bpy.types.Armature = None
                    if self.apply_to_armature_in_selected == False:
                        for obj in bpy.context.scene.objects:
                            if obj.name.casefold() == file_base_name.casefold() and obj.type == "ARMATURE":
                                target_armature = obj
                                break
                        if target_armature is None:
                            skeleton_name = ImportSkinnedMesh.get_skeleton_name(filepath, self)
                            ImportUtils.debug_print(self, f"Skeleton_name found: [{skeleton_name}]")
                            if skeleton_name != "":
                                for obj in bpy.context.scene.objects:
                                    if obj.name.casefold() == skeleton_name.casefold() and obj.type == "ARMATURE":
                                        target_armature = obj
                                        break
                    else:
                        for obj in bpy.context.selected_objects:
                            if obj.type == "ARMATURE":
                                target_armature = obj
                                break

                    target_armature_bone_names = []
                    if target_armature:
                        if ImportUtils.is_armature_valid(self, target_armature, False) == True:
                            target_armature_bone_names = [""] * len(target_armature.data.bones)
                            for bone in target_armature.data.bones:
                                bone_id = bone.get("bone_id")
                                target_armature_bone_names[bone_id] = bone.name
                        else:
                            self.report({"INFO"}, f"Armature [{target_armature.name}] was found not valid. Weights won't be assigned to bones, but assigned to vertex groups with their IDs instead.")
                    else:
                        self.report({"INFO"}, f"Target armature of the file [{file.name}] could not be found. Weights won't be assigned to bones, but assigned to vertex groups with their IDs instead.")
                    
                    with open(filepath, "rb") as opened_file:
                        data = opened_file.read()
                        offset = 0

                        def read_uint32():
                            nonlocal offset
                            val = struct.unpack_from("<I", data, offset)[0]
                            offset += 4
                            return val

                        def read_float():
                            nonlocal offset
                            val = struct.unpack_from("<f", data, offset)[0]
                            offset += 4
                            return val

                        def read_uint16():
                            nonlocal offset
                            val = struct.unpack_from("<H", data, offset)[0]
                            offset += 2
                            return val

                        def read_string():
                            nonlocal offset
                            length = read_uint32()
                            str_data = data[offset:offset + (length - 1) * 2]
                            offset += length * 2
                            return str_data.decode("utf-16")

                        try:
                            # Read the file header
                            object_name = read_string()
                            vertex_amount = read_uint32()
                            triangle_amount = read_uint32()
                            ImportUtils.debug_print(self, f"File [{pure_file_name}] vertex amount: {vertex_amount}")
                            ImportUtils.debug_print(self, f"File [{pure_file_name}] triangle amount: {triangle_amount}")
                            offset += 24
                            
                            # Read the triangles
                            triangles = []
                            for _ in range(int(triangle_amount / 3)):
                                a = read_uint16()
                                b = read_uint16()
                                c = read_uint16()
                                triangles.append((a, b, c))

                            
                            offset += 4
                            # Read the vertices
                            vertices = []
                            for _ in range(vertex_amount):
                                x = read_float()
                                y = read_float()
                                z = read_float()
                                vertices.append(ImportUtils.convert_position_unity_to_blender(x, y, z, self.z_minus_is_forward))

                            # Read the normals
                            normal_amount = read_uint32()
                            ImportUtils.debug_print(self, f"File [{pure_file_name}] normal amount: {normal_amount}")
                            normals = []
                            for _ in range(normal_amount):
                                x = read_float()
                                y = read_float()
                                z = read_float()
                                normals.append(ImportUtils.convert_position_unity_to_blender(x, y, z, self.z_minus_is_forward))

                            # Read the texture coordinates
                            uv_amount = read_uint32()
                            ImportUtils.debug_print(self, f"File [{pure_file_name}] uv coordinates amount: {uv_amount}")
                            uvs = []
                            for _ in range(uv_amount):
                                u = read_float()
                                v = read_float()
                                uvs.append((u, 1-v))

                            # Read the bone weights
                            weight_amount = read_uint32()
                            ImportUtils.debug_print(self, f"File [{pure_file_name}] weight structure amount: {weight_amount}")
                            weights = []
                            for _ in range(weight_amount):
                                total_bones_with_weights_amount = read_uint32()
                                indice_amount = read_uint32()
                                indices = [read_uint32() for _ in range(indice_amount)]
                                weight_value_amount = read_uint32()
                                weight_values = [read_float() for _ in range(weight_value_amount)]
                                weights.append((total_bones_with_weights_amount, indices, weight_values))
                            # File reading end

                            # Create the mesh in Blender
                            mesh = bpy.data.meshes.new(pure_file_name)
                            obj = bpy.data.objects.new(pure_file_name, mesh)
                            context.collection.objects.link(obj)

                            mesh.from_pydata(vertices, [], triangles, False)
                            mesh.update()

                            # Assign UVs
                            if uvs:
                                mesh.uv_layers.new(name="UVMap")
                                uv_layer = mesh.uv_layers.active.data
                                for poly in mesh.polygons:
                                    for loop_index in range(poly.loop_start, poly.loop_start + poly.loop_total):
                                        uv = uvs[mesh.loops[loop_index].vertex_index]
                                        uv_layer[loop_index].uv = uv
                                        
                            # Trying to search a texture for a standalone mesh will get the first texture assigned, which usually is the _a variation for player characters.
                            texture_directory, texture_file_name = ImportSkinnedMesh.get_texture_directory_and_name(opened_file.name, self)

                            ImportUtils.debug_print(self, f"texture_directory found: {texture_directory}")
                            ImportUtils.debug_print(self, f"texture_file_name found: {texture_file_name}")
                            if texture_file_name != "":
                                texture_path = ImportSkinnedMesh.find_texture_file(self.directory, texture_file_name, texture_directory, 10)
                                if texture_path:
                                    ImportSkinnedMesh.apply_texture_to_mesh(obj, texture_path)
                                else:
                                    self.report({"INFO"}, f"Texture could not be found despite .xml file pointing to one: \n Directory: {os.path.join(*texture_directory)} \n Texture file name: {texture_file_name}")
                            else:
                                self.report({"INFO"}, f"Texture file path for object [{file.name}] was not found.")
                            
                            # Assign weights
                            if weights:
                                # Check if the object already has an Armature modifier
                                existing_modifier = None
                                if target_armature:
                                    for mod in obj.modifiers:
                                        if mod.type == "ARMATURE" and mod.object == target_armature:
                                            existing_modifier = mod
                                            break
                                
                                    if not existing_modifier:
                                        modifier = obj.modifiers.new(name="Armature", type="ARMATURE")
                                        modifier.object = target_armature
                                    else:
                                        modifier = existing_modifier

                                for i, (total_bones_with_weights_amount, indices, weight_values) in enumerate(weights):
                                    for bone_index, weight in zip(indices, weight_values):
                                        bone_name = ""
                                        if target_armature and target_armature_bone_names[bone_index] != "":
                                            bone_name = target_armature_bone_names[bone_index]
                                        else: 
                                            bone_name = f"{bone_index}"

                                        group = obj.vertex_groups.get(bone_name)
                                        if group is None:
                                            group = obj.vertex_groups.new(name=bone_name)
                                        group.add([i], weight, "REPLACE")

                        except UnicodeDecodeError as e:
                            self.report({"ERROR"}, f"Unicode decode error while opening file at [{filepath}]: {e}")
                            traceback.print_exc()
                            return
                        
                        except Exception as e:
                            self.report({"ERROR"}, f"Unexpected error while opening file at [{filepath}]: {e}")
                            traceback.print_exc()
                            return

                import_skinnedmesh(file)

        return {"FINISHED"}

    def invoke(self, context: Context, event: Event):
        if self.directory:
            return context.window_manager.invoke_props_dialog(self)
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

class CBB_FH_ImportSkinnedMesh(bpy.types.FileHandler):
    bl_idname = "CBB_FH_skinnedmesh_import"
    bl_label = "File handler for skinnedmesh imports"
    bl_import_operator = ImportSkinnedMesh.bl_idname
    bl_file_extensions = ImportSkinnedMesh.filename_ext

    @classmethod
    def poll_drop(cls, context):
        return (context.area and context.area.type == "VIEW_3D")

class ExportSkinnedMesh(Operator, ExportHelper):
    bl_idname = "cbb.skinnedmesh_export"
    bl_label = "Export SkinnedMesh"
    bl_options = {"PRESET"}

    filename_ext = ".SkinnedMesh"

    filter_glob: StringProperty(default="*.SkinnedMesh",options={"HIDDEN"})

    directory: StringProperty(
        name="Directory",
        description="Directory to export files to",
        subtype="DIR_PATH",
        default=""
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

    def execute(self, context):
        return self.export_skinnedmeshes(context, self.directory)

    def export_skinnedmeshes(self, context, directory):
        selected_objects = [obj for obj in context.selected_objects if obj.type == "MESH"]
        if not selected_objects:
            selected_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]

        if not selected_objects:
            self.report({"ERROR"}, f"There are no selected objects or objects in the scene with meshes. Aborting exportation.")
            return {"CANCELLED"}
        
        for scene_mesh in selected_objects:
            def export_skinnedmesh(mesh_object):
                try:
                    filepath = bpy.path.ensure_ext(directory + "/" + mesh_object.name, self.filename_ext)
                    ImportUtils.debug_print(self, f"Exporting mesh [{mesh_object.name}] to file at [{filepath}]")

                    mesh_armature: bpy.types.Armature = None
                    for mod in mesh_object.modifiers:
                        if mod.type == "ARMATURE":
                            mesh_armature = mod.object

                    bone_name_to_id = {}
                    if mesh_armature:
                        if ImportUtils.is_armature_valid(self, mesh_armature, True) == False:
                            self.report({"ERROR"}, f"Armature {mesh_armature.name}, target of [{mesh_object.name}], was found not valid. Aborting this exportation.")
                            return
                    else:
                        self.report({"ERROR"}, f"Target armature in ARMATURE modifier in the object [{mesh_object.name}] could not be found. Aborting this exportation.")
                        return

                    mesh = mesh_object.data
                    vertices = mesh.vertices
                    polygons = mesh.polygons
                    loops = mesh.loops
                    uvs = mesh.uv_layers.active.data if mesh.uv_layers.active else None

                    ImportUtils.debug_print(self, f"Object [{mesh_object.name}]'s vertex amount: [{len(vertices)}]")
                    ImportUtils.debug_print(self, f"Object [{mesh_object.name}]'s polygon amount: [{len(polygons)}]")
                    ImportUtils.debug_print(self, f"Object [{mesh_object.name}]'s loop amount: [{len(loops)}]")
                    ImportUtils.debug_print(self, f"Object [{mesh_object.name}]'s uv amount: [{len(uvs)}]")

                    if len(vertices) > 65536:
                        self.report({"ERROR"}, f"Error while exporting mesh [{mesh_object.name}]: mesh has more than 65536 vertices. The .SkinnedMesh file type can't work with more than this quantity.")
                        return

                    # Step 1: Get original vertices
                    original_vertices = [v.co for v in vertices]

                    # Step 2: Construct collection of vertex index and UVs from loops
                    loop_data = []
                    for poly in polygons:
                        for loop_index in poly.loop_indices:
                            loop = loops[loop_index]
                            uv = tuple((uvs[loop.index].uv)) if uvs else (0.0, 0.0)
                            loop_data.append((loop.vertex_index, uv))

                    # Step 4: Create unique vertices collection
                    unique_vertices = []
                    unique_uvs = []
                    seen_pairs = set()

                    for vertex_index, uv in loop_data:
                        if (vertex_index, uv) not in seen_pairs:
                            unique_vertices.append(vertex_index)
                            unique_uvs.append(tuple(uv))
                            seen_pairs.add((vertex_index, uv))

                    # Step 5: Build exporter vertex collection
                    exporter_vertices = []
                    exporter_normals = []
                    exporter_uvs = []
                    exporter_weights = []

                    vertex_mapping = {}
                    for i, (vertex_index, uv) in enumerate(zip(unique_vertices, unique_uvs)):
                        exporter_vertices.append(original_vertices[vertex_index])
                        exporter_normals.append(vertices[vertex_index].normal)
                        exporter_uvs.append(uv)

                        vertex_mapping[(vertex_index, uv)] = i

                        # Get bone weights
                        vertex = vertices[vertex_index]
                        groups = vertex.groups
                        bone_indices = []
                        weights = []
                        if mesh_armature:
                            for group in groups:
                                bone_name = mesh_object.vertex_groups[group.group].name
                                bone_id = bone_name_to_id.get(bone_name, 0)
                                bone_indices.append(bone_id)
                                weights.append(group.weight)
                            
                            exporter_weights.append((len(groups), len(bone_indices), bone_indices, len(weights), weights))

                    # Rebuild polygon indices
                    new_polygons = []
                    for poly in polygons:
                        new_poly = []
                        for loop_index in poly.loop_indices:
                            loop = loops[loop_index]
                            uv = tuple((uvs[loop.index].uv)) if uvs else (0.0, 0.0)
                            new_poly.append(vertex_mapping[(loop.vertex_index, tuple(uv))])
                        new_polygons.append(new_poly)

                    ImportUtils.debug_print(self, f"Object [{mesh_object.name}]'s vertex amount for export: [{len(exporter_vertices)}]")
                    ImportUtils.debug_print(self, f"Object [{mesh_object.name}]'s polygon amount for export: [{len(new_polygons)}]")

                    if len(exporter_vertices) > 65536:
                        self.report({"ERROR"}, f"Error while exporting mesh [{mesh_object.name}]: mesh has {len(exporter_vertices)} vertices after vertex remapping, which is more than 65536 vertices.\nThis issue can be caused by the mesh's uv map having duplicate entries for each vertex. Consider remapping the mesh's UV map as a single continuous map or reduce the total amount of vertices.")
                        return
                except Exception as e:
                    self.report({"ERROR"}, f"Exception while trying to remap vertices for object [{mesh_object.name}]: {e}")
                    return
                try:
                    # Write to file
                    with open(filepath, "wb") as file:
                        # 1. Write the length in characters of the name of the object (including null terminator)
                        name = mesh_object.name
                        name_length = len(name) + 1
                        file.write(struct.pack("I", name_length)) 

                        # 2. The name of the object as a Unicode string
                        file.write(name.encode("utf-16-le") + b"\x00\x00")

                        # 3. The amount of vertices in the mesh as an integer
                        vertex_count = len(exporter_vertices)
                        file.write(struct.pack("I", vertex_count))

                        # 4. The amount of triangles in the mesh as an integer
                        triangle_count = sum(len(poly) - 2 for poly in new_polygons)
                        file.write(struct.pack("I", triangle_count*3))

                        # 5. Write five consecutive integers: 1, 1, 0, 1, 1
                        file.write(struct.pack("5I", 1, 1, 0, 1, 1))

                        # 6. The amount of triangles in the mesh as an integer again
                        file.write(struct.pack("I", triangle_count*3))

                        # 7. All the indices that make all the triangles in the mesh
                        for poly in new_polygons:
                            if len(poly) == 3:
                                file.write(struct.pack("3H", *poly))
                            elif len(poly) == 4:
                                # If the polygon is a quad, split it into two triangles
                                file.write(struct.pack("3H", poly[0], poly[1], poly[2]))
                                file.write(struct.pack("3H", poly[0], poly[2], poly[3]))
                            else:
                                # Handle polygons with more than 4 vertices (n-gons)
                                v0 = poly[0]
                                for i in range(1, len(poly) - 1):
                                    file.write(struct.pack("3H", v0, poly[i], poly[i + 1]))

                        # 8. The amount of vertices in the mesh as an integer again
                        file.write(struct.pack("I", vertex_count))

                        # 9. All the vertices in the mesh (position: float, float, float)
                        for vertex in exporter_vertices:
                            converted_position = ImportUtils.convert_position_blender_to_unity_vector(Vector((vertex.x, vertex.y, vertex.z, self.z_minus_is_forward)))
                            file.write(struct.pack("3f", converted_position.x, converted_position.y, converted_position.z))

                        # 10. The amount of normals in the mesh (same as vertices)
                        file.write(struct.pack("I", vertex_count))

                        # 11. All the normals in the mesh
                        for normal in exporter_normals:
                            converted_normal = ImportUtils.convert_position_blender_to_unity_vector(Vector((normal.x, normal.y, normal.z, self.z_minus_is_forward)))
                            file.write(struct.pack("3f", converted_normal.x, converted_normal.y, converted_normal.z))

                        # 12. The amount of UV coordinates in the mesh (same as vertices)
                        file.write(struct.pack("I", vertex_count))

                        # 13. All UV coordinates of the mesh
                        for uv in exporter_uvs:
                            file.write(struct.pack("2f", uv[0], 1 - uv[1]))

                        # 14. The amount of weights in the mesh (same as vertices)
                        file.write(struct.pack("I", vertex_count))

                        # 15. All the weights for each vertex
                        for groups_count, bone_count, bone_indices, weight_count, weights in exporter_weights:
                            file.write(struct.pack("I", groups_count))  # Number of bones with weight assigned
                            file.write(struct.pack("I", bone_count))  # Amount of bone indices
                            file.write(struct.pack(f"{bone_count}I", *bone_indices))  # Bone indices array
                            file.write(struct.pack("I", weight_count))  # Amount of weights
                            file.write(struct.pack(f"{weight_count}f", *weights))  # Bone weights array
                except Exception as e:
                    self.report({"ERROR"}, f"Exception while writing to file at [{filepath}]: {e}")
                    return

            export_skinnedmesh(scene_mesh)

        return {"FINISHED"}


def menu_func_import(self, context):
    self.layout.operator(ImportSkinnedMesh.bl_idname, text="SkinnedMesh (.SkinnedMesh)")

def menu_func_export(self, context):
    self.layout.operator(ExportSkinnedMesh.bl_idname, text="SkinnedMesh (.SkinnedMesh)")

def register():
    bpy.utils.register_class(ImportSkinnedMesh)
    bpy.utils.register_class(CBB_FH_ImportSkinnedMesh)
    bpy.utils.register_class(ExportSkinnedMesh)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.utils.unregister_class(ImportSkinnedMesh)
    bpy.utils.unregister_class(CBB_FH_ImportSkinnedMesh)
    bpy.utils.unregister_class(ExportSkinnedMesh)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_export)

if __name__ == "__main__":
    register()
