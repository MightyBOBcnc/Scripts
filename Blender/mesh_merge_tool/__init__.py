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
    "version": (1, 3, 0),
    "blender": (2, 80, 0),
    "location": "View3D > TOOLS > Merge Tool",
    "warning": "Dev Branch. Somewhat experimental features. Possible performance issues.",
    "wiki_url": "https://github.com/MightyBOBcnc/Scripts/tree/Loopanar-Hybrid/Blender",
    "tracker_url": "https://github.com/MightyBOBcnc/Scripts/issues",
    "category": "Mesh"
}

# ToDo:
# Real raycasting
# Modifier or alternate keys to specify First/Last/Center at runtime
#     Side note: At present because the WorkSpaceMergeTool only has a bl_keymap for leftmouse press, anything that isn't a leftmouse press gets ignored and executed normally without even firing the tool.
#     To have modifiers we would need to add more bl_keymap entries in case the user starts their action with the modifier held.
#     This would potentially break the current benefit where, at present, shift+leftmouse and ctrl+leftmouse are being ignored and passed to the regular view3d.select operator so even more special handling code would need to be written.
# Fallback tool (box or lasso select)
#     Configurable by user.  # NOTE: This may conflict with modifier/alternate keys because shift/ctrl/alt+LMB are used by box and lasso.
# Possibly see if vertices can be added to a list in real time as the mouse is dragged and then merge at the final one where the mouse is released.
# To more easily allow most of the above, some parts of the function should be abstracted out (e.g. the part that is duplicated in the modal and the invoke where we check if not self.started in order to set the start_comp)
# Maybe a mode where you can use the Circle Select to paint the vertices to merge. (multi-merge)
# Test and find out if context is actually needed in the remove_handles, draw_callback_3d, and draw_callback_2d functions.  (After removing and testing, it doesn't seem to be strictly required, but it's there in Blender's built-in templates so I'm keeping it even though it doesn't appear to do anything.)
# The part of the code that does the merging could use some cleanup because it's a bit repetitive.
#     We might also get rid of all use of bpy.ops.mesh.merge(type=self.merge_location) and manual selection and select_history manipulation at some point for any merging of only two vertices. (multi-merge would need to use it still, because math for the CENTER mode might be hard)(plot twist: it's easy)
# We probably don't need the REGISTER in the bl_options. (although if called directly instead of via tool, maybe we do)  Need to test and find out.
# I wonder if the workspacetool trigger keymap entry could actually be a tweak event, which would allow us to pass through regular click and double click events.  (I tested and yes this works; but this might preclude having box or lasso as a fallback tool.)
#     It MIGHT be possible to use Left Mouse to start the tool but then in the Invoke section if we detect a tweak we run the fallback tool instead.  But this might be unreliable.  It simply might not be possible to have a fallback tool like box or lasso because they are click+drag just like Merge Tool.
# This may be a bad idea, but possibly a default merge location that is different for vertices and edges, like vertices merge to last by default and edges merge to center by default.  It would be easy to code but could by far too convoluted as a user experience because it might be confusing which mode you're in and which position it will merge to.
# Collapse edge rings. If N number of edges are part of contiguous loops that are right next to each other (opposite edges on the same quad face loop), if they're part of the initial selection like the vert multi-merge, then collapse them from 2 loops into 1 loop.  Must be an even number total.


import bpy
import bgl
import gpu
import bmesh
import os
from mathutils import Vector
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
if bpy.app.version[1] < 81:  # 2.80 didn't have the PAINT_CROSS cursor
    t_cursor = 'CROSSHAIR'
else:
    t_cursor = 'PAINT_CROSS'


classes = []

class MergeToolPreferences(bpy.types.AddonPreferences):
    # this must match the addon __name__
    # use '__package__' when defining this in a submodule of a python package.
    bl_idname = __name__

    allow_multi: BoolProperty(name="Allow Multi-Merge",
        description="In Vertex mode, if there is a starting selection, merge all those vertices together",
        default=True)

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

        layout.prop(self, "allow_multi")
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


vertex_shader = '''
    uniform mat4 u_ViewProjectionMatrix;

    in vec3 position;
    in float arcLength;

    out float v_ArcLength;

    void main()
    {
        v_ArcLength = arcLength;
        gl_Position = u_ViewProjectionMatrix * vec4(position, 1.0f);
    }
'''

fragment_shader = '''
    uniform float u_Scale;
    uniform vec4 u_Color;

    in float v_ArcLength;
    out vec4 FragColor;

    void main()
    {
        if (step(sin(v_ArcLength * u_Scale), 0.5) == 1) discard;
        FragColor = vec4(u_Color);
    }
'''


class DrawPoint():
    def __init__(self):
        self.shader = None
        self.coords = None
        self.color = None

    def draw(self):
        batch = batch_for_shader(self.shader, 'POINTS', {"pos": self.coords})
        self.shader.bind()
        self.shader.uniform_float("color", self.color)
        batch.draw(self.shader)

    def add(self, shader, coords, color):
        self.shader = shader
        if isinstance(coords, Vector):
            self.coords = [coords]
        else:
            self.coords = coords
        self.color = color
        self.draw()


class DrawLine():
    def __init__(self):
        self.shader = None
        self.coords = None
        self.color = None

    def draw(self):
        batch = batch_for_shader(self.shader, 'LINES', {"pos": self.coords})
        self.shader.bind()
        self.shader.uniform_float("color", self.color)
        batch.draw(self.shader)

    def add(self, shader, coords, color):
        self.shader = shader
        self.coords = coords
        self.color = color
        self.draw()


class DrawLineDashed():
    def __init__(self):
        self.shader = None
        self.coords = None
        self.color = None
        self.arc_lengths = None

    def draw(self):
        batch = batch_for_shader(self.shader, 'LINES', {"position": self.coords, "arcLength": self.arc_lengths})
        self.shader.bind()
        matrix = bpy.context.region_data.perspective_matrix
        self.shader.uniform_float("u_ViewProjectionMatrix", matrix)
        self.shader.uniform_float("u_Scale", 50)
        self.shader.uniform_float("u_Color", self.color)
        batch.draw(self.shader)

    def add(self, shader, coords, color):
        self.shader = shader
        self.coords = coords
        self.color = color
        self.arc_lengths = [0]
        for a, b in zip(self.coords[:-1], self.coords[1:]):
            self.arc_lengths.append(self.arc_lengths[-1] + (a - b).length)
        self.draw()


def draw_callback_3d(self, context):
    if self.started and self.start_comp is not None:
        bgl.glEnable(bgl.GL_BLEND)
        bgl.glPointSize(self.prefs.point_size)
        shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
        if self.end_comp is not None and self.end_comp != self.start_comp:
            bgl.glLineWidth(self.prefs.line_width)
            if not self.multi_merge:
                line_coords = [self.start_comp_transformed, self.end_comp_transformed]
            else:
                line_coords = []
                vert_coords = []
                if self.merge_location == 'CENTER':
                    vert_list = [v.co for v in self.start_sel]
                    if self.end_comp not in self.start_sel:
                        vert_list.append(self.end_comp.co)
                    for v in self.start_sel:
                        line_coords.append(self.world_matrix @ v.co)
                        line_coords.append(self.world_matrix @ find_center(vert_list))
                        vert_coords.append(self.world_matrix @ v.co)
                    line_coords.append(self.end_comp_transformed)
                    line_coords.append(self.world_matrix @ find_center(vert_list))
                elif self.merge_location == 'LAST':
                    for v in self.start_sel:
                        line_coords.append(self.world_matrix @ v.co)
                        line_coords.append(self.end_comp_transformed)
                        vert_coords.append(self.world_matrix @ v.co)
                elif self.merge_location == 'FIRST':
                    for v in self.start_sel:
                        line_coords.append(self.world_matrix @ v.co)
                        line_coords.append(self.start_comp_transformed)
                        vert_coords.append(self.world_matrix @ v.co)
                    line_coords.append(self.end_comp_transformed)
                    line_coords.append(self.start_comp_transformed)

            # Line that connects the start and end position (draw first so it's beneath the vertices)
            if not self.multi_merge:
                tool_line = DrawLine()
                tool_line.add(shader, line_coords, self.prefs.line_color)
            else:
                shader_dashed = gpu.types.GPUShader(vertex_shader, fragment_shader)
                tool_line = DrawLineDashed()
                tool_line.add(shader_dashed, line_coords, self.prefs.line_color)

            # Ending edge
            if self.sel_mode == 'EDGE':
                bgl.glLineWidth(self.prefs.edge_width)
                e1v = [self.world_matrix @ v.co for v in self.end_comp.verts]

                end_edge = DrawLine()
                if self.merge_location in ('FIRST', 'CENTER'):
                    end_edge.add(shader, e1v, self.prefs.start_color)
                else:
                    end_edge.add(shader, e1v, self.prefs.end_color)

            # Ending point
            end_point = DrawPoint()
            if self.multi_merge:
                end_point.add(shader, vert_coords, self.prefs.start_color)
            if self.merge_location in ('FIRST', 'CENTER'):
                end_point.add(shader, self.end_comp_transformed, self.prefs.start_color)
            else:
                end_point.add(shader, self.end_comp_transformed, self.prefs.end_color)

            # Middle point
            if self.merge_location == 'CENTER':
                if self.sel_mode == 'VERT':
                    if self.multi_merge:
                        midpoint = self.world_matrix @ find_center(vert_list)
                    else:
                        midpoint = self.world_matrix @ find_center([self.start_comp, self.end_comp])
                elif self.sel_mode == 'EDGE':
                    midpoint = self.world_matrix @ \
                            find_center([find_center(self.start_comp), find_center(self.end_comp)])

                mid_point = DrawPoint()
                mid_point.add(shader, midpoint, self.prefs.end_color)

        # Starting edge
        if self.sel_mode == 'EDGE':
            bgl.glLineWidth(self.prefs.edge_width)
            e0v = [self.world_matrix @ v.co for v in self.start_comp.verts]

            start_edge = DrawLine()
            if self.merge_location == 'FIRST':
                start_edge.add(shader, e0v, self.prefs.end_color)
            else:
                start_edge.add(shader, e0v, self.prefs.start_color)

        # Starting point
        start_point = DrawPoint()
        if self.merge_location == 'FIRST':
            start_point.add(shader, self.start_comp_transformed, self.prefs.end_color)
        else:
            start_point.add(shader, self.start_comp_transformed, self.prefs.start_color)

        bgl.glLineWidth(1)
        bgl.glPointSize(1)
        bgl.glDisable(bgl.GL_BLEND)


def draw_callback_2d(self, context):
    bgl.glEnable(bgl.GL_BLEND)

    # Have to add 1 for some reason in order to get proper number of segments.
    # This could potentially also be a ratio with the radius.
    circ_segments = 8 + 1
    draw_circle_2d(self.m_coord, self.prefs.circ_color, self.prefs.circ_radius, circ_segments)

    bgl.glDisable(bgl.GL_BLEND)


def find_center(source):
    """Assumes that the input is an Edge or an ordered object holding vertices or Vectors"""
    coords = []
    if isinstance(source, bmesh.types.BMEdge):
        coords = [source.verts[0].co, source.verts[1].co]
    elif isinstance(source[0], bmesh.types.BMVert):
        coords = [v.co for v in source]
    elif isinstance(source[0], Vector):
        coords = [v for v in source]

    offset = Vector((0.0, 0.0, 0.0))
    for v in coords:
        offset = offset + v
    return offset / len(coords)


def set_component(self, mode):
    selected_comp = None
    selected_comp = self.bm.select_history.active

    if selected_comp:
        if mode == 'START':
            self.start_comp = selected_comp  # Set the start component
            if self.sel_mode == 'VERT':
                self.start_comp_transformed = self.world_matrix @ self.start_comp.co
            elif self.sel_mode == 'EDGE':
                self.start_comp_transformed = self.world_matrix @ find_center(self.start_comp)
        if mode == 'END':
            self.end_comp = selected_comp  # Set the end component
            if self.sel_mode == 'VERT':
                self.end_comp_transformed = self.world_matrix @ self.end_comp.co
            elif self.sel_mode == 'EDGE':
                self.end_comp_transformed = self.world_matrix @ find_center(self.end_comp)


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
    # We probably don't need the REGISTER. (although if called directly instead of via tool, maybe we do)
    bl_options = {'REGISTER', 'UNDO'}

    merge_location: EnumProperty(
        name = "Location",
        description = "Merge location",
        items = [('FIRST', "First", "Components will be merged at the first component", 'TRIA_LEFT', 1),
                ('LAST', "Last", "Components will be merged at the last component", 'TRIA_RIGHT', 2),
                ('CENTER', "Center", "Components will be merged at the center between the two", 'TRIA_DOWN', 3)
                ],
        default = 'LAST'
    )

    wait_for_input: BoolProperty(
        name = "Wait for Input",
        description = "Wait for input or begin modal immediately",
        default = False
    )

    def __init__(self):
        print("========This happens first========")  # Delete me later
        self.prefs = bpy.context.preferences.addons[__name__].preferences
        self.window = bpy.context.window_manager.windows[0]
        self.m_coord = None
        self.sel_mode = None
        self.start_sel = None
        self.start_comp = None
        self.end_comp = None
        self.started = False
        self.multi_merge = False
        self._handle3d = None
        self._handle2d = None

    def restore_selection(self):
        bpy.ops.mesh.select_all(action='DESELECT')
        if self.start_sel is not None and len(self.start_sel) > 1:
            for c in self.start_sel:
                c.select = True
            self.bm.select_flush_mode()
            bmesh.update_edit_mesh(self.me)

    def finish(self, context):
        self.remove_handles(context)
        context.workspace.status_text_set(None)
        self.window.cursor_modal_restore()
        self.m_coord = None  # Most of this is probably not required
        self.sel_mode = None
        self.start_sel = None
        self.start_comp = None
        self.end_comp = None
        self.started = False
        self.multi_merge = False
        self._handle3d = None
        self._handle2d = None

    def add_handles(self, context):
        args = (self, context)
        self._handle3d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_3d, args, 'WINDOW', 'POST_VIEW')
        if self.prefs.show_circ:
            self._handle2d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_2d, args, 'WINDOW', 'POST_PIXEL')

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
            # Allow navigation (event.alt allows for using Industry Compatible keymap navigation)
            return {'PASS_THROUGH'}
        elif event.type in {'ONE', 'A', 'F'} and event.value == 'PRESS':
            self.merge_location = 'FIRST'
        elif event.type in {'TWO', 'C'} and event.value == 'PRESS':
            self.merge_location = 'CENTER'
        elif event.type in {'THREE', 'L'} and event.value == 'PRESS':
            self.merge_location = 'LAST'
        elif event.type == 'MOUSEMOVE':
            if self.started:
#                self.bm.select_history.clear()
#                bpy.ops.mesh.select_all(action='DESELECT')  # ANY PERFORMANCE HIT FOR THIS?
                self.m_coord = event.mouse_region_x, event.mouse_region_y
                bpy.ops.view3d.select(extend=False, location=self.m_coord)
#                print("Running view3d.select")  # Delete me later (this runs A LOT)

#                if result == {'PASS_THROUGH'}:
#                    bpy.ops.mesh.select_all(action='DESELECT')
#                    self.end_comp = None
#                    self.end_comp_transformed = None
#                    print("debug")

                set_component(self, 'END')

#                else:  # Future improvement: If we replace the use of view3d.select with actual raycasting we can detect if the ray has no hits (is empty space) and only then set end_comp back to None.
#                    self.end_comp = None  # That way we can do no merge if we're off mesh, but if we're on mesh we won't get flickering if the cursor is on a big face not near an edge or vertex.
#                    self.end_comp_transformed = None
        elif event.type == 'LEFTMOUSE':
            main(self, context, event)
            if not self.started:
                if (self.sel_mode == 'VERT' and context.object.data.total_vert_sel == 1) or \
                   (self.sel_mode == 'EDGE' and context.object.data.total_edge_sel == 1):

                    set_component(self, 'START')
                    self.started = True
                    if self.prefs.allow_multi and self.sel_mode == 'VERT':
                        if self.start_sel and self.start_comp in self.start_sel:
                            self.multi_merge = True
                    print("We're in here and are started.")
                    self.add_handles(context)

                else:
                    self.finish(context)
                    print("Nope, cancelled.")  # Delete me later
                    return {'CANCELLED'}
            elif self.start_comp is self.end_comp:
                self.finish(context)
                print("Cancelled for lack of anything to do.")  # Delete me later
                return {'CANCELLED'}
            elif self.start_comp is not None and self.end_comp is not None:
                bpy.ops.mesh.select_all(action='DESELECT')  # Clear selection
                self.bm.select_history.clear()  # Purge selection history so we can manually control it
                try:
                    if self.sel_mode == 'VERT':
                        if self.multi_merge:
                            print("Gonna try a big merge")
                            for v in self.start_sel:
                                v.select = True
                        self.start_comp.select = True
                        self.end_comp.select = True
                        self.bm.select_history.add(self.start_comp)
                        self.bm.select_history.add(self.end_comp)
                        bpy.ops.mesh.merge(type=self.merge_location)
                    elif self.sel_mode == 'EDGE':
                        # Two separate edges
                        if not any([v for v in self.start_comp.verts if v in self.end_comp.verts]):
                            bridge = bmesh.ops.bridge_loops(self.bm, edges=(self.start_comp, self.end_comp))
                            new_e0 = bridge['edges'][0]
                            new_e1 = bridge['edges'][1]
                            sv0 = [v for v in new_e0.verts if v in self.start_comp.verts][0]  # Start vert 0
                            sv1 = [v for v in new_e1.verts if v in self.start_comp.verts][0]  # Start vert 1
                            ev0 = new_e0.other_vert(sv0)  # End vert 0
                            ev1 = new_e1.other_vert(sv1)  # End vert 1

                            merge_map = {}
                            merge_map[sv0] = ev0
                            merge_map[sv1] = ev1
                            # bmesh weld_verts always moves verts to target so we must manually set desired vert.co
                            if self.merge_location == 'FIRST':  # Move end verts to start vert locations
                                ev0.co = sv0.co
                                ev1.co = sv1.co
                            elif self.merge_location == 'CENTER':  # Move end verts to centers
                                ev0.co = find_center(new_e0)
                                ev1.co = find_center(new_e1)
                            elif self.merge_location == 'LAST':  # Moving not required but doing this for consistency
                                sv0.co = ev0.co
                                sv1.co = ev1.co
                            bmesh.ops.weld_verts(self.bm, targetmap=merge_map)
                            bmesh.update_edit_mesh(self.me)
                        # Edges share a vertex
                        else:
                            shared_vert = [v for v in self.start_comp.verts if v in self.end_comp.verts][0]
#                            print("shared index:", shared_vert.index)  # Delete me later
                            sv = [v for v in self.start_comp.verts if v is not shared_vert][0]  # Start vert
                            ev = [v for v in self.end_comp.verts if v is not shared_vert][0]  # End vert
                            merge_map = {}
                            merge_map[sv] = ev
                            # bmesh weld_verts always moves verts to target so we must manually set desired vert.co
                            if self.merge_location == 'FIRST':  # Move end verts to start vert locations
                                ev.co = sv.co
                            elif self.merge_location == 'CENTER':  # Move end verts to centers
                                ev.co = find_center([sv, ev])
                            elif self.merge_location == 'LAST':  # Moving not required but doing this for consistency
                                sv.co = ev.co
                            bmesh.ops.weld_verts(self.bm, targetmap=merge_map)
                            bmesh.update_edit_mesh(self.me)

#                    bpy.ops.ed.undo_push(
#                        message="Merge Tool undo step")  # We may not even need the undo step if all we are doing is running a merge?  (Perhaps if the merge fails this is good to prevent undoing a step farther than the user wants?)
                except TypeError:
                    print("That failed for some reason.")
                    self.finish(context)
                    return {'CANCELLED'}
                finally:
                    bpy.ops.mesh.select_all(action='DESELECT')
                    self.finish(context)
                return {'FINISHED'}
            else:
                self.finish(context)
                print("End of line; cancelled.")  # Delete me later
                return {'CANCELLED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            print("Cancelled")  # Delete me later
            self.restore_selection()
            self.finish(context)
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        if context.tool_settings.mesh_select_mode[0] and not context.tool_settings.mesh_select_mode[1]:
            self.sel_mode = 'VERT'
        elif context.tool_settings.mesh_select_mode[1] and not context.tool_settings.mesh_select_mode[0]:
            self.sel_mode = 'EDGE'
        elif context.tool_settings.mesh_select_mode[2]:
            self.sel_mode = 'FACE'

        # Check for incompatible modes first
        if self.sel_mode == 'FACE':
            self.report({'WARNING'}, "Merge Tool does not work with Face selection mode")
            return {'CANCELLED'}
        if context.tool_settings.mesh_select_mode[0] and context.tool_settings.mesh_select_mode[1]:
            self.report({'WARNING'}, "Selection Mode must be Vertex OR Edge, not both at the same time")
            return {'CANCELLED'}
        if context.space_data.type == 'VIEW_3D':
            context.workspace.status_text_set("Left click and drag to merge vertices. Esc or right click to cancel. Modifier keys during drag: [1], [2], [3], [A], [C], [F], [L]")

#            self.start_comp = None
#            self.end_comp = None
#            self.started = False
            self.me = bpy.context.object.data
            self.world_matrix = bpy.context.object.matrix_world
            self.bm = bmesh.from_edit_mesh(self.me)
#            self.start_sel = None

            if self.sel_mode == 'VERT' and context.object.data.total_vert_sel > 1:
                self.start_sel = [v for v in self.bm.verts if v.select]
            elif self.sel_mode == 'EDGE' and context.object.data.total_edge_sel > 1:
                self.start_sel = [e for e in self.bm.edges if e.select]

            if self.wait_for_input:
                # https://docs.blender.org/api/current/bpy.types.WindowManager.html#bpy.types.WindowManager.modal_handler_add  Is this proper usage and/or mandatory?
                context.window_manager.modal_handler_add(self)
                self.window.cursor_modal_set(t_cursor)
                print("Operator invoked directly instead of via tool")
                return {'RUNNING_MODAL'}

            main(self, context, event)  #This goes up here or else there will be a hard crash

            if self.sel_mode == 'VERT' and context.object.data.total_vert_sel == 0:  # These two checks will need to be replaced if we want to be able to set a fallback of box/lasso select?
                self.finish(context)
                print("Cancelled; No starting component to begin.")
                return {'CANCELLED'}
            elif self.sel_mode == 'EDGE' and context.object.data.total_edge_sel == 0:
                self.finish(context)
                print("Cancelled; No starting component to begin.")
                return {'CANCELLED'}

            self.add_handles(context)

            if not self.started:
                if (self.sel_mode == 'VERT' and context.object.data.total_vert_sel == 1) or \
                   (self.sel_mode == 'EDGE' and context.object.data.total_edge_sel == 1):

                    set_component(self, 'START')
                    self.started = True
                    if self.prefs.allow_multi and self.sel_mode == 'VERT':
                        if self.start_sel and self.start_comp in self.start_sel:
                            self.multi_merge = True
                else:
                    self.finish(context)
                    print("Nope, cancelled.")  # Delete me later
                    return {'CANCELLED'}

            # https://docs.blender.org/api/current/bpy.types.WindowManager.html#bpy.types.WindowManager.modal_handler_add  Is this proper usage and/or mandatory?
            context.window_manager.modal_handler_add(self)
            self.window.cursor_modal_set(t_cursor)
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
    bl_cursor = t_cursor
    bl_widget = None
    bl_keymap = (
        ("mesh.merge_tool", {"type": 'LEFTMOUSE', "value": 'PRESS'},
        {"properties": [("wait_for_input", False)]}),
    )

    def draw_settings(context, layout, tool):
        tool_props = tool.operator_properties("mesh.merge_tool")
        prefs = bpy.context.preferences.addons[__name__].preferences

        row = layout.row()
        row.prop(tool_props, "merge_location")
        row.prop(prefs, "allow_multi")
#        row.prop(tool_props, "wait_for_input")


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
