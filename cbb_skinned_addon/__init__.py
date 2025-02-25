bl_info = {
    "name": "SkinnedMesh, Skeleton, and SkinnedAnim formats",
    "blender": (4, 1, 0),
    "category": "Import-Export",
    "version": (0, 3, 1),
    "description": "Importer-exporter for SkinnedMesh, Skeleton, and SkinnedAnim files.",
    "author": "Cardboard Box",
    "location": "File > Import-Export",
    "warning": "",
    "doc_url": "",
    "tracker_url": "",
}

import sys
import os
addon_dir = os.path.dirname(__file__)
shared_dir = os.path.abspath(os.path.join(addon_dir, '..', 'shared'))
if shared_dir not in sys.path:
    sys.path.append(shared_dir)
import utils

from .operators import mesh_operators
from .operators import skeleton_operators
from .operators import animation_operators
from .ui import custom_panel
from .ui import ui_properties


def register():
    mesh_operators.register()
    skeleton_operators.register()
    animation_operators.register()
    utils.register()
    ui_properties.register()
    custom_panel.register()
    

def unregister():
    mesh_operators.unregister()
    skeleton_operators.unregister()
    animation_operators.unregister()
    utils.unregister()
    custom_panel.unregister()
    ui_properties.unregister()

if __name__ == "__main__":
    register()
