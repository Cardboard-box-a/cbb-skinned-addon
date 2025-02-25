import bpy
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.types import Context, Event, Operator
from bpy.props import CollectionProperty, StringProperty, BoolProperty
from bpy_extras.io_utils import ImportHelper
from mathutils import Vector
import traceback
from utils import Utils, CoordsSys
Serializer = Utils.Serializer
CoordinatesConverter = Utils.CoordinatesConverter
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from ..core.mesh_core import import_skinnedmesh
from ..core.skeleton_core import SkeletonData
from ..ui.ui_properties import LuniaProperties

class CBB_OT_SkinnedMeshImporter(Operator, ImportHelper):
    bl_idname = "cbb.skinnedmesh_import"
    bl_label = "Import SkinnedMesh"
    bl_options = {"PRESET", "UNDO"}

    filename_ext = ".SkinnedMesh"

    filter_glob: StringProperty(default=f"*{filename_ext}",options={"HIDDEN"}) # type: ignore

    files: CollectionProperty(
        type=bpy.types.OperatorFileListElement,
        options={"HIDDEN", "SKIP_SAVE"}
    ) # type: ignore

    directory: StringProperty(subtype="DIR_PATH") # type: ignore

    apply_to_armature_in_selected: BoolProperty(
        name="Apply to armature in selected",
        description="Enabling this option will make the import of the animation to target any armature present between currently selected objects.",
        default=False
    ) # type: ignore

    debug: BoolProperty(
        name="Debug import",
        description="Enabling this option will make the importer print debug data to console.",
        default=False
    ) # type: ignore
    
    only_deform_bones: BoolProperty(
        name="Consider only deform bones (Recommended)",
        description="Leave this option checked if you wish to consider only deform bones in armatures. Recommended in case you are using rigged armatures that have non-deforming bones",
        default=True
    ) # type: ignore

    
    def execute(self, context):
        return_value = {"CANCELLED"}
        for file in self.files:
            result = import_skinnedmesh(self.debug, file.name, self.directory, self.apply_to_armature_in_selected, self.only_deform_bones, operator=self)
            if result == {"FINISHED"}:
                return_value = {"FINISHED"}
        return return_value


    def invoke(self, context: Context, event: Event):
        if self.directory:
            return context.window_manager.invoke_props_dialog(self)
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}
    
class CBB_OT_SkinnedMeshImportLoaded(bpy.types.Operator):
    bl_idname = "cbb.skinnedmesh_import_from_panel"
    bl_label = "Import Selected SkinnedMesh"
    bl_options = {"UNDO"}
    
    apply_to_armature: BoolProperty(name="Apply to Armature in Selected Objects", default=False) # type: ignore
    debug: BoolProperty(name="Debug", default=False) # type: ignore
    only_deform_bones: BoolProperty(name="Only Deform Bones", default=True) # type: ignore

    def execute(self, context):
        props: LuniaProperties = context.scene.lunia_props
        
        return_value = {"CANCELLED"}
        for mesh_data in props.mesh_data:
            mesh_data.name
            if mesh_data.selected == False:
                continue
            result = import_skinnedmesh(self.debug, mesh_data.mesh_path, props.main_directory, self.apply_to_armature, self.only_deform_bones, str(Path(props.skeleton_file_name).stem), mesh_data.texture_folder, mesh_data.texture_name, self)
            if result == {"FINISHED"}:
                return_value = {"FINISHED"}
                
        return return_value

class CBB_FH_SkinnedMeshImporter(bpy.types.FileHandler):
    bl_idname = "CBB_FH_skinnedmesh_import"
    bl_label = "File handler for skinnedmesh imports"
    bl_import_operator = CBB_OT_SkinnedMeshImporter.bl_idname
    bl_file_extensions = CBB_OT_SkinnedMeshImporter.filename_ext

    @classmethod
    def poll_drop(cls, context):
        return (context.area and context.area.type == "VIEW_3D")

class CBB_OT_SkinnedMeshExporter(Operator, ExportHelper):
    bl_idname = "cbb.skinnedmesh_export"
    bl_label = "Export SkinnedMesh"
    bl_options = {"PRESET"}

    filename_ext = CBB_OT_SkinnedMeshImporter.filename_ext
    
    filter_glob: StringProperty(default=f"*{filename_ext}",options={"HIDDEN"}) # type: ignore

    directory: StringProperty(
        name="Directory",
        description="Directory to export files to",
        subtype="DIR_PATH",
        default=""
    ) # type: ignore

    debug: BoolProperty(
        name="Debug export",
        description="Enabling this option will make the exporter print debug data to console",
        default=False
    ) # type: ignore
    
    export_only_selected: BoolProperty(
        name="Export only selected",
        description="Leave this option checked if you wish export only meshes among currently selected objects",
        default=False
    ) # type: ignore
    
    only_deform_bones: BoolProperty(
        name="Consider only deform bones (Recommended)",
        description="Leave this option checked if you wish to consider only deform bones in armatures",
        default=True
    ) # type: ignore

    def execute(self, context):
        return self.export_skinnedmeshes(context, self.directory)

    def export_skinnedmeshes(self, context, directory):
        objects_for_exportation = None
        if self.export_only_selected == True:
            objects_for_exportation = [obj for obj in context.selected_objects if obj.type == "MESH"]
        else:
            objects_for_exportation = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]

        if not objects_for_exportation:
            if self.export_only_selected == True:
                self.report({"ERROR"}, f"There are no objects of type MESH among currently selected objects. Aborting exportation.")
            else:
                self.report({"ERROR"}, f"There are no objects of type MESH among scene objects. Aborting exportation.")
            return {"CANCELLED"}
        
        msg_handler = Utils.MessageHandler(self.debug, self.report)
        
        for scene_mesh in objects_for_exportation:
            def export_skinnedmesh(mesh_object: bpy.types.Object):
                try:
                    filepath = (Path(directory) / mesh_object.name).with_suffix(self.filename_ext)
                    
                    msg_handler.debug_print(f"Exporting mesh [{mesh_object.name}] to file at [{filepath}]")

                    mesh_armature: bpy.types.Armature = None
                    mesh_modifier = None
                    for mod in mesh_object.modifiers:
                        if mod.type == "ARMATURE":
                            if mesh_modifier is None:
                                mesh_modifier = mod
                                if mod.object is not None:
                                    mesh_armature = mod.object
                                else:
                                    self.report({"ERROR"}, f"Object [{mesh_object.name}] has it's armature modifier without a target armature. Aborting this exportation.")
                                    return
                            else:
                                self.report({"ERROR"}, f"Object [{mesh_object.name}] has more than one armature modifier. Aborting this exportation.")
                                return

                    
                    if mesh_modifier is None:
                        self.report({"ERROR"}, f"Object [{mesh_object.name}] has no armature modifier. Aborting this exportation.")
                        return
                    
                    skeleton_data = SkeletonData.build_skeleton_from_armature(mesh_armature, self.only_deform_bones, True, msg_handler)
                    if skeleton_data is None:
                        self.report({"ERROR"}, f"Armature [{mesh_armature.name}], target of [{mesh_object.name}], was found not valid. Aborting this exportation.")
                        return
                        
                    mesh = mesh_object.data
                    vertices = mesh.vertices
                    polygons = mesh.polygons
                    loops = mesh.loops
                    uvs = mesh.uv_layers.active.data if mesh.uv_layers.active else None

                    msg_handler.debug_print(f"Object [{mesh_object.name}]'s vertex amount: [{len(vertices)}]")
                    msg_handler.debug_print(f"Object [{mesh_object.name}]'s polygon amount: [{len(polygons)}]")
                    msg_handler.debug_print(f"Object [{mesh_object.name}]'s loop amount: [{len(loops)}]")
                    msg_handler.debug_print(f"Object [{mesh_object.name}]'s uv amount: [{len(uvs)}]")

                    if len(vertices) > 65536:
                        self.report({"ERROR"}, f"Error while exporting mesh [{mesh_object.name}]: mesh has more than 65536 vertices. The .SkinnedMesh file type can't work with more than this quantity.")
                        return

                    # Step 1: Get original vertices
                    original_vertices: list[Vector] = [v.co for v in vertices]

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
                    exporter_vertices: list[Vector] = []
                    exporter_normals: list[Vector] = []
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
                                bone_id = skeleton_data.bone_name_to_id.get(bone_name, 0)
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

                    msg_handler.debug_print(f"Object [{mesh_object.name}]'s vertex amount for export: [{len(exporter_vertices)}]")
                    msg_handler.debug_print(f"Object [{mesh_object.name}]'s polygon amount for export: [{len(new_polygons)}]")

                    if len(exporter_vertices) > 65536:
                        self.report({"ERROR"}, f"Error while exporting mesh [{mesh_object.name}]: mesh has {len(exporter_vertices)} vertices after vertex remapping, which is more than 65536 vertices.\nThis issue can be caused by the mesh's uv map having duplicate entries for each vertex. Consider remapping the mesh's UV map as a single continuous map or reduce the total amount of vertices.")
                        return
                except Exception as e:
                    self.report({"ERROR"}, f"Exception while trying to remap vertices for object [{mesh_object.name}]: {e}")
                    traceback.print_exc()
                    return
                try:
                    co_conv = CoordinatesConverter(CoordsSys.Blender, CoordsSys.Unity)
                    # Write to file
                    with open(filepath, "wb") as opened_file:
                        writer = Serializer(opened_file, Serializer.Endianness.Little, Serializer.Quaternion_Order.XYZW, Serializer.Matrix_Order.RowMajor, co_conv)
                        try:
                            
                            # 1. Write the length in characters of the name of the object (including null terminator)
                            name_length = len(mesh_object.name) + 1
                            writer.write_uint(name_length)

                            # 2. The name of the object as a Unicode string
                            writer.write_fixed_string(name_length*2, "utf-16-le", mesh_object.name)

                            # 3. The amount of vertices in the mesh as an integer
                            vertex_count = len(exporter_vertices)
                            writer.write_uint(vertex_count)

                            # 4. The amount of triangles in the mesh as an integer
                            triangle_count = sum(len(poly) - 2 for poly in new_polygons)
                            writer.write_uint(triangle_count*3)

                            # 5. Write five consecutive integers: 1, 1, 0, 1, 1
                            writer.write_uint(1)
                            writer.write_uint(1)
                            writer.write_uint(0)
                            writer.write_uint(1)
                            writer.write_uint(1)

                            # 6. The amount of triangles in the mesh as an integer again
                            writer.write_uint(triangle_count*3)

                            # 7. All the indices that make all the triangles in the mesh
                            for poly in new_polygons:
                                if len(poly) == 3:
                                    writer.write_values("3H", poly)
                                elif len(poly) == 4:
                                    # If the polygon is a quad, split it into two triangles
                                    writer.write_values("3H", (poly[0], poly[1], poly[2]))
                                    writer.write_values("3H", (poly[0], poly[2], poly[3]))
                                else:
                                    # Handle polygons with more than 4 vertices (n-gons)
                                    v0 = poly[0]
                                    for i in range(1, len(poly) - 1):
                                        writer.write_values("3H", (v0, poly[i], poly[i + 1]))

                            # 8. The amount of vertices in the mesh as an integer again
                            writer.write_uint(vertex_count)

                            # 9. All the vertices in the mesh (position: float, float, float)
                            for vertex in exporter_vertices:
                                writer.write_converted_vector3f(vertex)

                            # 10. The amount of normals in the mesh (same as vertices)
                            writer.write_uint(vertex_count)

                            # 11. All the normals in the mesh
                            for normal in exporter_normals:
                                writer.write_converted_vector3f(normal)

                            # 12. The amount of UV coordinates in the mesh (same as vertices)
                            writer.write_uint(vertex_count)

                            # 13. All UV coordinates of the mesh
                            for uv in exporter_uvs:
                                writer.write_values("2f", (uv[0], -uv[1]))

                            # 14. The amount of weights in the mesh (same as vertices)
                            writer.write_uint(vertex_count)

                            # 15. All the weights for each vertex
                            for groups_count, bone_count, bone_indices, weight_count, weights in exporter_weights:
                                writer.write_uint(groups_count)
                                writer.write_uint(bone_count)
                                writer.write_values(f"{bone_count}I", bone_indices)
                                writer.write_uint(weight_count)
                                writer.write_values(f"{weight_count}f", weights)
                                
                        except Exception as e:
                            opened_file.close()
                            os.remove(filepath)
                            self.report({"ERROR"}, f"Exception while writing to file at [{filepath}]: {e}")
                            traceback.print_exc()
                            return
                except Exception as e:
                    self.report({"ERROR"}, f"Could not open file for writing at [{filepath}]: {e}")
                    traceback.print_exc()
                    return

            export_skinnedmesh(scene_mesh)

        return {"FINISHED"}

def menu_func_import(self, context):
    self.layout.operator(CBB_OT_SkinnedMeshImporter.bl_idname, text="SkinnedMesh (.SkinnedMesh)")

def menu_func_export(self, context):
    self.layout.operator(CBB_OT_SkinnedMeshExporter.bl_idname, text="SkinnedMesh (.SkinnedMesh)")

classes = (
    CBB_OT_SkinnedMeshImporter,
    CBB_OT_SkinnedMeshImportLoaded,
    CBB_FH_SkinnedMeshImporter,
    CBB_OT_SkinnedMeshExporter,
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
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_export)

if __name__ == "__main__":
    register()
