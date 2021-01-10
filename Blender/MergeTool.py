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
    "version": (1, 1, 6),
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
import os
from gpu_extras.presets import draw_circle_2d
from gpu_extras.batch import batch_for_shader
from bpy.props import (
    EnumProperty,
    StringProperty,
    BoolProperty,
    IntProperty,
    FloatVectorProperty,
    FloatProperty,
    )

icon_dir = os.path.join(os.path.dirname(__file__), "icons")

classes = []

class MergeToolPreferences(bpy.types.AddonPreferences):
    # this must match the addon __name__
    # use '__package__' when defining this in a submodule of a python package.
    bl_idname = __name__

    show_circ: BoolProperty(name="Show Circle",
        description="Show the circle cursor",
        default=True)

    point_size: FloatProperty(name="Point Size",
        description="Size of highlighted vertices",
        default=6.0,
        min=3.0,
        max=10.0,
        step=1,
        precision=2)

    edge_width: FloatProperty(name="Edge Width",
        description="Width of highlighted edges",
        default=2.5,
        min=1.0,
        max=10.0,
        step=1,
        precision=2)

    line_width: FloatProperty(name="Line Width",
        description="Width of the connecting line",
        default=2.0,
        min=1.0,
        max=10.0,
        step=1,
        precision=2)

    circ_radius: FloatProperty(name="Circle Size",
        description="Size of the circle cursor (VISUAL ONLY)",
        default=12.0,
        min=6.0,
        max=100,
        step=1,
        precision=2)

    start_color: FloatVectorProperty(name="Starting Color",
        default=(0.6, 0.0, 1.0, 1.0),
        size=4,
        subtype="COLOR",
        min=0,
        max=1)

    end_color: FloatVectorProperty(name="Ending Color",
        default=(0.2, 1.0, 0.3, 1.0),
        size=4,
        subtype="COLOR",
        min=0,
        max=1)

    line_color: FloatVectorProperty(name="Line Color",
        default=(1.0, 0.0, 0.0, 1.0),
        size=4,
        subtype="COLOR",
        min=0,
        max=1)

    circ_color: FloatVectorProperty(name="Circle Color",
        default=(1.0, 1.0, 1.0, 1.0),
        size=4,
        subtype="COLOR",
        min=0,
        max=1)

    def draw(self, context):
        layout = self.layout

        layout.prop(self, "show_circ")

        layout.use_property_split = True
        nums = layout.grid_flow(row_major=False, columns=0, even_columns=True, even_rows=False, align=False)

        nums.prop(self, "point_size")
        nums.prop(self, "edge_width")
        nums.prop(self, "line_width")
#        nums.prop(self, "circ_radius")

        colors = layout.grid_flow(row_major=False, columns=0, even_columns=True, even_rows=False, align=False)
        colors.prop(self, "start_color")
        colors.prop(self, "end_color")
        colors.prop(self, "line_color")
        colors.prop(self, "circ_color")
classes.append(MergeToolPreferences)


def draw_callback_3d(self, context):
    if self.started:
        if self.start_comp is not None and self.end_comp is not None:
            bgl.glEnable(bgl.GL_BLEND)
            bgl.glLineWidth(self.prefs.line_width)
            bgl.glPointSize(self.prefs.point_size)
            coords = [self.start_comp_transformed, self.end_comp_transformed]

            # Line that connects the start and end position (draw first so it's beneath the vertices)
            shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
            batch = batch_for_shader(shader, 'LINES', {"pos": coords})
            shader.bind()
            shader.uniform_float("color", self.prefs.line_color)
            batch.draw(shader)

            # Ending point
            if self.end_comp != self.start_comp:
                shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
                batch = batch_for_shader(shader, 'POINTS', {"pos": [self.end_comp_transformed]})
                shader.bind()
                shader.uniform_float("color", self.prefs.end_color)
                batch.draw(shader)

            bgl.glLineWidth(1)
            bgl.glPointSize(1)
            bgl.glDisable(bgl.GL_BLEND)

        # Starting point
        if self.start_comp is not None:
            bgl.glEnable(bgl.GL_BLEND)
            bgl.glPointSize(self.prefs.point_size)

            shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
            batch = batch_for_shader(shader, 'POINTS', {"pos": [self.start_comp_transformed]})
            shader.bind()
            shader.uniform_float("color", self.prefs.start_color)
            batch.draw(shader)

#            bgl.glLineWidth(1)
            bgl.glPointSize(1)
            bgl.glDisable(bgl.GL_BLEND)


def draw_callback_2d(self, context):
    bgl.glEnable(bgl.GL_BLEND)

    circ_segments = 8 + 1  # Have to add 1 for some reason in order to get proper number of segments. This could potentially also be a ratio with the radius.
    draw_circle_2d(self.m_coord, self.prefs.circ_color, self.prefs.circ_radius, circ_segments)

#    bgl.glLineWidth(1)
    bgl.glDisable(bgl.GL_BLEND)


def find_center(source):
    """Assumes that the input is an Edge or an ordered object holding 2 vertices"""
    if type(source) == bmesh.types.BMEdge:
        v0 = source.verts[0]
        v1 = source.verts[1]
    elif len(source) != 2:
        print("find_center accepts a BMEdge or an ordered BMElemSeq, List, or Tuple of vertices.")
    else:
        v0 = source[0]
        v1 = source[1]
    offset = (v0.co - v1.co)/2
    return v0.co - offset


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
        print("Yas queen")
#    if 'FINISHED' not in result:
#        print("Butt")


class MergeTool(bpy.types.Operator):
    """Modal object selection with a ray cast"""
    bl_idname = "mesh.merge_tool"
    bl_label = "Merge Tool"
    bl_options = {'REGISTER', 'UNDO'}  # We probably don't need the REGISTER.

    merge_location: bpy.props.EnumProperty(
        name="Location",
        description="Merge location",
        items=[('FIRST', "First", "Components will be merged at the first component", 1),
               ('LAST', "Last", "Components will be merged at the last component", 2),
               ('CENTER', "Center", "Components will be merged at the center between the two", 3)
               ],
        default='LAST'
    )

    def __init__(self):
        print("========This happens first========")  # Delete me later
        self.prefs = bpy.context.preferences.addons[__name__].preferences
        self.m_coord = None
        self.vert_mode = None
        self.edge_mode = None
        self.face_mode = None
        self.start_comp = None
        self.end_comp = None
        self.started = False
        self._handle3d = None
        self._handle2d = None


    def remove_handles(self, context):
        if self._handle3d:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle3d, 'WINDOW')
            self._handle3d = None
        if self._handle2d:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle2d, 'WINDOW')
            self._handle2d = None


    def modal(self, context, event):
        context.area.tag_redraw()

        if event.alt or event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            # allow navigation (event.alt allows for using Industry Compatible keymap navigation)
            return {'PASS_THROUGH'}
        elif event.type == 'MOUSEMOVE':
            if self.started:
#                self.bm.select_history.clear()
#                bpy.ops.mesh.select_all(action='DESELECT')  # ANY PERFORMANCE HIT FOR THIS?
                self.m_coord = event.mouse_region_x, event.mouse_region_y
                bpy.ops.view3d.select(extend=False, location=self.m_coord)
                print("Running view3d.select")  # Delete me later (this runs A LOT)

#                if result == {'PASS_THROUGH'}:
#                    bpy.ops.mesh.select_all(action='DESELECT')
#                    self.end_comp = None
#                    self.end_comp_transformed = None
#                    print("debug")

                selected_comp = None
                selected_comp = self.bm.select_history.active
#                print(selected_comp)

                if selected_comp:
                    self.end_comp = selected_comp  # Set the end component
                    if self.vert_mode:
                        self.end_comp_transformed = self.world_matrix @ self.end_comp.co
                    elif self.edge_mode:
                        self.end_comp_transformed = self.world_matrix @ find_center(self.end_comp)
                        self.e1 = selected_comp
#                else:  # Future improvement: If we replace the use of view3d.select with actual raycasting we can detect if the ray has no hits (is empty space) and only then set end_comp back to None.
#                    self.end_comp = None  # That way we can do no merge if we're off mesh, but if we're on mesh we won't get flickering if the cursor is on a big face not near an edge or vertex.
#                    self.end_comp_transformed = None
        elif event.type == 'LEFTMOUSE':
            main(self, context, event)
            if not self.started:
                if (self.vert_mode and context.object.data.total_vert_sel == 1) or \
                   (self.edge_mode and context.object.data.total_edge_sel == 1):
                    selected_comp = None
                    selected_comp = self.bm.select_history.active

                    if selected_comp:
                        self.start_comp = selected_comp  # Set the start component
                        if self.vert_mode:
                            self.start_comp_transformed = self.world_matrix @ self.start_comp.co  # Edge mode is going to need 6 transformed points to draw; the verts and center of each edge.  I feel that transformation should happen outside of the actual draw handlers?
                        elif self.edge_mode:
                            self.start_comp_transformed = self.world_matrix @ find_center(self.start_comp)
                            self.e0 = selected_comp
                    else:
                        self.remove_handles(context)
                        print("Nope, cancelled.")  # Delete me later
                        return {'CANCELLED'}
                    self.started = True
                    print("We're in here and are started.")
            elif self.start_comp is self.end_comp:
                self.remove_handles(context)
                context.workspace.status_text_set(None)
                print("Cancelled for lack of anything to do.")  # Delete me later
                return {'CANCELLED'}
            elif self.start_comp is not None and self.end_comp is not None:
                bpy.ops.mesh.select_all(action='DESELECT')  # Clear selection
                self.bm.select_history.clear()  # Purge selection history so we can manually control it
                try:
                    if self.vert_mode:
                        self.start_comp.select = True
                        self.end_comp.select = True
                        self.bm.select_history.add(self.start_comp)
                        self.bm.select_history.add(self.end_comp)
                        bpy.ops.mesh.merge(type=self.merge_location)
                    elif self.edge_mode:
                        bpy.ops.object.mode_set_with_submode(mode='EDIT', mesh_select_mode={'VERT'})  # THIS MAY NOT BE NECESSARY NOW THAT WE'RE DOING BMESH MERGING; TEST AND SEE. Note: would have to replace the bpy.ops.mesh.merge code for the "edges share a vertex" case.
                        # Separate edges
                        if not any([v for v in self.start_comp.verts if v in self.end_comp.verts]):
                            bridge = bmesh.ops.bridge_loops(self.bm, edges=(self.start_comp, self.end_comp))
                            new_e0 = bridge['edges'][0]
                            new_e1 = bridge['edges'][1]
                            sv0 = [v for v in new_e0.verts if v in self.start_comp.verts][0]
                            sv1 = [v for v in new_e1.verts if v in self.start_comp.verts][0]
                            ev0 = new_e0.other_vert(sv0)
                            ev1 = new_e1.other_vert(sv1)

                            merge_map = {}
                            merge_map[sv0] = ev0
                            merge_map[sv1] = ev1
                            # bmesh weld_verts always moves verts to target so we must manually set desired vert.co
                            if self.merge_location == 'FIRST':
                                ev0.co = sv0.co
                                ev1.co = sv1.co
                            elif self.merge_location == 'CENTER':
                                ev0.co = find_center(new_e0)
                                ev1.co = find_center(new_e1)
                            elif self.merge_location == 'LAST':
                                sv0.co = ev0.co
                                sv1.co = ev1.co
                            bmesh.ops.weld_verts(self.bm, targetmap=merge_map)
                            bmesh.update_edit_mesh(self.me)
                        # Edges share a vertex
                        else:
                            shared_vert = [v for v in self.start_comp.verts if v in self.end_comp.verts][0]
                            print("shared index:", shared_vert.index)
                            for v in self.start_comp.verts:
                                if v is not shared_vert:
                                    v.select = True
                                    self.bm.select_history.add(v)
                            for v in self.end_comp.verts:
                                if v is not shared_vert:
                                    v.select = True
                                    self.bm.select_history.add(v)
                            bpy.ops.mesh.merge(type=self.merge_location)
                        bpy.ops.object.mode_set_with_submode(mode='EDIT', mesh_select_mode={'EDGE'})  # THIS MAY NOT BE NECESSARY NOW THAT WE'RE DOING BMESH MERGING; TEST AND SEE. Note: would have to replace the bpy.ops.mesh.merge code for the "edges share a vertex" case.

#                    bpy.ops.ed.undo_push(
#                        message="Merge Tool undo step")  # We may not even need the undo step if all we are doing is running a merge?  (Perhaps if the merge fails this is good to prevent undoing a step farther than the user wants?)
                except TypeError:
                    print("That failed for some reason.")
                    return {'CANCELLED'}
                finally:
                    bpy.ops.mesh.select_all(action='DESELECT')
                    self.start_comp = None
                    self.end_comp = None
                    if self.edge_mode:
                        self.e0 = None
                        self.e1 = None
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
        self.vert_mode = context.tool_settings.mesh_select_mode[0] and not context.tool_settings.mesh_select_mode[1]
        self.edge_mode = context.tool_settings.mesh_select_mode[1] and not context.tool_settings.mesh_select_mode[0]
        self.face_mode = context.tool_settings.mesh_select_mode[2]

        print("Modes:", self.vert_mode, self.edge_mode, self.face_mode)

        # Checks if we are in face selection mode.
        if self.face_mode:
            self.report({'WARNING'}, "Merge Tool does not work with Face selection mode")
            return {'CANCELLED'}
        if context.tool_settings.mesh_select_mode[0] and context.tool_settings.mesh_select_mode[1]:
            self.report({'WARNING'}, "Selection Mode must be Vertex OR Edge, not both at the same time")
            return {'CANCELLED'}
        if context.space_data.type == 'VIEW_3D':
            context.workspace.status_text_set("Left click and drag to merge vertices, Esc or right click to cancel")

            self.start_comp = None
            self.end_comp = None
            self.started = False

            main(self, context, event)  #This goes up here or else there will be a hard crash; probably one of the "gotchas" related to memory pointers.

            if self.vert_mode and context.object.data.total_vert_sel == 0:
                context.workspace.status_text_set(None)
                return {'CANCELLED'}
            elif self.edge_mode and context.object.data.total_edge_sel == 0:
                context.workspace.status_text_set(None)
                return {'CANCELLED'}

            self.me = bpy.context.object.data
            self.world_matrix = bpy.context.object.matrix_world
            self.bm = bmesh.from_edit_mesh(self.me)

            args = (self, context)
            self._handle3d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_3d, args, 'WINDOW', 'POST_VIEW')
            if self.prefs.show_circ:
                self._handle2d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_2d, args, 'WINDOW', 'POST_PIXEL')

            context.window_manager.modal_handler_add(self)
            if not self.started:
                if (self.vert_mode and context.object.data.total_vert_sel == 1) or \
                   (self.edge_mode and context.object.data.total_edge_sel == 1):
                    selected_comp = None
                    selected_comp = self.bm.select_history.active

                    if selected_comp:
                        self.start_comp = selected_comp  # Set the start component
                        if self.vert_mode:
                            self.start_comp_transformed = self.world_matrix @ self.start_comp.co  # Edge mode is going to need 6 transformed points to draw; the verts and center of each edge.  I feel that transformation should happen outside of the actual draw handlers?
                        elif self.edge_mode:
                            self.start_comp_transformed = self.world_matrix @ find_center(self.start_comp)
                            self.e0 = selected_comp
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
classes.append(MergeTool)


class WorkSpaceMergeTool(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'

    bl_idname = "edit_mesh.merge_tool"
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
        row.prop(tool_props, "merge_location", text="Location")


def register():
    for every_class in classes:
        bpy.utils.register_class(every_class)
    bpy.utils.register_tool(WorkSpaceMergeTool, after={"builtin.measure"}, separator=True, group=False)


def unregister():
    for every_class in classes:
        bpy.utils.unregister_class(every_class)
    bpy.utils.unregister_tool(WorkSpaceMergeTool)


if __name__ == "__main__":
    register()
