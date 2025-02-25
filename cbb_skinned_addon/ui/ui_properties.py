from bpy.props import CollectionProperty, StringProperty, PointerProperty, BoolProperty, IntProperty
import bpy
from typing import Any, List, Optional, Union, Iterator, TYPE_CHECKING, TypeAlias

class MeshProperties(bpy.types.PropertyGroup):
    """Properties for each mesh extracted from XML"""
    name: StringProperty(
        name="Name",
        description="Animation name"
    )  # type: ignore
    mesh_path: StringProperty(
        name="Path",
        description="Path to the mesh file"
    )  # type: ignore
    material_file_path: StringProperty(
        name="Material Path",
        description="Path for the XML file for the mesh material"
    )  # type: ignore
    material_name: StringProperty(
        name="Material Name",
        description="Material name for the mesh"
    )  # type: ignore
    texture_folder: StringProperty(
        name="Texture Folder",
        description="Texture folder the texture is located at (can be relative)"
    )  # type: ignore
    texture_name: StringProperty(
        name="Texture Name",
        description="Mesh texture name"
    )  # type: ignore
    selected: BoolProperty(
        name="Selected",
        description="Whether this mesh is selected",
        default=False
    )  # type: ignore
    
class AnimationProperties(bpy.types.PropertyGroup):
    """Properties for each mesh extracted from XML"""
    name: StringProperty(
        name="Name",
        description="Animation name"
    )  # type: ignore
    animation_file_path: StringProperty(
        name="Animation Path",
        description="Path to the animation file"
    )  # type: ignore
    selected: BoolProperty(
        name="Selected",
        description="Whether this clip is selected",
        default=False
    )  # type: ignore

class LuniaProperties(bpy.types.PropertyGroup):
    """Lunia-specific properties container"""
    main_directory: StringProperty(
        name="Main XML File Directory",
        description="The path the main XML file is located at"
    )  # type: ignore
    
    animation_xml_path: StringProperty(
        name="Animation XML Path",
        description="Path to the animation XML file"
    )  # type: ignore
    animation_xml_name: StringProperty(
        name="Animation XML Name",
        description="Name of the animation XML"
    )  # type: ignore
    skeleton_file_name: StringProperty(
        name="Skeleton File Path",
        description="Path to the skeleton relative to the current animation data"
    ) # type: ignore
    
    animation_data: CollectionProperty(
        type=AnimationProperties,
        description="Collection of animation data from XML"
    )  # type: ignore
    mesh_data: CollectionProperty(
        type=MeshProperties,
        description="Collection of mesh data from XML"
    )  # type: ignore
    show_debug_info: BoolProperty(
        name="Show Debug Info",
        description="Display additional debugging information",
        default=False
    )  # type: ignore
    
    # import options
    apply_to_armature_mesh: BoolProperty(
        name="Apply to Armature in Selected Objects",
        description="Apply the import to the armature in selected objects",
        default=False
    ) # type: ignore
    apply_to_armature_anim: BoolProperty(
        name="Apply to Armature in Selected Objects",
        description="Apply the import to the armature in selected objects",
        default=False
    ) # type: ignore
    skeleton_import_debug: BoolProperty(
        name="Debug Import",
        description="Enable debug output during import",
        default=False
    ) # type: ignore
    mesh_import_debug: BoolProperty(
        name="Debug Import",
        description="Enable debug output during import",
        default=False
    ) # type: ignore
    animation_import_debug: BoolProperty(
        name="Debug Import",
        description="Enable debug output during import",
        default=False
    ) # type: ignore
    only_deform_bones: BoolProperty(
        name="Only Deform Bones",
        description="Consider only deform bones during import",
        default=True
    ) # type: ignore
    
    last_selected_mesh_index: IntProperty(
        name="Last Selected Index",
        description="Index of the last selected mesh for range selection",
        default=-1,
        options={'HIDDEN'}
    )  # type: ignore
    last_selected_anim_index: IntProperty(
        name="Last Selected Index",
        description="Index of the last selected anim for range selection",
        default=-1,
        options={'HIDDEN'}
    )  # type: ignore
    
    active_mesh_index: IntProperty(
        name="Active Mesh Index",
        description="Index of the active mesh in the list (for template_list)",
        default=-1
    )  # type: ignore
    active_animation_index: IntProperty(
        name="Active Anim Index",
        description="Index of the active animation in the list (for template_list)",
        default=-1
    )  # type: ignore
    
classes = (
MeshProperties,
AnimationProperties,
LuniaProperties,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()