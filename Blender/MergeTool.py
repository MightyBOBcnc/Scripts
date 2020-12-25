# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

import bpy
import bgl
import gpu
import bmesh
import math
import os
from gpu_extras.batch import batch_for_shader

bl_info = {
    "name": "Merge Tool",
    "category": "Mesh",
    "author": "Andreas Strømberg, Chris Kohl",
    "wiki_url": "https://github.com/Stromberg90/Scripts/tree/master/Blender",
    "tracker_url": "https://github.com/Stromberg90/Scripts/issues",
    "blender": (2, 80, 0),
    "version": (1, 1, 1)
}

# ToDo:
# Is there a way to get the previous active tool so we can potentially restore it when we cancel or are done?  That is something that *might* be needed?

icon_dir = os.path.join(os.path.dirname(__file__), "icons")

def draw_callback_px(self, context):
    if self.started and self.start_vertex is not None and self.end_vertex is not None:
        bgl.glEnable(bgl.GL_BLEND)
        coords = [self.start_vertex_transformed, self.end_vertex_transformed]
        shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": coords})
        shader.bind()
        shader.uniform_float("color", (1, 0, 0, 1))
        batch.draw(shader)

        shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'POINTS', {"pos": coords})
        shader.bind()
        shader.uniform_float("color", (1, 0, 0, 1))
        batch.draw(shader)

        bgl.glLineWidth(1)
        bgl.glDisable(bgl.GL_BLEND)


def main(self, context, event):
    """Run this function on left mouse, execute the ray cast"""
    coord = event.mouse_region_x, event.mouse_region_y

    if self.started:
        result = bpy.ops.view3d.select(extend=True, location=coord)
    else:
        result = bpy.ops.view3d.select(extend=False, location=coord)

    print("Result is:", result)  # Delete me later
    if result == {'PASS_THROUGH'}:
        bpy.ops.mesh.select_all(action='DESELECT')
#    if 'FINISHED' in result:
#        print("Butt")
#        self.started = True


class MergeTool(bpy.types.Operator):
    """Modal object selection with a ray cast"""
    bl_idname = "mesh.merge_tool"
    bl_label = "Merge Tool"
    bl_options = {'REGISTER', 'UNDO'}

    merge_mode: bpy.props.EnumProperty(
        name="Mode",
        description="Merge mode",
        items=[('VERT', "Vertex", "Tool will merge vertices", 'MERGE_VERTS', 1),
               ('EDGE', "Edge", "Tool will merge edges", 'MERGE_EDGES', 2)
               ],
        default='VERT'
    )

    merge_location: bpy.props.EnumProperty(
        name="Location",
        description="Merge location",
        items=[('TARGET', "Target", "Components will be merged at the target's location", 'LOC_TARGET', 1),
               ('CENTER', "Center", "Components will be merged at the averaged center between the two", 'LOC_CENTER', 2)
               ],
        default='TARGET'
    )

    def __init__(self):
        print("This happens first")  # Delete me later
        self.start_vertex = None
        self.end_vertex = None
        self.started = False
        self._handle = None

    def modal(self, context, event):
        context.area.tag_redraw()
        
#        self.started = True  # Delete me later if this doesn't work?
#        main(context, event, self.started)  # Delete me later if this doesn't work?

#        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
        if event.alt or event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            # allow navigation (event.alt allows for using Industry Compatible keymap navigation)
            return {'PASS_THROUGH'}
        elif event.type == 'MOUSEMOVE':
            if self.started:
                coord = event.mouse_region_x, event.mouse_region_y
                bpy.ops.view3d.select(extend=False, location=coord)
                print("Running view3d.select")  # Delete me later (this runs A LOT)

                selected_vertex = None
                for v in self.bm.verts:
                    if v.select:
                        selected_vertex = v
                        break

                if selected_vertex:
                    self.end_vertex = selected_vertex
                    self.end_vertex_transformed = self.world_matrix @ self.end_vertex.co
        elif event.type == 'LEFTMOUSE':
            main(self, context, event)
            if not self.started:
#            if not self.started and event.value == 'PRESS':
                if context.object.data.total_vert_sel == 1:  # Consider trying to make this work with the selection history instead of iterating over every vertex in the bmesh
                    selected_vertex = None
                    for v in self.bm.verts:
                        if v.select:
                            selected_vertex = v
                            break

                    if selected_vertex:
                        self.start_vertex = selected_vertex
                        self.start_vertex_transformed = self.world_matrix @ self.start_vertex.co
                    else:
                        bpy.types.SpaceView3D.draw_handler_remove(
                            self._handle, 'WINDOW')
                        return {'CANCELLED'}
                    self.started = True
            elif self.start_vertex is self.end_vertex:
                bpy.types.SpaceView3D.draw_handler_remove(
                    self._handle, 'WINDOW')
                context.workspace.status_text_set(None)
                return {'CANCELLED'}
            elif self.start_vertex is not None and self.end_vertex is not None:
                self.start_vertex.select = True
                self.end_vertex.select = True
                try:
                    bpy.ops.mesh.merge(type='LAST')
                    bpy.ops.ed.undo_push(
                        message="Merge Tool undo step")
                except TypeError:
                    pass
                finally:
                    self.start_vertex = None
                    self.end_vertex = None
                    self.started = False
            else:
                bpy.types.SpaceView3D.draw_handler_remove(
                    self._handle, 'WINDOW')
                context.workspace.status_text_set(None)
                return {'CANCELLED'}
            return {'RUNNING_MODAL'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            print("Cancelled")  # Delete me later
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')  # Probably comment this out as well?!  Somehow this needs to be removed when we leave the tool?  Or, rather maybe this should be removed automatically when "done" with a merge, or on pass_through?  ALSO at the moment no other keys work to exit the tool (not does the mouse).. so, like, there needs to be a 'if event is NOT in the events we care about and is not navigation, then pass through and return cancelled so we can switch to other tools?'
            context.workspace.status_text_set(None)  # Comment this out when we fix the tool to never be 'inactive'
#            self.start_vertex = None  # Uncomment me
#            self.end_vertex = None  # Uncomment me
            return {'CANCELLED'}  # Basically the idea is that to keep the tool going we have to replace most if not all instances of returning cancelled with reseting start_vertex, end_vertex, self.started and returning 'running modal' again.
            # In other words, "cancelling" is really just resetting to the starting state so there isn't an active vert and active drawing a red vert and red line so we can start over with a different selection.

        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        if context.space_data.type == 'VIEW_3D':
            context.workspace.status_text_set(
                "Left click and drag to merge vertices, Esc or right click to cancel")

            self.start_vertex = None
            self.end_vertex = None
            self.started = False
            self.me = bpy.context.object.data
            self.world_matrix = bpy.context.object.matrix_world
            self.bm = bmesh.from_edit_mesh(self.me)

            args = (self, context)
            self._handle = bpy.types.SpaceView3D.draw_handler_add(
                draw_callback_px, args, 'WINDOW', 'POST_VIEW')

            context.window_manager.modal_handler_add(self)
#            main(self, context, event)  # Delete me later if this doesn't work?

            print("Invoke called, it wants its joke back")
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "Active space must be a View3d")
            return {'CANCELLED'}


class ToolMergeTool(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'

    bl_idname = "mesh_tool.merge_tool"
    bl_label = "Merge Tool"
    bl_description = "Interactively merge vertices with the Merge Tool"
    bl_icon = os.path.join(icon_dir, "ops.mesh.merge_tool")
    bl_widget = None
#    bl_operator = "mesh.merge_tool('INVOKE_DEFAULT')"
    bl_keymap = (
        ("mesh.merge_tool", {"type": 'LEFTMOUSE', "value": 'PRESS'},
         {"properties": []}),
    )

    def draw_settings(context, layout, tool):
        tool_props = tool.operator_properties("mesh.merge_tool")

        row = layout.row()
        row.use_property_split = False
        row.prop(tool_props, "merge_mode", text="Mode")
        row.prop(tool_props, "merge_location", text="Location")


def register():
    bpy.utils.register_class(MergeTool)
    bpy.utils.register_tool(ToolMergeTool, after={"builtin.measure"}, separator=True, group=False)


def unregister():
    bpy.utils.unregister_class(MergeTool)
    bpy.utils.unregister_tool(ToolMergeTool)


if __name__ == "__main__":
    register()
