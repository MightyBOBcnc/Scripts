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

bl_info = {
    "name": "Merge Tool",
    "description": "An interactive tool for merging vertices.",
    "author": "Andreas Strømberg, Chris Kohl",
    "version": (1, 1, 3),
    "blender": (2, 83, 0),  # Minimum version might have to be 2.83 due to changes in tool registration in that version that are different from before?
    "location": "View3D > TOOLS > Merge Tool",
    "warning": "Dev Branch. Somewhat experimental features. Possible performance issues.",
    "wiki_url": "https://github.com/MightyBOBcnc/Scripts/tree/Loopanar-Hybrid/Blender",
    "tracker_url": "https://github.com/MightyBOBcnc/Scripts/issues",
    "category": "Mesh"
}

import bpy
import bgl
import gpu
import bmesh
import math
import os
from gpu_extras.presets import draw_circle_2d
from gpu_extras.batch import batch_for_shader

icon_dir = os.path.join(os.path.dirname(__file__), "icons")

def draw_callback_3d(self, context):
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


def draw_callback_2d(self, context):
    bgl.glEnable(bgl.GL_BLEND)

    circ_loc = self.m_coord
    circ_color = (1, 1, 1, 1)
    circ_radius = 12
    circ_segments = 8 + 1
    draw_circle_2d(self.m_coord, circ_color, circ_radius, circ_segments)

    bgl.glLineWidth(1)
    bgl.glDisable(bgl.GL_BLEND)


def main(self, context, event):
    """Run this function on left mouse, execute the ray cast"""
    self.m_coord = event.mouse_region_x, event.mouse_region_y

    if self.started:
        result = bpy.ops.view3d.select(extend=True, location=self.m_coord)
    else:
        result = bpy.ops.view3d.select(extend=False, location=self.m_coord)

    print("Result is:", result)  # Delete me later
    if result == {'PASS_THROUGH'}:
        bpy.ops.mesh.select_all(action='DESELECT')
#    if 'FINISHED' not in result:
#        print("Butt")


class MergeTool(bpy.types.Operator):
    """Modal object selection with a ray cast"""
    bl_idname = "mesh.merge_tool"
    bl_label = "Merge Tool"
    bl_options = {'REGISTER', 'UNDO'}  # We probably don't need the REGISTER.

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
        items=[('LAST', "Last", "Components will be merged at the target's location", 1),
               ('CENTER', "Center", "Components will be merged at the averaged center between the two", 2)
               ],
        default='LAST'
    )

    def __init__(self):
        print("========This happens first========")  # Delete me later
        self.start_vertex = None
        self.end_vertex = None
        self.started = False
        self._handle3d = None
        self._handle2d = None


    def remove_handles(self, context):
        bpy.types.SpaceView3D.draw_handler_remove(self._handle3d, 'WINDOW')
        bpy.types.SpaceView3D.draw_handler_remove(self._handle2d, 'WINDOW')


    def modal(self, context, event):
        context.area.tag_redraw()

        if event.alt or event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            # allow navigation (event.alt allows for using Industry Compatible keymap navigation)
            return {'PASS_THROUGH'}
        elif event.type == 'MOUSEMOVE':
            if self.started:
                self.m_coord = event.mouse_region_x, event.mouse_region_y
                bpy.ops.view3d.select(extend=False, location=self.m_coord)
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
                if context.object.data.total_vert_sel == 1:
                    selected_vertex = None
                    for v in self.bm.verts:  # Consider trying to make this work with the selection history instead of iterating over every vertex in the bmesh
                        if v.select:
                            selected_vertex = v
                            break

                    if selected_vertex:
                        self.start_vertex = selected_vertex
                        self.start_vertex_transformed = self.world_matrix @ self.start_vertex.co
                    else:
                        self.remove_handles(context)
                        print("Nope, cancelled.")  # Delete me later
                        return {'CANCELLED'}
                    self.started = True
                    print("We're in here and are started.")
            elif self.start_vertex is self.end_vertex:
                self.remove_handles(context)
                context.workspace.status_text_set(None)
                print("Cancelled for lack of anything to do.")  # Delete me later
                return {'CANCELLED'}
            elif self.start_vertex is not None and self.end_vertex is not None:
                self.start_vertex.select = True
                self.end_vertex.select = True
                try:
                    bpy.ops.mesh.merge(type=self.merge_location)
#                    bpy.ops.ed.undo_push(
#                        message="Merge Tool undo step")  # We may not even need the undo step if all we are doing is running a merge?  (Perhaps if the merge fails this is good to prevent undoing a step farther than the user wants?)
                except TypeError:
                    print("That failed for some reason.")
                    pass
                finally:
                    self.start_vertex = None
                    self.end_vertex = None
                    self.started = False
                    self.remove_handles(context)
                    context.workspace.status_text_set(None)
                    return {'FINISHED'}
            else:
                self.remove_handles(context)
                context.workspace.status_text_set(None)
                print("End of line; cancelled.")  # Delete me later
                return {'CANCELLED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            print("Cancelled")  # Delete me later
            self.remove_handles(context)
            context.workspace.status_text_set(None)
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        # Checks if we are in face selection mode.
        if context.tool_settings.mesh_select_mode[2]:
            return {'CANCELLED'}
        # Checks if we are in edge selection mode.
        if context.tool_settings.mesh_select_mode[1]:
            return {'CANCELLED'}
        if context.space_data.type == 'VIEW_3D':
            context.workspace.status_text_set(
                "Left click and drag to merge vertices, Esc or right click to cancel")

            self.start_vertex = None
            self.end_vertex = None
            self.started = False

            main(self, context, event)  #This goes up here or else there will be a hard crash; probably one of the "gotchas" related to memory pointers.

            if context.object.data.total_vert_sel == 0:
                context.workspace.status_text_set(None)
                print("Pls no break.")  # Delete me later
                return {'CANCELLED'}
            
            self.me = bpy.context.object.data
            self.world_matrix = bpy.context.object.matrix_world
            self.bm = bmesh.from_edit_mesh(self.me)

            args = (self, context)
            self._handle3d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_3d, args, 'WINDOW', 'POST_VIEW')
            self._handle2d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_2d, args, 'WINDOW', 'POST_PIXEL')

            context.window_manager.modal_handler_add(self)
            if not self.started:
                if context.object.data.total_vert_sel == 1:
                    selected_vertex = None
                    for v in self.bm.verts:  # Consider trying to make this work with the selection history instead of iterating over every vertex in the bmesh
                        if v.select:
                            selected_vertex = v
                            break

                    if selected_vertex:
                        self.start_vertex = selected_vertex
                        self.start_vertex_transformed = self.world_matrix @ self.start_vertex.co
                    else:
                        self.remove_handles(context)
                        print("Nope, cancelled.")  # Delete me later
                        return {'CANCELLED'}
                    self.started = True


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
    bl_cursor = 'PAINT_CROSS'
    bl_widget = None
    bl_keymap = (
        ("mesh.merge_tool", {"type": 'LEFTMOUSE', "value": 'PRESS'},
         {"properties": []}),
    )

    def draw_settings(context, layout, tool):
        tool_props = tool.operator_properties("mesh.merge_tool")

        row = layout.row()
        row.use_property_split = False
#        row.prop(tool_props, "merge_mode", text="Mode")
        row.prop(tool_props, "merge_location", text="Location")


def register():
    bpy.utils.register_class(MergeTool)
    bpy.utils.register_tool(ToolMergeTool, after={"builtin.measure"}, separator=True, group=False)


def unregister():
    bpy.utils.unregister_class(MergeTool)
    bpy.utils.unregister_tool(ToolMergeTool)


if __name__ == "__main__":
    register()
