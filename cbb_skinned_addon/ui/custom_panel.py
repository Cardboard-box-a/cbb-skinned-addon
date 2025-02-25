import bpy
import xml.etree.ElementTree as ET
from bpy.types import UILayout
import bpy_extras
from bpy.props import CollectionProperty, StringProperty, PointerProperty, BoolProperty, IntProperty
from pathlib import Path
from ..core.mesh_core import import_skinnedmesh
from ..operators.mesh_operators import CBB_OT_SkinnedMeshImportLoaded
from ..operators.skeleton_operators import CBB_OT_SkeletonImportLoaded
from ..operators.animation_operators import CBB_OT_SkinnedAnimImporterLoaded
from .ui_properties import AnimationProperties, MeshProperties, LuniaProperties
from utils import Utils
import traceback

class LUNIA_OT_mesh_toggle_select(bpy.types.Operator):
    """Toggle selection of a mesh item"""
    bl_idname = "lunia.mesh_toggle_select"
    bl_label = "Toggle Mesh Selection"
    index: IntProperty() # type: ignore

    def invoke(self, context, event):
        props: LuniaProperties = context.scene.lunia_props
        
        if self.index < 0 or self.index >= len(props.mesh_data):
            return {'CANCELLED'}
        
        mesh: MeshProperties = props.mesh_data[self.index]

        if event.ctrl:
            # Control+Click: Toggle selection
            mesh.selected = not mesh.selected
            if mesh.selected:
                props.last_selected_mesh_index = self.index
        elif event.shift and props.last_selected_mesh_index != -1:
            # Shift+Click: Select range
            start = min(props.last_selected_mesh_index, self.index)
            end = max(props.last_selected_mesh_index, self.index)
            for i in range(start, end + 1):
                props.mesh_data[i].selected = True
        else:
            for i, item in enumerate(props.mesh_data):
                if i != self.index:
                    item.selected = False
            mesh.selected = not mesh.selected
            props.last_selected_mesh_index = self.index

        context.area.tag_redraw()
        return {'FINISHED'}

class LUNIA_UL_mesh_data(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.operator("lunia.mesh_toggle_select", text=item.name, emboss=True, depress=item.selected).index = index
        
class LUNIA_OT_anim_toggle_select(bpy.types.Operator):
    """Toggle selection of a mesh item"""
    bl_idname = "lunia.anim_toggle_select"
    bl_label = "Toggle Mesh Selection"
    index: IntProperty() # type: ignore

    def invoke(self, context, event):
        props: LuniaProperties = context.scene.lunia_props
        
        if self.index < 0 or self.index >= len(props.animation_data):
            return {'CANCELLED'}
        
        animation_data: AnimationProperties = props.animation_data[self.index]

        if event.ctrl:
            # Control+Click: Toggle selection
            animation_data.selected = not animation_data.selected
            if animation_data.selected:
                props.last_selected_anim_index = self.index
        elif event.shift and props.last_selected_anim_index != -1:
            # Shift+Click: Select range
            start = min(props.last_selected_anim_index, self.index)
            end = max(props.last_selected_anim_index, self.index)
            for i in range(start, end + 1):
                props.animation_data[i].selected = True
        else:
            for i, item in enumerate(props.animation_data):
                if i != self.index:
                    item.selected = False
            animation_data.selected = not animation_data.selected
            props.last_selected_anim_index = self.index

        context.area.tag_redraw()
        return {'FINISHED'}

class LUNIA_UL_anim_data(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.operator("lunia.anim_toggle_select", text=item.name, emboss=True, depress=item.selected).index = index

class LUNIA_OT_select_xml_file(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    bl_idname = "lunia.select_xml_file"
    bl_label = "Select XML File"
    filename_ext = ".xml"
    filter_glob: StringProperty(default="*.xml", options={'HIDDEN'}) # type: ignore

    def execute(self, context):
        context.scene.xml_file_path = self.filepath
        return {'FINISHED'}

class VIEW3D_PT_lunia_tab(bpy.types.Panel):
    bl_label = "Lunia Tools"
    bl_idname = "VIEW3D_PT_lunia_tab"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lunia Tools"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props: LuniaProperties = scene.lunia_props

        box = layout.box()
        box.label(text="XML File Selection", icon='FILE_FOLDER')
        box.operator("lunia.select_xml_file", text=scene.xml_file_path or "Select XML File")
        
        anim_header: UILayout
        anim_body: UILayout
        anim_header, anim_body = layout.panel("animation_panel")
        anim_header.label(text="Animation", icon="ANIM")
        if anim_body is not None:
            if props.animation_xml_path or props.animation_xml_name:
                
                box = anim_body.box()
                col = box.column(align=True)
                col.label(text=f"Skeleton file: {props.skeleton_file_name}")
                if props.skeleton_file_name.casefold().endswith(".skeleton"):
                    box.prop(props, "skeleton_import_debug")
                    op = box.operator(CBB_OT_SkeletonImportLoaded.bl_idname, text="Import current skeleton", icon="PLUS")
                    op.debug = props.skeleton_import_debug
                else:
                    col.label(text="No valid skeleton to import.")
                box = anim_body.box()
            
                row = box.row()
                row.template_list(
                    "LUNIA_UL_anim_data",
                    "",
                    props,
                    "animation_data",
                    props,
                    "active_animation_index",
                    rows=5
                )
                
                if any(animation.selected for animation in props.animation_data):
                    box.prop(props, "apply_to_armature_anim")
                    box.prop(props, "animation_import_debug")
                    op = box.operator(CBB_OT_SkinnedAnimImporterLoaded.bl_idname, text="Import Selected Animations", icon="PLUS")
                    op.apply_to_armature_in_selected = props.apply_to_armature_anim
                    op.debug = props.animation_import_debug
        
        mesh_header: UILayout
        mesh_body: UILayout
        mesh_header, mesh_body = layout.panel("mesh_panel")
        mesh_header.label(text="Mesh Items", icon="OBJECT_DATA")
        if mesh_body is not None:
            box = mesh_body.box()
            
            row = box.row()
            row.template_list(
                "LUNIA_UL_mesh_data",
                "",
                props,
                "mesh_data",
                props,
                "active_mesh_index",
                rows=5
            )
            
            if any(mesh.selected for mesh in props.mesh_data):
                box.prop(props, "apply_to_armature_mesh")
                box.prop(props, "mesh_import_debug")
                box.prop(props, "only_deform_bones")
                op = box.operator(CBB_OT_SkinnedMeshImportLoaded.bl_idname, text="Import Selected Meshes", icon="PLUS")
                op.apply_to_armature = props.apply_to_armature_mesh
                op.debug = props.mesh_import_debug
                op.only_deform_bones = props.only_deform_bones

        layout.prop(props, "show_debug_info")
        """
        if props.show_debug_info:
            box = layout.box()
            box.label(text="Debug Information", icon='INFO')
            for mesh_data in props.mesh_data:
                col = box.column(align=True)
                col.label(text=f"Mesh: {mesh_data.path}")
                col.label(text=f"Material: {mesh_data.material}")"""

def parse_xml_file(scene: bpy.types.Scene, context):
    """Parse the XML file and update the addon's properties"""
    
    props: LuniaProperties = scene.lunia_props
    
    # Clear existing data
    props.mesh_data.clear()
    props.animation_data.clear()
    props.animation_xml_path = ""
    props.animation_xml_name = ""
    
    xml_path = scene.xml_file_path
    if not xml_path or not xml_path.endswith('.xml'):
        return
    
    msg_handler = Utils.MessageHandler(False)
    
    try:
        # Main file parse
        if not Path(xml_path).exists():
            raise FileNotFoundError(f"XML file not found: {xml_path}")
        props.main_directory = str(Path(xml_path).parent)
        main_directory = Path(props.main_directory)
        
        root = Utils.read_xml_file(msg_handler, xml_path, f"Failed to read main xml file.")
        
        if root is None:
            return
        
        print(f"Loaded root")
        
        animation_elem = root.find(".//Animation")
        if animation_elem is not None:
            animation_value = animation_elem.get("value", "")
            if animation_value:
                animation_data = animation_value.lstrip("/").split("|")
                if len(animation_data) >= 2:
                    props.animation_xml_path = str(main_directory / animation_data[0])
                    props.animation_xml_name = animation_data[1]
        
        material_xml_file_names = set()
        mesh_data_index_by_material_name = {}
        # Mesh parsing
        for item in root.findall('.//item'):
            if item.get("type") == "Model":
                mesh_index = len(props.mesh_data)
                mesh_data: MeshProperties = props.mesh_data.add()
                
                name_elem = item.find(".//Name")
                mesh_data.name = name_elem.get("value", "") if name_elem is not None else ""
                
                mesh_path = item.find(".//Mesh")
                mesh_material = item.find(".//Material")
                
                mesh_data.mesh_path = mesh_path.get("value", "").lstrip("/") if mesh_path is not None else ""
                
                mesh_material_value = mesh_material.get("value", "") if mesh_material is not None else None
                if mesh_material_value:
                    mesh_material_data = mesh_material_value.lstrip("/").split("|")
                    if len(mesh_material_data) >= 2:
                        material_path = str(main_directory / mesh_material_data[0])
                        material_xml_file_names.add(material_path)
                        mesh_data.material_file_path = material_path
                        mesh_data.material_name = mesh_material_data[1]
                        mesh_data_index_by_material_name[mesh_material_data[1]] = mesh_index
        
        
        texture_xml_file_names = set()
        mesh_data_index_by_texture_name: dict[str, int] = {}
        
        # Material parsing
        for material_xml_file_name in material_xml_file_names:
            if material_xml_file_name != "" and Path(material_xml_file_name).exists():
                root = Utils.read_xml_file(msg_handler, material_xml_file_name, f"Failed to read material xml file.")
                if root is None:
                    continue
                
                for material in root.findall('.//material'):
                    material_name = material.get("name")
                    if material_name is None or material_name not in mesh_data_index_by_material_name.keys():
                        continue
                    
                    current_mesh_data: MeshProperties = props.mesh_data[mesh_data_index_by_material_name[material_name]]
                    
                    texture_element = material.find(".//diffuse_tex")
                    texture_value = texture_element.get("value", "").lstrip("/").split("|") if texture_element is not None else ""
                    if len(texture_value) < 2:
                        texture_path = Path(texture_value[0])
                        current_mesh_data.texture_folder = str(texture_path.parent)
                        current_mesh_data.texture_name = str(texture_path.stem)
                    else:
                        texture_xml_file_names.add(texture_value[0])
                        mesh_data_index_by_texture_name[texture_value[1]] = mesh_data_index_by_material_name[material_name]
        
        
        # Texture parsing (if any)
        for texture_xml_file_name in texture_xml_file_names:
            if texture_xml_file_name != "" and Path(texture_xml_file_name).exists():
                root = Utils.read_xml_file(msg_handler, texture_xml_file_name, f"Failed to read texture xml file.")
                if root is None:
                    continue
                for texture in root.findall('.//texture'):
                    texture_name = texture.get("name")
                    if texture_name is None:
                        continue
                    
                    if texture_name not in mesh_data_index_by_texture_name.keys():
                        continue
                    
                    current_mesh_data: MeshProperties = props.mesh_data[mesh_data_index_by_texture_name[texture_name]]
                    
                    texture_element = material.find(".//source")
                    texture_value = texture_element.get("value", "").lstrip("/")
                    texture_path = Path(texture_value[0])
                    current_mesh_data.texture_folder = str(texture_path.parent)
                    current_mesh_data.texture_name = str(texture_path.stem)
        
             
        # Animation parsing
        if props.animation_xml_path != "" and Path(props.animation_xml_path).exists():
            root = Utils.read_xml_file(msg_handler, props.animation_xml_path, f"Failed to read animation xml file.")
            if root is None:
                return
            animation_elem = root.find(".//animation")
            if animation_elem is not None and animation_elem.get("name") is not None and animation_elem.get("name") == props.animation_xml_name:
                props.skeleton_file_name = animation_elem.find(".//skeleton").get("value", "").lstrip("/") if animation_elem.find(".//skeleton") is not None else ""
            
            for clip in animation_elem.findall('.//clip'):
                anim_data: AnimationProperties = props.animation_data.add()
                
                anim_data.name = clip.get("name", "")
                
                anim_file = clip.find(".//file")
                anim_data.animation_file_path = anim_file.get("value", "").lstrip("/") if anim_file is not None else ""
        
        
    except Exception as e:
        print(f"Error parsing XML: {e}")
        traceback.print_exc()
        

classes = (
    VIEW3D_PT_lunia_tab,
    LUNIA_UL_mesh_data,
    LUNIA_OT_mesh_toggle_select,
    LUNIA_OT_anim_toggle_select,
    LUNIA_UL_anim_data,
    LUNIA_OT_select_xml_file,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.lunia_props = PointerProperty(type=LuniaProperties)
    bpy.types.Scene.xml_file_path = StringProperty(
        name="XML File Path",
        description="Path to the XML file containing animation data",
        subtype='FILE_PATH',
        update=parse_xml_file
    )

def unregister():
    for prop in ("xml_file_path", "lunia_props"):
        if hasattr(bpy.types.Scene, prop):
            delattr(bpy.types.Scene, prop)
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()