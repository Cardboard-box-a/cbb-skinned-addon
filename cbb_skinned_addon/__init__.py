bl_info = {
    "name": "SkinnedMesh, Skeleton, and SkinnedAnim formats",
    "blender": (4, 1, 0),
    "category": "Import-Export",
    "version": (0, 1, 3),
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
import import_utils

from . import skinnedmesh
from . import skeleton
from . import skinnedanim





def register():
    skinnedmesh.register()
    skeleton.register()
    skinnedanim.register()
    import_utils.register()

def unregister():
    skinnedmesh.unregister()
    skeleton.unregister()
    skinnedanim.unregister()
    import_utils.unregister()

if __name__ == "__main__":
    register()
