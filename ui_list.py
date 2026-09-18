"""
Kimodo Blender Bridge — UIList
Custom UILists for the addon panels.
"""

import bpy
from bpy.types import UIList


class KIMODO_UL_History(UIList):
    """Draws each history entry: timestamp, truncated prompt, seed, duration, file check."""

    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index):
        if self.layout_type not in {'DEFAULT', 'COMPACT'}:
            layout.label(text="", icon='TIME')
            return

        import os
        row = layout.row(align=True)
        ts_short = item.timestamp[-8:] if len(item.timestamp) >= 8 else item.timestamp
        row.label(text=ts_short, icon='TIME')
        prompt_preview = item.prompt[:48] + ("…" if len(item.prompt) > 48 else "")
        row.label(text=prompt_preview)
        # Compact stats hug the right so the prompt gets the leftover width
        stats = row.row(align=True)
        stats.alignment = 'RIGHT'
        # "…" marks multi-segment entries: all seeds are in the detail view
        seed_txt = str(item.seed) + ("…" if "," in item.seeds else "")
        stats.label(text=seed_txt)
        stats.label(text=f"{item.duration:.1f}s")
        stats.label(text="", icon='CHECKMARK' if os.path.isfile(item.bvh_path) else 'ERROR')


def register():
    bpy.utils.register_class(KIMODO_UL_History)


def unregister():
    bpy.utils.unregister_class(KIMODO_UL_History)
