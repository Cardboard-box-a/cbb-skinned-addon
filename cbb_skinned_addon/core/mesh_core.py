import bpy
import struct
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.types import Context, Event, Operator
from bpy.props import CollectionProperty, StringProperty, BoolProperty
from bpy_extras.io_utils import ImportHelper
import mathutils
from mathutils import Vector, Quaternion, Matrix
import math
import traceback
from utils import Utils, CoordsSys
Serializer = Utils.Serializer
CoordinatesConverter = Utils.CoordinatesConverter
import os
import xml.etree.ElementTree as ET
from .skeleton_core import SkeletonData
from pathlib import Path

def import_skinnedmesh(debug: bool, file_name: str, directory: str, apply_to_armature_in_selected: bool, only_deform_bones:bool, skeleton_name = "", texture_directory = "", texture_file_name = "", operator: Operator = None):
    """
    Imports any amount of given skinned mesh files. The function also tries to find suitable values for the default empty strings, if no value is given.
    """
    msg_handler = Utils.MessageHandler(debug, operator.report) if operator is not None else Utils.MessageHandler(debug)
    context = bpy.context
    
    return_value = {"CANCELLED"}
    
    msg_handler.debug_print(f"Skeleton name [{skeleton_name}] | Texture dir [{texture_directory}] | Texture name [{texture_file_name}]")
    
    if file_name.casefold().endswith(".skinnedmesh"):
        filepath: Path = Path(directory) / file_name
        
        
        base_file_name: str = filepath.stem
        
        # file_base_name is used to try and get the appropriate skeleton faster. Sometimes this is not possible, so we resort to searching in the xml files.
        item_base_identifier: str = base_file_name.split("_")[0]
        
        msg_handler.debug_print(f"Directory: {directory} \n File name: {file_name} \n base file name: {base_file_name} \n item identifier name: {item_base_identifier}")
        
        target_armature: bpy.types.Armature = None
        
        if apply_to_armature_in_selected == False:
            for obj in context.scene.objects:
                if obj.name.casefold() == item_base_identifier.casefold() and obj.type == "ARMATURE":
                    target_armature = obj
                    break
            if target_armature is None:
                skeleton_name = try_get_skeleton_name_for_mesh(Path(filepath), directory, msg_handler) if skeleton_name == "" else skeleton_name
                msg_handler.debug_print(f"Skeleton_name found: [{skeleton_name}]")
                if skeleton_name != "":
                    for obj in context.scene.objects:
                        if obj.name.casefold() == skeleton_name.casefold() and obj.type == "ARMATURE":
                            target_armature = obj
                            break
        
        else:
            for obj in context.selected_objects:
                if obj.type == "ARMATURE":
                    if target_armature is None:
                        target_armature = obj
                    else:
                        msg_handler.report("ERROR", f"More than one armature has been found in the current selection. The imported mesh can only be assigned to one armature at a time.")

        skeleton_data = None
        if target_armature:
            skeleton_data = SkeletonData.build_skeleton_from_armature(target_armature, only_deform_bones, False, msg_handler)
            if skeleton_data is None:
                msg_handler.report("INFO", f"Armature [{target_armature.name}] was found not valid. Weights won't be assigned to bones, but assigned to vertex groups with their IDs instead.") 
        else:
            msg_handler.report("INFO", f"Target armature of the file [{file_name}] could not be found. Weights won't be assigned to bones, but assigned to vertex groups with their IDs instead.")
        
        co_conv = CoordinatesConverter(CoordsSys.Unity, CoordsSys.Blender)
        
        try:
            with open(filepath, "rb") as opened_file:
                reader = Serializer(opened_file, Serializer.Endianness.Little, Serializer.Quaternion_Order.XYZW, Serializer.Matrix_Order.RowMajor, co_conv)
                
                try:
                    # Read the file header
                    name_length_in_bytes = reader.read_uint()*2
                    object_name = reader.read_fixed_string(name_length_in_bytes, "utf-16-le")
                    vertex_amount = reader.read_uint()
                    triangle_index_amount = reader.read_uint()
                    
                    msg_handler.debug_print(f"File [{base_file_name}] vertex amount: {vertex_amount}")
                    msg_handler.debug_print(f"File [{base_file_name}] triangle amount: {triangle_index_amount}")
                    
                    # 
                    opened_file.seek(24, 1)
                    
                    # Read the triangles
                    triangles = []
                    for _ in range(int(triangle_index_amount / 3)):
                        triangles.append((reader.read_ushort(), reader.read_ushort(), reader.read_ushort()))

                    opened_file.seek(4, 1)
                    # Read the vertices
                    vertices = []
                    for _ in range(vertex_amount):
                        vertices.append(reader.read_converted_vector3f())

                    # Read the normals
                    normal_amount = reader.read_uint()
                    msg_handler.debug_print(f"File [{base_file_name}] normal amount: {normal_amount}")
                    normals = []
                    for _ in range(normal_amount):
                        normals.append(reader.read_converted_vector3f())

                    # Read the texture coordinates
                    uv_amount = reader.read_uint()
                    msg_handler.debug_print(f"File [{base_file_name}] uv coordinates amount: {uv_amount}")
                    uvs = []
                    for _ in range(uv_amount):
                        uvs.append((reader.read_float(), -reader.read_float()))

                    # Read the bone weights
                    weight_amount = reader.read_uint()
                    msg_handler.debug_print(f"File [{base_file_name}] weight structure amount: {weight_amount}")
                    weights = []
                    for _ in range(weight_amount):
                        total_bones_with_weights_amount = reader.read_uint()
                        indice_amount = reader.read_uint()
                        indices = [reader.read_uint() for _ in range(indice_amount)]
                        weight_value_amount = reader.read_uint()
                        weight_values = [reader.read_float() for _ in range(weight_value_amount)]
                        weights.append((total_bones_with_weights_amount, indices, weight_values))
                    
                except UnicodeDecodeError as e:
                    msg_handler.report("ERROR", f"Unicode decode error while opening file at [{filepath}]: {e}")
                    traceback.print_exc()
                    return return_value
                
                except Exception as e:
                    msg_handler.report("ERROR", f"Unexpected error while opening file at [{filepath}]: {e}")
                    traceback.print_exc()
                    return return_value
                
        except Exception as e:
            msg_handler.report("ERROR", f"Could not open file for reading at [{filepath}]: {e}")
            traceback.print_exc()
            return return_value
        
        # At least one action modifies the scene, return FINISHED to allow undo
        return_value = {"FINISHED"}
        
        # Create the mesh in Blender
        mesh = bpy.data.meshes.new(base_file_name)
        obj = bpy.data.objects.new(base_file_name, mesh)
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
                    
        # If the texture file name was not given as a parameter, try to search for it
        if (texture_file_name == ""):
            texture_directory, texture_file_name = get_texture_directory_and_name(Path(opened_file.name), Path(directory), msg_handler)

        msg_handler.debug_print(f"texture_directory found: {texture_directory}")
        msg_handler.debug_print(f"texture_file_name found: {texture_file_name}")
        
        if texture_file_name != "":
            texture_path = find_texture_file(directory, texture_file_name, texture_directory, 10)
            if texture_path:
                apply_texture_to_mesh(obj, texture_path)
            else:
                msg_handler.report("INFO", f"Texture could not be found despite .xml file pointing to one: \n Directory: {texture_directory} \n Texture file name: {texture_file_name}")
        else:
            msg_handler.report("INFO", f"Texture file path for object [{file_name.name}] was not found.")
        
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
                    existing_modifier = obj.modifiers.new(name="Armature", type="ARMATURE")
                    existing_modifier.object = target_armature

            for i, (total_bones_with_weights_amount, indices, weight_values) in enumerate(weights):
                for bone_index, weight in zip(indices, weight_values):
                    bone_name = ""
                    if target_armature and skeleton_data:
                        bone_name = skeleton_data.bone_names[bone_index]
                    else: 
                        bone_name = f"{bone_index}"

                    group = obj.vertex_groups.get(bone_name)
                    if group is None:
                        group = obj.vertex_groups.new(name=bone_name)
                    group.add([i], weight, "REPLACE")
    else:
        msg_handler.report("ERROR", f"File [{file_name}] does not have the skinnedmesh extension.")

    return return_value

def find_target_directory(start_path: str, target_dir: str, max_levels: int) -> str | None:
    if not start_path:
        return None

    current_path = Path(start_path).resolve()

    for _ in range(max_levels):
        current_path = current_path.parent
        target_path = current_path / target_dir

        if target_path.exists():
            return str(target_path)

    return None

def find_texture_in_directory(target_directory, mesh_name, possible_extensions=[".png", ".jpg", ".jpeg", ".bmp", ".tga", ".dds"]):
    for root, dirs, files in os.walk(target_directory):
        for file in files:
            for ext in possible_extensions:
                if file.casefold() == (mesh_name + ext).casefold():
                    return Path(root).joinpath(file)
    return None

def find_texture_file(mesh_file_path, mesh_name, target_dir, max_levels):
    target_directory = find_target_directory(mesh_file_path, target_dir, max_levels)
    if not target_directory:
        return None

    # Search for the texture file in the target directory and its subdirectories
    texture_path = find_texture_in_directory(target_directory, mesh_name)
    return texture_path

def apply_texture_to_mesh(mesh_obj, texture_path):
    # Create a new material
    mat = bpy.data.materials.new(name=mesh_obj.name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]

    # Load the image texture
    tex_image = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex_image.image = bpy.data.images.load(str(texture_path))

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
        
    organizer = Utils.NodeOrganizer()
    organizer.arrange_nodes_no_context(mat.node_tree, 300, 300)
        
def get_texture_directory_and_name(file_path: Path, directory: Path, msg_handler: Utils.MessageHandler):
    mesh_material_file_name: str = ""
    mesh_material_name: str = ""

    msg_handler.debug_print("[get_texture_directory_and_name] method")
    msg_handler.debug_print(f"File_path used: {file_path}")

    def __get_material_file_and_name(xml_root_element):
        if xml_root_element is not None:
            model_element = xml_root_element.find(".//Models")
            for item_element in model_element.iterfind(".//item"):
                for item_child in item_element:
                    if item_child.tag == "Mesh":
                        mesh_attribute: str = item_child.get("value").lstrip("/")
                        if mesh_attribute is not None:
                            msg_handler.debug_print(f"Compared files: \n {mesh_attribute.casefold()} \n {file_path.name.casefold()}")
                            
                            if mesh_attribute.casefold() == file_path.name.casefold():
                                msg_handler.debug_print(f"Found match in mesh attribute and file name.")
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
                                        msg_handler.debug_print(f"Model of name: {material_attibute} failed to give value of Mesh tag.")
        return "", ""
    
    for file in Utils.find_single_xml_files(directory):
        msg_handler.debug_print(f"Trying to find .material.xml in the file {file}")
        filepath: Path = directory / file
        mesh_material_file_name, mesh_material_name = __get_material_file_and_name(Utils.read_xml_file(msg_handler, filepath, f"Error while trying to read source .xml file at [{filepath}]"))
        if mesh_material_file_name != "":
            break


    if mesh_material_file_name == "":
        msg_handler.report({"INFO"}, f"File [{file_path.name}]: .material.xml file for this file mesh was not found in any source .xml in the file directory.")
        return "", ""
    
    def __read_texture_xml(texture_xml_identifier):
        texture_xml_file_name: str = texture_xml_identifier.split("|")[0]
        texture_name_in_xml: str = texture_xml_identifier.split("|")[1]
        texture_xml_root = Utils.read_xml_file(msg_handler, directory / texture_xml_file_name, f"Error while trying to read .texture.xml file at [{directory / texture_xml_file_name}]")
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
                                return "/".join(target_dir), texture_file_name
        else:
            return "", ""

        

    material_xml_root = Utils.read_xml_file(msg_handler, directory / mesh_material_file_name, f"Error while trying to read  .material.xml file at [{directory / mesh_material_file_name}]")

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
                                    return "/".join(target_dir), texture_file_name
                                else:
                                    return __read_texture_xml(material_child_attribute)
    else:
        return "", ""


    return target_dir, texture_file_name

def try_get_skeleton_name_for_mesh(file_path: Path, directory: str, msg_handler: Utils.MessageHandler):
    mesh_animation_file_name: str = ""

    msg_handler.debug_print("[get_skeleton_name] method")
    msg_handler.debug_print(f"File_path used: {file_path}")

    def get_animation_file_and_name(xml_root_element: ET.Element):
        if xml_root_element is not None:
            model_element = xml_root_element.find(".//Models")
            for item_element in model_element.iterfind(".//item"):
                for item_child in item_element:
                    if item_child.tag == "Mesh":
                        mesh_attribute: str = item_child.get("value")
                        if mesh_attribute is not None:
                            mesh_attribute = mesh_attribute.lstrip("/")
                            msg_handler.debug_print(f"Compared files: \n {mesh_attribute.casefold()} \n {file_path.name.casefold()}")
                            if mesh_attribute.casefold() == file_path.name.casefold():
                                msg_handler.debug_print(f"Found match in mesh attribute and file name.")
                                animation_element = xml_root_element.find(".//Animation")
                                if animation_element is not None:
                                    animation_attribute = animation_element.get("value")
                                    if animation_attribute is not None:
                                        mesh_animation_file_name = animation_attribute.lstrip("/").split("|")[0]
                                        return mesh_animation_file_name
                                else:
                                    msg_handler.debug_print(f"Animation element could not be found inside a .xml source file.")
                        else:
                            for item_child_for_mesh in item_element:
                                if item_child_for_mesh.tag == "Name":
                                    name_attribute = item_child_for_mesh.get("value")
                                    if name_attribute is not None:
                                        msg_handler.debug_print(f"Model of name: {name_attribute} failed to give value of Mesh tag.")
        return ""
    
    for file in Utils.find_single_xml_files(directory):
        msg_handler.debug_print(f"Trying to find .animation.xml in the file {file}")
        filepath: str = Path(directory) / file
        mesh_animation_file_name = get_animation_file_and_name(Utils.read_xml_file(msg_handler, filepath, f"Error while trying to read source .xml file at [{filepath}]"))
        if mesh_animation_file_name != "":
            break


    if mesh_animation_file_name == "":
        msg_handler.report("INFO", f"File [{file_path.name}]: .animation.xml file for this file mesh was not found in any source .xml in the file directory.")
        return ""

    animation_xml_root = Utils.read_xml_file(msg_handler, Path(directory) / mesh_animation_file_name, f"Error while trying to read  .animation.xml file at [{Path(directory) / mesh_animation_file_name}]")

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

