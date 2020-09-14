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
    "name": "Context Select Hybrid",
    "description": "Context-aware loop selection for vertices, edges, and faces.",
    "author": "Andreas Strømberg, nemyax, Chris Kohl",
    "version": (0, 1, 8),
    "blender": (2, 80, 0),
    "location": "",
    "warning": "Dev Branch. Somewhat experimental features. Possible performance issues.",
    "wiki_url": "https://github.com/MightyBOBcnc/Scripts/tree/Loopanar-Hybrid/Blender",
    "tracker_url": "https://github.com/MightyBOBcnc/Scripts/issues",
    "category": "Mesh"
}

# ToDo: 
# Fully implement checks for hidden geometry and prefs.ignore_hidden_geometry option. (Still need to test with instanced geometry.)
#     And then tell this guy about it: https://blender.community/c/rightclickselect/ltbbbc/
# Add some more robust checks to validate against nonmanifold geometry like more than 2 faces connected to 1 edge and such.
#    And--in appropriate places--tests like component.is_manifold, component.is_boundary, and (for edges only, I think) e.is_wire
# More speed/performance testing and improvements.
# Implement deselection for all methods of selection (except maybe select_linked).
#    This is actually going to be problematic because we need to track the most recent DEselected component, which Blender does not do.
#    This addon only executes on double click.  We would have to build a helper function using the @persistent decorator to maintain a deselection list (even if said list is only 2 members long).
#    And we would have to replace the regular view3d.select operator in at least 1 place (whatever the keymap is for deselecting; e.g. Ctrl+Click.. or Shift+Click if it's set to Toggle?)
#    And Blender's wonky Undo system would invalidate the deselection list although that MAY not be a problem for something as simple as tracking only 2 components.
#        Rather than using an object property to store the two most recently deselected components would it make sense to use a custom layer?
#        https://b3d.interplanety.org/en/assigning-custom-properties-to-vertexes/  (Probably not; but it's worth investigating the performance costs involved in creating, updating, or deleting custom layers.  I still have to do my own raycasts either way..)
# Investigate doing our own raycasting. 
#    This would be needed if we want DEselection because Blender has no 'deselection history' list. Unless we want to compare the selection history for every view3d.select click but that would be much messier.
#    It is also a solution for the bug where double clicking on empty space causes a selection (although that one could alternatively be solved by adding 'deselect on nothing' to the default view3d.select keymap entries).
# Find out if these selection tools can be made to work in the UV Editor. (NOTE: Probably need to set double click and shift double click operators for the UV section if the key map editor)
# Write own loop/ring selection function for wire edges.  Loops will be easy because I don't think we have to worry about normal vector direction?  Rings will be harder because there's no face loop?  Or maybe it's the same with loop radial and then walk forward twice.  We'll see.
#    After looking into this, this is actually much harder than I thought it would be.  Rings might be impossible, loops are HARD unless it's just a single loop (only 2 edges per vertex like the Circle object).  Will need extra steps and 2 or 3-level deep testing.
# Bounded edge loop selection on a floating edge ring like the Circle primitive type. (Wire edges.)
# Possible new user preferences:
#    Terminate self-intersecting loops and rings at crossing point.
#        Successfully implemented this for all manifold component selections and boundary edges! That just leaves nonmanifold selection types if I choose to do so.
#    Allow user to specify which select_linked method they want to use on double click? (from a dropdown list)  Or, instead maybe forcibly pop up the delimit=set() in the corner instead?  Hmm but it doesn't appear to always force the popup?
#    Preference to not use bm.select_flush_mode() at the end of the functions? This would make it so that sub-components aren't visibly selected (e.g. the edge between 2 verts) but you'd have to replace all the regular view3d.select operators as well.
# Consolidate redundant code.  I still haven't figured out a proper way to do this since the main loop-getting functions are almost identical but with different methods for getting the next component and testing for dead ends...
#    Partially done, now.  Made generic partial loop functions for manifold vertices, edges, and faces that are strung together to get full loops or bounded loops.
# Investigate if bm.free() is needed to prevent memory leaks.  (Free the bmesh) According to the bmesh documentation this happens automatically when a script ends but there are a couple spots where I think I'm getting multiple bmeshes so it might be wise to free them up separately.
# Investigate adding keymap entries automatically in the add-on preferences and/or the main keymap preferences.  What I know for certain is that the way Cirno's Box Select X-Ray add-on seems extraordinarily complicated and straight up does not work when I try to use his add-on (I always have to hard-code my defaults).
# Extension methods: 
#    [X] manifold vertex, 
#        [X] Full loop
#        [X] Bounded loop
#    [ ] boundary vertex, 
#        [p] Full loop (for the time being this works by using the edge mode)
#        [ ] Bounded loop
#    [ ] wire vertex, 
#        [ ] Full loop
#        [ ] Bounded loop
#    [ ] nonmanifold vertex if I'm feeling spicy
#        [ ] Full loop
#        [ ] Bounded loop
#    [X] manifold edge loop, 
#        [X] Full loop
#        [X] Bounded loop
#    [X] manifold edge ring, 
#        [X] Full loop
#        [X] Bounded loop
#    [X] boundary edge loop, 
#        [X] Full loop
#        [X] Bounded loop
#    [ ] wire edge loop, 
#        [ ] Full loop
#        [ ] Bounded loop
#    [ ] nonmanifold edge loop if I'm feeling spicy
#        [ ] Full loop
#        [ ] Bounded loop
#    [X] face loop
#        [X] Full loop
#        [X] Bounded loop
# 
# Fix the boundary edge partial loop function to return indices?  How about we performance test the different between getting and selecting indices and components.  If there's no performance difference we should just use components directly. Other future use cases may need them.
# 
# For vertices and faces.. to stop them from running twice on a bounded loop that is infinite we could do like..
# if "infinite" in list:
    # for face in the connected faces:
        # if that face index in list:
            # remove that connecting face edge loop from consideration so we don't run again in the opposite direction..



import bpy
import bmesh
import time

classes = []
mouse_keymap = []


class ContextSelectPreferences(bpy.types.AddonPreferences):
    # this must match the addon name, use '__package__'
    # when defining this in a submodule of a python package.
    bl_idname = __name__

    select_linked_on_double_click: bpy.props.BoolProperty(
        name="Select Linked On Double Click", 
        description="Double clicking on a face or a vertex (if not part of a loop selection) "
                    + "will select all components for that contiguous mesh piece",
        default=False)

    allow_non_quads_at_ends: bpy.props.BoolProperty(
        name="Allow Non-Quads At Start/End Of Face Loops", 
        description="If a loop of faces terminates at a triangle or n-gon, "
                    + "allow that non-quad face to be added to the final loop selection, "
                    + "and allow using that non-quad face to begin a loop selection. "
                    + "NOTE: For bounded face selection the starting OR ending face must be a quad",
        default=True)

    terminate_self_intersects: bpy.props.BoolProperty(
        name="Terminate Self-Intersects At Intersection", 
        description="If a loop or ring of vertices, edges, or faces circles around and crosses over itself, "
                    + "stop the selection at that location", 
        default=False)

    ignore_boundary_wires: bpy.props.BoolProperty(
        name="Ignore Wire Edges On Boundaries", 
        description="If wire edges are attached to a boundary vertex the selection will ignore it, "
                    + "pass through, and continue selecting the boundary loop",
        default=False)

    leave_edge_active: bpy.props.BoolProperty(
        name="Leave Edge Active After Selections", 
        description="When selecting edge loops or edge rings, the active edge will remain active. "
                    + "NOTE: This changes the behavior of chained neighbour selections",
        default=False)

    ignore_hidden_geometry: bpy.props.BoolProperty(
        name="Ignore Hidden Geometry", 
        description="Loop selections will ignore hidden components and continue through to the other side",
        default=False)
    
    return_single_loop: bpy.props.BoolProperty(
        name="Select Single Bounded Loop", 
        description="For bounded selections, if there are multiple equal-length paths between the start and "
                    + "end component, select only one loop instead of all possible loops",
        default=False)

    def draw(self, context):
        layout = self.layout
        layout.label(text="General Selection:")
        layout.prop(self, "select_linked_on_double_click")
        layout.prop(self, "terminate_self_intersects")
        layout.prop(self, "ignore_hidden_geometry")
        layout.prop(self, "return_single_loop")
        layout.label(text="Edge Selection:")
        layout.prop(self, "leave_edge_active")
        layout.prop(self, "ignore_boundary_wires")
        layout.label(text="Face Selection:")
        layout.prop(self, "allow_non_quads_at_ends")
classes.append(ContextSelectPreferences)


def register_keymap_keys():
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name="Mesh", space_type='EMPTY')

#        kmi = km.keymap_items.new("object.context_select", 'LEFTMOUSE', 'DOUBLE_CLICK', ctrl=True)
#        kmi.properties.mode = 'SUB'
#        mouse_keymap.append((km, kmi))
        
        kmi = km.keymap_items.new("object.context_select", 'LEFTMOUSE', 'DOUBLE_CLICK', shift=True)
        kmi.properties.mode = 'ADD'
        mouse_keymap.append((km, kmi))
        
        kmi = km.keymap_items.new("object.context_select", 'LEFTMOUSE', 'DOUBLE_CLICK')
        kmi.properties.mode = 'SET'
        mouse_keymap.append((km, kmi))

def unregister_keymap_keys():
    for km, kmi in mouse_keymap:
        km.keymap_items.remove(kmi)
    mouse_keymap.clear()


class ObjectMode:
    OBJECT = 'OBJECT'
    EDIT = 'EDIT'
    POSE = 'POSE'
    SCULPT = 'SCULPT'
    VERTEX_PAINT = 'VERTEX_PAINT'
    WEIGHT_PAINT = 'WEIGHT_PAINT'
    TEXTURE_PAINT = 'TEXTURE_PAINT'
    PARTICLE_EDIT = 'PARTICLE_EDIT'
    GPENCIL_EDIT = 'GPENCIL_EDIT'


class ReportErr(bpy.types.Operator):
    bl_idname = 'wm.report_err'
    bl_label = 'Custom Error Reporter'
    bl_description = 'Mini Operator for using self.report outside of an operator'
    
    err_type: bpy.props.StringProperty(name="Error Type")
    err_message: bpy.props.StringProperty(name="Error Message")
    
    def execute(self, context):
        self.report({self.err_type}, self.err_message)
        return {'CANCELLED'}
classes.append(ReportErr)


class OBJECT_OT_context_select(bpy.types.Operator):
    bl_idname = "object.context_select"
    bl_label = "Context Select"
    bl_description = ('Contextually select vertex loops, edge loops, face loops, partial edge loops, '
                     + 'partial face loops, edge rings, partial edge rings, '
                     + 'vertex boundaries, and edge boundaries.')
#    bl_options = {'REGISTER', 'UNDO'} # Do we actually need the REGISTER option?
    bl_options = {'UNDO'} # Do we actually need the REGISTER option?

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

#    mode: bpy.props.StringProperty()
    select_modes = [
    ("SET", "Set", "Set a new selection (deselects any existing selection)", 1),
    ("ADD", "Extend", "Extend selection instead of deselecting everything first", 2),
    ]
 
    mode: bpy.props.EnumProperty(items=select_modes, name="Selection Mode", description="Choose whether to set or extend selection", default="SET")

    def execute(self, context):
        print("=====LET IT BEGIN!=====")
        if context.object.mode == ObjectMode.EDIT: # Isn't there a specific edit_mesh mode? 'edit' is more generic? Or, nah, this is checking the mode of the OBJECT, not the workspace.
            # Checks if we are in vertex selection mode.
            if context.tool_settings.mesh_select_mode[0]: # Since it's a tuple maybe I could test if mesh_select_mode == (1,0,0) ?
                return context_vert_select(context, self.mode)

            # Checks if we are in edge selection mode.
            if context.tool_settings.mesh_select_mode[1]:
                return context_edge_select(context, self.mode)

            # Checks if we are in face selection mode.
            if context.tool_settings.mesh_select_mode[2]:
                if context.area.type == 'VIEW_3D':
                    return context_face_select(context, self.mode)
                elif context.area.type == 'IMAGE_EDITOR':
                    bpy.ops.uv.select_linked_pick(extend=False)
        return {'FINISHED'}

#    def invoke(self, context, event):
#        if event.type == 'SHIFT':
#            self.mode = 'ADD'
#        else:
#            self.mode = 'SET'
#        return {'RUNNING_MODAL'}
classes.append(OBJECT_OT_context_select)


def context_vert_select(context, mode):
    prefs = context.preferences.addons[__name__].preferences
    me = context.object.data
    bm = bmesh.from_edit_mesh(me)

    if len(bm.select_history) == 0:
        return {'CANCELLED'}

    active_vert = bm.select_history.active
    previous_active_vert = bm.select_history[len(bm.select_history) - 2]
    # Sanity check.  Make sure we're actually working with vertices.
    # A more radical option would be to get the bmesh and the active/previous_active component back in the main class and do bmesh.types.BMComponent checks there instead to determine which context_N_select to use rather than relying on mesh_select_mode.
    # That could possibly solve the Multi-select conundrum and we maybe wouldn't need to come up with logic to handle mesh_select_mode 1,0,0, 1,1,0, 1,0,1, 1,1,1, 0,1,0, 0,1,1, and 0,0,1 all individually.
    # 
    # Also if I get my bmesh back in the main class I could move the if len(bm.select_history) == 0: test up there as well.
    # 
    # Maybe the way to do it would be, if active and previous are the same type, use that appropriate context_N_select.  If they are different, return cancelled UNLESS the active is an edge, in which case, fire off context_edge_select with special logic 
    # to skip all the tests and just select an edge loop (since it's a double click).  I could restructure that function to use Modes (loop, ring, bounded?) perhaps.  Even if I don't this will be the most complicated function of the 3 just due to the many different edge types and selections.
    if type(active_vert) is not bmesh.types.BMVert or type(previous_active_vert) is not bmesh.types.BMVert:
        return {'CANCELLED'}

    adjacent = previous_active_vert in get_neighbour_verts(active_vert)

    if not previous_active_vert.index == active_vert.index:
        # Do we want to do anything differently if the two verts are of different manifolds? Like if 1 is manifold and 1 is boundary do we grab a boundary loop for the mesh border or do we grab a manifold loop that's perpendicular to the boundary?  The same question applies to edge ring selections.
        # For the time being we currently are using the 2 adjacent verts to get an edge and using that edge's manifold-ness to determine what to do. (Which, in the case of 1 manifold vert and 1 boundary vert means we go perpendicular to boundary because the edge will be manifold.)
        if adjacent:
            active_edge = [e for e in active_vert.link_edges if e in previous_active_vert.link_edges][0]
            if active_edge.is_manifold:
                print("Selecting Vertex Loop")
                blark = time.perf_counter()
                new_sel = full_loop_vert_manifold(prefs, active_vert, active_edge)
                blork = time.perf_counter()
                print("full_loop_vert_manifold runtime: %.20f sec" % (blork - blark))
                for i in new_sel:
                    bm.verts[i].select = True
            # Instead of looping through vertices we totally cheat and use the two adjacent vertices to get an edge
            # and then use that edge to get an edge loop. The select_flush_mode (which we must do anyway)
            # near the end of context_vert_select will handle converting the edge loop back into vertices.
            elif active_edge.is_boundary:
                print("Selecting Boundary Edges Then Verts")
                boundary_edges = full_loop_boundary_edge(prefs, active_edge)
                for e in boundary_edges:
                    e.select = True
#                    bm.edges[i].select = True
        elif not adjacent:
            time_start = time.perf_counter()
            bounded_sel = get_bounded_selection(active_vert, previous_active_vert, mode='VERT')
            time_end = time.perf_counter()
            print("get_bounded_selection runtime: %.20f sec" % (time_end - time_start))
            if bounded_sel:
                print("Selecting Bounded Vertices")
                for i in bounded_sel:
                    bm.verts[i].select = True
            # If no loop contains both vertices, select linked.
            elif not bounded_sel and prefs.select_linked_on_double_click:
                print("No Bounded Selection")
                print("End of Line - Selecting Linked")
                if mode in ('SET', 'ADD'):
                    bpy.ops.mesh.select_linked_pick('INVOKE_DEFAULT', delimit=set())
                else:
                    print("Mode is Deselect")
                    bpy.ops.mesh.select_linked_pick('INVOKE_DEFAULT', delimit=set(), deselect=True)
#        else:
#            if prefs.select_linked_on_double_click:
#                print("Selecting Linked")
#                if mode in ('SET', 'ADD'):
#                    bpy.ops.mesh.select_linked_pick('INVOKE_DEFAULT', delimit=set())
#                else:
#                    print("Mode is Deselect")
#                    bpy.ops.mesh.select_linked_pick('INVOKE_DEFAULT', delimit=set(), deselect=True)
    else:
        if prefs.select_linked_on_double_click:
            print("Skip Tests - Selecting Linked")
            if mode in ('SET', 'ADD'):
                bpy.ops.mesh.select_linked_pick('INVOKE_DEFAULT', delimit=set())
            else:
                print("Mode is Deselect")
                bpy.ops.mesh.select_linked_pick('INVOKE_DEFAULT', delimit=set(), deselect=True)

    time_start = time.perf_counter()
    bm.select_history.add(active_vert)  # Re-add active_vert to history to keep it active.
#    bm.select_flush(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(me)
    time_end = time.perf_counter()
#    print("Time to Flush and update_edit_mesh: %.4f sec" % (time_end - time_start))
    return {'FINISHED'}


def context_face_select(context, mode):
    prefs = context.preferences.addons[__name__].preferences
    me = context.object.data
    bm = bmesh.from_edit_mesh(me)

    if len(bm.select_history) == 0:
        return {'CANCELLED'}

    active_face = bm.select_history.active
    previous_active_face = bm.select_history[len(bm.select_history) - 2]
    # Sanity check.  Make sure we're actually working with faces.
    if type(active_face) is not bmesh.types.BMFace or type(previous_active_face) is not bmesh.types.BMFace:
        return {'CANCELLED'}

    if len(active_face.verts) != 4 and len(previous_active_face.verts) != 4:
        quads = (0, 0)
    elif len(active_face.verts) == 4 and len(previous_active_face.verts) == 4:
        quads = (1, 1)
    elif len(active_face.verts) == 4 and len(previous_active_face.verts) != 4:
        quads = (1, 0)
    elif len(active_face.verts) != 4 and len(previous_active_face.verts) == 4:
        quads = (0, 1)

    adjacent = previous_active_face in get_neighbour_faces(active_face)

    if not previous_active_face.index == active_face.index and not quads == (0, 0):  # LOL I FOUND AN ISSUE. If you select 1 face and then Shift+Double Click on EMPTY SPACE it will trigger select_linked (if the pref is true) because LMB with no modifiers is the only keymap entry that has "deselect on nothing" by default. Can I even do anything?
        if adjacent and (quads == (1, 1) or prefs.allow_non_quads_at_ends):
            print("Selecting Face Loop")
            a_edges = active_face.edges
            p_edges = previous_active_face.edges
            ring_edge = [e for e in a_edges if e in p_edges][0]
            loop_faces = face_loop_from_edge(ring_edge, active_face)
            for i in loop_faces:
                bm.faces[i].select = True  # It only takes about 0.0180 sec to set 34,000 faces as selected.
        elif not adjacent and (quads == (1, 1) or prefs.allow_non_quads_at_ends):
            print("Faces Not Adjacent. Trying Bounded Selection")
            bounded_sel = get_bounded_selection(active_face, previous_active_face, mode='FACE')
            if bounded_sel:
                print("Selecting Bounded Faces")
                for i in bounded_sel:
                    bm.faces[i].select = True
            # If no loop contains both faces, select linked.
            elif not bounded_sel and prefs.select_linked_on_double_click:
                print("No Bounded Selection")
                print("End of Line - Selecting Linked")
                if mode in ('SET', 'ADD'):
                    bpy.ops.mesh.select_linked_pick('INVOKE_DEFAULT', delimit=set())
                else:
                    print("Mode is Deselect")
                    bpy.ops.mesh.select_linked_pick('INVOKE_DEFAULT', delimit=set(), deselect=True)
#        else:  # Catchall for if not prefs.allow_non_quads_at_ends
#            if prefs.select_linked_on_double_click:
#                print("Selecting Linked")
#                if mode in ('SET', 'ADD'):
#                    bpy.ops.mesh.select_linked_pick('INVOKE_DEFAULT', delimit=set())
#                else:
#                    print("Mode is Deselect")
#                    bpy.ops.mesh.select_linked_pick('INVOKE_DEFAULT', delimit=set(), deselect=True)
    else:
        if prefs.select_linked_on_double_click:
            print("Skip Tests - Selecting Linked")
            if mode in ('SET', 'ADD'):
                bpy.ops.mesh.select_linked_pick('INVOKE_DEFAULT', delimit=set())
            else:
                print("Mode is Deselect")
                bpy.ops.mesh.select_linked_pick('INVOKE_DEFAULT', delimit=set(), deselect=True)

    time_start = time.perf_counter()
    bm.select_history.add(active_face)
#    bm.select_flush(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(me)  # Takes about 0.0310 sec to both Flush and Update the mesh on a 333k face mesh.
    time_end = time.perf_counter()
#    print("Time to Flush and update_edit_mesh: %.4f sec" % (time_end - time_start))
    return {'FINISHED'}


def context_edge_select(context, mode):
    prefs = context.preferences.addons[__name__].preferences
    me = context.object.data
    bm = bmesh.from_edit_mesh(me)

    if len(bm.select_history) == 0:
        return {'CANCELLED'}

    active_edge = bm.select_history.active
    previous_active_edge = bm.select_history[len(bm.select_history) - 2]
    # Sanity check.  Make sure we're actually working with edges.
    if type(active_edge) is not bmesh.types.BMEdge or type(previous_active_edge) is not bmesh.types.BMEdge:
        return {'CANCELLED'}

    adjacent = previous_active_edge in get_neighbour_edges(active_edge)

    #If the previous edge and current edge are different we are doing a Shift+Double Click selection.
    # This could be a complete edge ring/loop, or partial ring/loop.
    if not previous_active_edge.index == active_edge.index:
        if adjacent:
            # If a vertex is shared then the active_edge and previous_active_edge are physically connected.
            # We want to select a full edge loop.
            if any([v for v in active_edge.verts if v in previous_active_edge.verts]):
                if active_edge.is_manifold:
                    print("Selecting Edge Loop")
#                    t0 = time.perf_counter()
                    loop_edges = full_loop_edge_manifold(active_edge)
#                    t1 = time.perf_counter()
#                    print("entire_loop runtime: %.20f sec" % (t1 - t0))  # Delete me later
                    for i in loop_edges:
                        bm.edges[i].select = True
                elif active_edge.is_boundary:
                    print("Selecting Boundary Edges")
                    boundary_edges = full_loop_boundary_edge(prefs, active_edge)
                    for e in boundary_edges:
                        e.select = True
#                        bm.edges[i].select = True
                elif active_edge.is_wire:
                    print("Selecting Wire Edges")
                    bpy.ops.mesh.loop_select('INVOKE_DEFAULT', extend=True)  # Need to get rid of this and write our own operator to handle wire loops that can get a loop and terminate if wire > 2 at a vertex.
            # If they're not connected but still adjacent then we want a full edge ring.
            else:
                print("Selecting Edge Ring")
                tame = time.perf_counter()
                ring_edges = edge_ring_from_edge(prefs, active_edge)
                tome = time.perf_counter()
                print("edge_ring_from_edge runtime: %.20f sec" % (tome - tame))  # Delete me later
                for i in ring_edges:
                    bm.edges[i].select = True
        # If we're not adjacent we have to test for bounded selections.
        elif not adjacent:
            print("Attempting Bounded Edge Selection")
            t0t = time.perf_counter()
            new_sel = get_bounded_selection(active_edge, previous_active_edge, mode='EDGE')  # 0.69s on my preferred test edges on the big mesh
            t1t = time.perf_counter()
            print("get_bounded_selection runtime: %.20f sec" % (t1t - t0t))  # Delete me later
            if new_sel:
                for i in new_sel:
                    bm.edges[i].select = True
            # For an edge that has loop of 36,000 and ring of 18,000: 0.68 to 0.697 sec compared to 0.75 to 0.79 for the old Loopanar way.
            else:
                if active_edge.is_manifold:
                    print("End of Line - Selecting Edge Loop")
                    tf = time.perf_counter()
                    loop_edges = full_loop_edge_manifold(active_edge)
                    td = time.perf_counter()
                    print("full_loop_edge_manifold runtime: %.20f sec" % (td - tf))  # Delete me later
                    for i in loop_edges:
                        bm.edges[i].select = True
                elif active_edge.is_boundary:
                    print("End of Line - Selecting Boundary Edges")
                    boundary_edges = full_loop_boundary_edge(prefs, active_edge)
                    for e in boundary_edges:
                        e.select = True
#                        bm.edges[i].select = True
                elif active_edge.is_wire:
                    print("End of Line - Selecting Wire Edges")
                    bpy.ops.mesh.loop_select('INVOKE_DEFAULT', extend=True)  # Need to get rid of this and write our own operator to handle wire loops that can get a loop and terminate if wire > 2 at a vertex.

    # I guess clicking an edge twice makes the previous and active the same? Or maybe the selection history is
    # only 1 item long.  Therefore we must be selecting a new loop that's not related to any previous selected edge.
    else:
        if active_edge.is_manifold:
            print("Skip Tests - Selecting Edge Loop")
            tx = time.perf_counter()
            loop_edges = full_loop_edge_manifold(active_edge)
            ty = time.perf_counter()
            print("full_loop_edge_manifold runtime: %.20f sec" % (ty - tx))  # Delete me later
            for i in loop_edges:
                bm.edges[i].select = True
        elif active_edge.is_boundary:
            print("Skip Tests - Selecting Boundary Edges")
            boundary_edges = full_loop_boundary_edge(prefs, active_edge)
            for e in boundary_edges:
                e.select = True
#                bm.edges[i].select = True
        elif active_edge.is_wire:
            print("Skip Tests - Selecting Wire Edges")
            if mode == 'SET':
                bpy.ops.mesh.loop_select('INVOKE_DEFAULT')  # Need to get rid of this and write our own operator to handle wire loops that can get a loop and terminate if wire > 2 at a vertex.
            else:
                bpy.ops.mesh.loop_select('INVOKE_DEFAULT', extend=True)  # Need to get rid of this and write our own operator to handle wire loops that can get a loop and terminate if wire > 2 at a vertex.


    # I have no idea why clearing history matters for edges and not for verts/faces, but it seems that it does.
    bm.select_history.clear()
    # Re-adding the active_edge to keep it active alters the way chained selections work so it's a user preference.
    if prefs.leave_edge_active:
        bm.select_history.add(active_edge)
#    bm.select_flush(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(me)
    return {'FINISHED'}


# Hey what this?
# https://developer.blender.org/diffusion/B/browse/master/release/scripts/startup/bl_operators/bmesh/find_adjacent.py


# Takes a vertex and returns a set of adjacent vertices.
def get_neighbour_verts(vertex):
    time_start = time.perf_counter()
    edges = vertex.link_edges  # There's no nonmanifold check
    relevant_neighbour_verts = {v for e in edges for v in e.verts if v != vertex}
    time_end = time.perf_counter()
    print("get_neighbour_verts runtime: %.10f sec" % (time_end - time_start))  # Delete me later
    return relevant_neighbour_verts


# Takes a face and returns a set of connected faces.
def get_neighbour_faces(face):
    time_start = time.perf_counter()
    face_edges = face.edges  # There's no nonmanifold check
    relevant_neighbour_faces = {f for e in face_edges for f in e.link_faces if f != face}
    time_end = time.perf_counter()
    print("get_neighbour_faces runtime: %.10f sec" % (time_end - time_start))  # Delete me later
    return relevant_neighbour_faces


# Takes an edge and returns a set of nearby edges.
# Optionally takes a mode and will return only components for that mode, otherwise returns all.
def get_neighbour_edges(edge, mode=''):
    time_start = time.perf_counter()
    prefs = bpy.context.preferences.addons[__name__].preferences
    if mode not in ['', 'LOOP', 'RING']:
        bpy.ops.wm.report_err(err_type = 'ERROR_INVALID_INPUT',
                              err_message = "ERROR: get_neighbour_edges mode must be one of: "
                              + "'', 'LOOP', or 'RING'")
        return {'CANCELLED'}

    edge_loops = edge.link_loops  # There are a couple of manifold checks below but there could stand to be more.
    edge_faces = edge.link_faces
    face_edges = {e for f in edge_faces for e in f.edges}

    ring_edges = []
    if len(edge_faces) == 1 or len(edge_faces) == 2:
        for f in edge_faces:
            if len(f.verts) == 4:
                # Get the only 2 verts that are not in the edge we start with.
                target_verts = [v for v in f.verts if v not in edge.verts]
                # Add the only edge that corresponds to those two verts.
                ring_edges.extend([e for e in f.edges
                                  if target_verts[0] in e.verts and target_verts[1] in e.verts])

    if edge.is_manifold:
        # Vertices connected to more or less than 4 edges are disqualified.
        loop_edges = [e for v in edge.verts for e in v.link_edges
                     if len(v.link_edges) == 4 and e.is_manifold and e not in face_edges]
    elif edge.is_boundary:
        edge_verts = edge.verts
        if not prefs.ignore_boundary_wires:
            loop_edges = []
            for v in edge_verts:
                linked_edges = v.link_edges
                for e in linked_edges:
                    if not any([e for e in linked_edges if e.is_wire]):
                        if e.is_boundary and e is not edge:
                            loop_edges.append(e)
        elif prefs.ignore_boundary_wires:
            loop_edges = [e for v in edge_verts for e in v.link_edges
                         if e.is_boundary and e is not edge]
    # There may be more that we can do with wires but for now this will have to do.
    elif edge.is_wire:
        loop_edges = []
        for vert in edge.verts:
            linked_edges = vert.link_edges
            if len(linked_edges) == 2:
                loop_edges.extend([e for e in linked_edges if e.is_wire and e is not edge])
    # Nonmanifold
    elif len(edge_faces) > 2:
        loop_edges = [e for v in edge.verts for e in v.link_edges
                     if not e.is_manifold and not e.is_wire and e not in face_edges]
                     
#    print("Edge Faces: " + str([f.index for f in edge_faces]))
#    print("Face Edges: " + str([e.index for e in face_edges]))
#    print("Loop Edges: " + str(loop_edges))
#    print("Ring Edges: " + str(ring_edges))

    relevant_neighbour_edges = set(ring_edges + loop_edges)
    time_end = time.perf_counter()
    print("get_neighbour_edges runtime: %.10f sec" % (time_end - time_start))  # Delete me later
    if mode == '':
        return relevant_neighbour_edges  # Returns a set.
    elif mode == 'LOOP':
        return loop_edges  # Returns a list, not a set. This is intentional.
    elif mode == 'RING':
        return ring_edges  # Returns a list, not a set. This is intentional.


# Deselect everything and select only the given component.
def select_component(component):
    bpy.ops.mesh.select_all(action='DESELECT')
    component.select = True


# Takes two components of the same type and returns a set of indices that are bounded between those two components.
def get_bounded_selection(component0, component1, mode):
    prefs = bpy.context.preferences.addons[__name__].preferences

    if not component0 or not component1 or component0.index == component1.index:
        bpy.ops.wm.report_err(err_type = 'ERROR_INVALID_INPUT',
                              err_message = "ERROR: You must supply two components of the same type and a mode.")
        return {'CANCELLED'}
    if mode not in ['VERT', 'EDGE', 'FACE']:
        bpy.ops.wm.report_err(err_type = 'ERROR_INVALID_INPUT',
                              err_message = "ERROR: get_bounded_selection mode must be one of "
                              + "'VERT', 'EDGE', or 'FACE'")
        return {'CANCELLED'}
    if type(component0) != type(component1):
        bpy.ops.wm.report_err(err_type = 'ERROR_INVALID_INPUT',
                              err_message = "ERROR: Both components must be the same type and "
                              + "must match the supplied mode.")
        # Fuck me if someone supplies a manifold edge and a wire edge.  Need to add sanity checks that if the type of both is edge, then both must also be is_manifold, is_boundary, or is_wire, or both have len(e.linked_faces) > 2
        return {'CANCELLED'}

    ends = [component0, component1]
    c0 = component0
    c1 = component1

    if mode == 'VERT':
        # Not implemented yet but if the len(v.link_edges) for one of the verts is 3 and the other is 4
        # we could maybe use the n=3 vert as the starting vert.
        # Official Blender definitions for non-manifold vertex.  Observe that a boundary vertex is not considered non-manifold.  It is considered manifold.  So I can't use vert.is_manifold to validate that a vertex is actually manifold.
        # So I likely need to run two layers of checks.  First make sure it isn't non-manifold, and then make sure that no edges are boundary.  The first check (non-manifold) should flag if we hit non-manifold extrusions or wire.
        # A vertex is non-manifold if it meets any of the following conditions:
        # 1: Loose - (has no edges/faces incident upon it).
        # 2: Joins two distinct regions - (two pyramids joined at the tip).
        # 3: Is part of an edge with more than 2 faces.
        # 4: Is part of a wire edge.
        
        if len(c0.link_edges) == 4:
            starting_vert = c0
        elif len(c0.link_edges) != 4 and len(c1.link_edges) == 4:
            starting_vert = c1
        elif len(c0.link_edges) != 4 and len(c1.link_edges) != 4:  # We have no valid path forward for boundary loops and wire loops.  We'll add those later on.  First I just want to get this working with manifold vert loops.
            return None

        connected_loops = get_bounded_verts_manifold(prefs, starting_vert, ends)

    if mode == 'EDGE':
        # Unlike face mode, edge mode has to contend with several different ways to advance through the loops to get lists.
        # So we can't just blindly fire off a set of the 2 loop edges and 2 ring edges, we actually need order.
        # The main two are loop and ring, but later on I also want to deal with boundary, and possibly wire and nonmanifold.
        
        # if both are manifold, fire off the bounded manifold code. (check bounded loop then ring)
        # elif both are boundary, fire off the bounded boundary code. (loop only)
        # elif both are wire, fire off the bounded wire code. (loop only)
        # elif both have linked faces > 2 fire off the spicy non-manifold loop code (loop only)
        # elif active.is_manifold and (prev.is_boundary or len(prev.link_faces) > 2) then fire off the bounded manifold ring code with active as start edge
        #     if it fails we return none and then externally fire the manifold loop code as the end of line action
        # elif prev.is_manifold and (active.is_boundary or len(active.link_faces) > 2) then fire off the bounded manifold ring code with prev as start edge
        #     if it fails we return none and externally fire off the boundary loop code or spicy non-manifold loop code as the end of line action
        # elif one is wire and the other is anything else, we retun none and externally fire off whatever is the appropriate loop code for its type.
        
        c0_faces = c0.link_faces
        c1_faces = c1.link_faces

        c0_loop_dirs = get_neighbour_edges(c0, mode='LOOP')  # edges
        c0_ring_dirs = get_neighbour_edges(c0, mode='RING')  # edges
        c1_loop_dirs = get_neighbour_edges(c1, mode='LOOP')  # edges
        c1_ring_dirs = get_neighbour_edges(c1, mode='RING')  # edges

        connected_loops = []
        if c0.is_manifold and c1.is_manifold:  # Manifold
#            if len(c0_faces) == 2:  # Works both for loops or rings
#                starting_edge = c0
#            elif len(c0_faces) != 2 and len(c1_faces) == 2:  # Rings can end on boundary edges
#                starting_edge = c1
#            elif len(c0_faces) != 2 and len(c1_faces) != 2:  # This doesn't leave any path forward for wire, boundary, or non-manifold.
#                return None

            starting_edge = c0
            
            if len(c0_loop_dirs):
                print("Trying bounded loop.")
                e0 = time.perf_counter()
                connected_loops = get_bounded_edge_loop_manifold(prefs, starting_edge, ends)  # Slightly faster
                e1 = time.perf_counter()
                print("get_bounded_edge_loop_manifold runtime: %.20f sec" % (e1 - e0))  # Delete me later
            if len(connected_loops) > 0:
                # Priority behavior is that if there is a positive match for a bounded loop selection then
                # return the loop selection. It doesn't care if there's an equal-length ring selection too.
                print("Found a loop")
                pass
            elif len(c0_ring_dirs):
                print("No loop. Trying bounded ring.")

                if any(map(lambda x: len(x.verts) != 4, c0_faces)):
                    starting_edge = c1

                e2 = time.perf_counter()
                connected_loops = get_bounded_edge_ring_manifold(prefs, starting_edge, ends)
                e3 = time.perf_counter()
                print("get_bounded_edge_ring_manifold runtime: %.20f sec" % (e3 - e2))  # Delete me later

        elif c0.is_boundary and c1.is_boundary:  # Boundary
            print("Attempting bounded boundary selection.")
            connected_loops = get_bounded_edge_loop_boundary(prefs, c0, ends)

        elif c0.is_wire and c1.is_wire:  # Wire
            return None  # For now, return no selection because I haven't written wire selector yet.

        elif len(c0_faces) > 2 and len(c1_faces) > 2:  # Non-manifold edge extrusion/intersection
            return None  # For now, return no selection because I haven't written non-manifold selector yet.

        elif c0.is_manifold and (c1.is_boundary or len(c1_faces) > 2):  # Only possible bounded selection is a ring.
            print("Attempting possible c0 ring. Trying bounded ring.")
            starting_edge = c0
            e2 = time.perf_counter()
            connected_loops = get_bounded_edge_ring_manifold(prefs, starting_edge, ends)
            e3 = time.perf_counter()
            print("get_bounded_edge_ring_manifold runtime: %.20f sec" % (e3 - e2))  # Delete me later

        elif c1.is_manifold and (c0.is_boundary or len(c0_faces) > 2):  # Only possible bounded selection is a ring.
            print("Attempting possible c1 ring. Trying bounded ring.")
            starting_edge = c1
            e2 = time.perf_counter()
            connected_loops = get_bounded_edge_ring_manifold(prefs, starting_edge, ends)
            e3 = time.perf_counter()
            print("get_bounded_edge_ring_manifold runtime: %.20f sec" % (e3 - e2))  # Delete me later

        elif (c0.is_wire and not c1.is_wire) or (c1.is_wire and not c0.is_wire):  # There is no conceivable condition where a wire edge can be part of any other type of loop or ring.
            return None

    if mode == 'FACE':
        # Not implemented yet but if one of the faces is a triangle and the other is a quad we could use the triangle
        # as our starting_face if the pref allows cause n=3 instead of n=4 to find out if the other face is connected
        if not prefs.allow_non_quads_at_ends and (len(c0.verts) != 4 or len(c1.verts) != 4):
            return None
        if len(c0.verts) == 4:
            starting_face = c0
        elif len(c0.verts) != 4 and len(c1.verts) == 4:
            starting_face = c1
        else:
#            print("Neither face is a quad.")
            return None

        connected_loops = get_bounded_face_loop(prefs, starting_face, ends)

    connected_loops.sort(key = lambda x: len(x))
#    print([len(r) for r in connected_loops])
    if len(connected_loops) == 0:
        return None
    elif len(connected_loops) == 1:
        return {i for i in connected_loops[0]}  # There might be a better way of returning the components in connected_loops than this.  connected_loops itself must be a list because I need to be able to sort it but the contents inside are already sets.
    # If multiple bounded loop candidates of identical length exist, this pref returns only the first loop.
    elif prefs.return_single_loop and len(connected_loops) > 1:
        return {i for i in connected_loops[0]}  # Because creating a new set from scratch that pulls every i from each loop is probably adding extra time.
    else:
        return {i for loop in connected_loops if len(loop) == len(connected_loops[0]) for i in loop}  # Maybe instead we could just merge the sets together rather than building a new set that contains i from all N sets.


# ##################### Bounded Selections ##################### #

# Takes 2 separated verts, and which vert to start with, and returns a list of loop lists of vertex indices.
def get_bounded_verts_manifold(prefs, starting_vert, ends):
    begintime = time.perf_counter()
    candidate_dirs = starting_vert.link_loops  # loops
    connected_loops = []
    reference_list = set()

    # There must be a clever way to skip running this 4 times if we bump into 1 or even 2 infinite loops.
    # 0. Get the 4 edges connected to the starting_vert  OR ACTUALLY USE THE LOOPS
    # 1. Designate the first edge as edge_a
    # 2. Use the BM_vert_step_fan_loop to get its opposite edge
    # 3. Eliminate edge_a and its opposite from the list in step 0
    # 4. Now pick either of the two remaining edges and designate it as edge_b
    # 5. Repeat step 2
    # 6. Get the edge.other_vert(starting_vert) for the edge_a edge pair and the edge_b edge pair
    # 7. With this information in hand, if we hit an infinite loop from edge_a to its opposite or edge_b to its opposite
    #    we can eliminate that opposite edge's loop from candidate_dirs since it will be wasted effort to get the same 
    #    infinite loop, just in the opposite direction.
    # 
    # The only caveat here is that I'm not sure if popping loops from candidate_dirs WHILE operating on candidate_dirs will break.
    # 
    # Also the same basic logic should be implemented for get_bounded_face_loop by picking the first loop belonging to the face 
    # and getting the loop.link_loop_radial_next.face (instead of the edge.other_vert) to check against
    # and then getting the first loop's loop.link_loop_next.link_loop_next.link_loop_radial_next.face for the opposite connected face
    # To move perpendicular to get the other face pair it's as easy as loop.link_loop_next since we're never leaving the starting face.
    for loop in candidate_dirs:
        starting_edge = loop.edge
        # What's the performance impact of .clear() and would it make much difference to just move reference_list = set() down here?
        reference_list.clear()  # delete me later maybe? This is an experimental idea to deal with unwanted early terminations from self-intersects but I have not tested the full ramifications.
        new_verts = partial_loop_vert(prefs, loop, starting_edge, starting_vert, reference_list, ends)
        if ends[0].index in new_verts and ends[1].index in new_verts:
            print("Appending new list.")
            connected_loops.append([c for c in new_verts])

    endtime = time.perf_counter()
    print("get_bounded_verts_manifold runtime: %.20f sec" % (endtime - begintime))  # Delete me later
    return connected_loops


# Takes 2 separated faces, and which face to start with, and returns a list of loop lists of face indices.
def get_bounded_face_loop(prefs, starting_face, ends):
    # Must use the face's loops instead of its edges because edge's loop[0] could point to a different face.
    candidate_dirs = starting_face.loops
    connected_loops = []
    reference_list = set()

    begintime = time.perf_counter()

    for loop in candidate_dirs:  # Theoretically there is potential for one or more of the loops to loop back on the starting component (infinite) and it would be wasteful to run the other loop but that's less likely in a bounded selection.
        reference_list.clear()  # delete me later maybe? This is an experimental idea to deal with unwanted early terminations from self-intersects but I have not tested the full ramifications.
        new_faces = partial_loop_face(prefs, loop, starting_face, reference_list, ends)
        if ends[0].index in new_faces and ends[1].index in new_faces:
            connected_loops.append([c for c in new_faces])

    endtime = time.perf_counter()
    print("get_bounded_face_loop runtime: %.20f sec" % (endtime - begintime))  # Delete me later
    return connected_loops


# Takes 2 separated edges, and which edge to start with, and returns a list of loop lists of edge indices.
def get_bounded_edge_loop_manifold(prefs, starting_edge, ends):
    starting_loop = starting_edge.link_loops[0]
    loops = [starting_loop, starting_loop.link_loop_next]
    connected_loops = []
    reference_list = set()

    for loop in loops:
        reference_list.clear()  # delete me later maybe? This is an experimental idea to deal with unwanted early terminations from self-intersects but I have not tested the full ramifications.
        tp = time.perf_counter()
        partial_list = partial_loop_edge(prefs, loop, starting_edge, reference_list, ends)
        tq = time.perf_counter()
        print("Time to get partial_list: %.20f sec" % (tq - tp))  # Delete me later
        if "infinite" not in partial_list:
            if ends[0].index in partial_list and ends[1].index in partial_list:
                connected_loops.append([c for c in partial_list])
                print("Connected Loop match. Adding partial_list to connected_loops.")
        else:
            break  # If we're infinite then there is no bounded selection to get
    return connected_loops


# Takes 2 separated edges, and which edge to start with, and returns a list of ring lists of edge indices.
def get_bounded_edge_ring_manifold(prefs, starting_edge, ends):
    print("ends:", [e.index for e in ends])
    print("Starting edge", starting_edge.index)
    starting_loop = starting_edge.link_loops[0]
    loops = [starting_loop, starting_loop.link_loop_radial_next]
    connected_loops = []
    reference_list = set()

    for loop in loops:
        reference_list.clear()  # delete me later maybe? This is an experimental idea to deal with unwanted early terminations from self-intersects but I have not tested the full ramifications.
        tp = time.perf_counter()
        partial_list = partial_ring_edge(prefs, loop, starting_edge, reference_list, ends)
        tq = time.perf_counter()
        print("Time to get partial_list: %.20f sec" % (tq - tp))  # Delete me later
        if "infinite" not in partial_list:
            if ends[0].index in partial_list and ends[1].index in partial_list:
                connected_loops.append([c for c in partial_list])
                print("Connected Loop match. Adding partial_list to connected_loops.")
        else:
            break  # If we're infinite then there is no bounded selection to get

#    if prefs.terminate_self_intersects and len(connected_loops) == 0:
#        print("Try the other edge.")
#        clear_tags(bm, mode='FACE')
#        other_edge = [e for e in ends if e is not starting_edge][0]
#        print("Other edge", other_edge.index)
#        starting_loop = other_edge.link_loops[0]
#        loops = [starting_loop, starting_loop.link_loop_radial_next]
#        for loop in loops:
#            tp = time.perf_counter()
#            partial_list = partial_ring_edge(prefs, loop, other_edge, ends)
#            tq = time.perf_counter()
#            print("Time to get partial_list: %.20f sec" % (tq - tp))  # Delete me later
#            if "infinite" not in partial_list:
#                if ends[0].index in partial_list and ends[1].index in partial_list:
#                    connected_loops.append([c for c in partial_list])
#                    print("Connected Loop match. Adding partial_list to connected_loops.")
#            else:
#                break  # If we're infinite then there is no bounded selection to get
    return connected_loops


# Takes 2 separated boundary edges, and which edge to start with, and returns a list of loop lists of edge indices.
def get_bounded_edge_loop_boundary(prefs, starting_edge, ends):
    connected_loops = []
    verts = starting_edge.verts

    for v in verts:
        tp = time.perf_counter()
        partial_list = partial_loop_edge_boundary(prefs, starting_edge, v, ends)
        tq = time.perf_counter()
        print("Time to get partial_list: %.20f sec" % (tq - tp))  # Delete me later
#        print("Partial list is:", [e.index for e in partial_list])
        if "infinite" not in partial_list:
#            partial_list.add(ends[1])  # 'Cause I'm a lazy bugger, here is a glorious hack.  Ugh, it doesn't work correctly with terminate_self_intersects.
            if ends[0] in partial_list and ends[1] in partial_list:
                connected_loops.append([c.index for c in partial_list])
                print("Connected Loop match. Adding partial_list to connected_loops.")
        else:
            break  # If we're infinite then there is no bounded selection to get
    return connected_loops


# ##################### Full Loop Selections ##################### #

# Takes a starting vertex and a connected reference edge and returns a full loop of vertex indices.
def full_loop_vert_manifold(prefs, starting_vert, starting_edge):
#    starting_loop = starting_edge.link_loops[0]
    edge_loops = starting_edge.link_loops
    candidates = [loop for loop in edge_loops if loop.vert == starting_vert]
    if len(candidates) > 0:
        starting_loop = candidates[0]
    else:
        starting_loop = edge_loops[0]
    loops = [starting_loop, starting_loop.link_loop_next]
    vert_list = set()
    reference_list = set()

    for loop in loops:
        starting_vert = loop.vert
        new_verts = partial_loop_vert(prefs, loop, starting_edge, starting_vert, reference_list)
        if "infinite" not in new_verts:
            vert_list.update(new_verts)
        else:
            new_verts.discard("infinite")
            vert_list.update(new_verts)
            break  # Early out so we don't get the same loop twice.
    endtime = time.perf_counter()
    return vert_list


# Takes an edge and returns a loop of face indices (as a set) for the ring direction of that edge.
def face_loop_from_edge(edge, face):
    t0 = time.perf_counter()  # Delete me later
    if len(edge.link_loops) > 2:
        return []

    prefs = bpy.context.preferences.addons[__name__].preferences
    starting_loop = [loop for loop in edge.link_loops if loop in face.loops][0]
    loops = [starting_loop, starting_loop.link_loop_radial_next]
    face_list = set()  # Checking for membership in sets is faster than lists []
    reference_list = set()

    for loop in loops:
        starting_face = loop.face
        new_faces = partial_loop_face(prefs, loop, starting_face, reference_list)
        if "infinite" not in new_faces:
            face_list.update(new_faces)
        else:
            new_faces.discard("infinite")
            face_list.update(new_faces)
            break  # Early out so we don't get the same loop twice.
    t1 = time.perf_counter()
    print("face_loop_from_edge runtime: %.20f sec" % (t1 - t0))  # Delete me later
    return face_list

# Takes an edge and returns a full loop of edge indices.
def full_loop_edge_manifold(edge):
    t0 = time.perf_counter()  # Delete me later
    starting_loop = edge.link_loops[0]
    loops = [starting_loop, starting_loop.link_loop_next]

    prefs = bpy.context.preferences.addons[__name__].preferences
    edge_list = set()  # Checking for membership in sets is faster than lists []
    reference_list = set()

    for loop in loops:
        new_edges = partial_loop_edge(prefs, loop, edge, reference_list)
        if "infinite" not in new_edges:
            edge_list.update(new_edges)
        else:
            new_edges.discard("infinite")
            edge_list.update(new_edges)
            break  # Early out so we don't get the same loop twice.
    t1 = time.perf_counter()
    print("full_loop_edge_manifold runtime: %.20f sec" % (t1 - t0))  # Delete me later
    return edge_list


# Takes an edge and returns a ring of edge indices (as a set) for that edge.
def edge_ring_from_edge(prefs, starting_edge):
    starting_loop = starting_edge.link_loops[0]
    loops = [starting_loop, starting_loop.link_loop_radial_next]
    edge_list = set()
    reference_list = set()

    for loop in loops:
        tp = time.perf_counter()
        partial_list = partial_ring_edge(prefs, loop, starting_edge, reference_list)
        tq = time.perf_counter()
        print("Time to get partial_list: %.20f sec" % (tq - tp))  # Delete me later
        if "infinite" not in partial_list:
            edge_list.update(partial_list)
        else:
            partial_list.discard("infinite")
            edge_list.update(partial_list)
            break  # Early out so we don't get the same loop twice.
    print("Length of list:", len(edge_list))
    return edge_list


# Takes a boundary edge and returns a list of boundary edge indices.
def full_loop_boundary_edge(prefs, edge):
    t0 = time.perf_counter()  # Delete me later
    verts = edge.verts
    edge_list = set()

    for v in verts:
        new_edges = partial_loop_edge_boundary(prefs, edge, v)
        if "infinite" not in new_edges:
            edge_list.update(new_edges)
        else:
            print("Discard infinite.")
            new_edges.discard("infinite")
            edge_list.update(new_edges)
            break  # Early out so we don't get the same loop twice.
    t1 = time.perf_counter()
    print("full_loop_boundary_edge runtime: %.20f sec" % (t1 - t0))  # Delete me later
    return edge_list


# ##################### Partial Loop (Fragment) Selections ##################### #

"""Write a better description than this."""
# Takes a loop, reference edge, reference vertex, and returns a set of edge indices starting at the edge until reaching a dead end
def partial_loop_vert(prefs, loop, starting_edge, starting_vert, reference_list, ends=''):
    e_step = starting_edge
    pcv = starting_vert  # Previous Current Vert (loop's vert)
    pov = starting_edge.other_vert(pcv)  # Previous Other Vert
    partial_list = {pcv.index}
    if not ends:
        reference_list.add(pov.index)
    while True:
        next_loop = BM_vert_step_fan_loop(e_step, loop)  # Pass the edge and its starting vert to loop_extension
        if next_loop:  # If loop_extension returns an edge, keep going.
            e_step = next_loop.edge
            
            # Can't reliably use loop_radial_next.vert as oth_vert because sometimes it's the same vert as cur_vert
            cur_vert = next_loop.vert
            oth_vert = next_loop.edge.other_vert(next_loop.vert)
            rad_vert = next_loop.link_loop_radial_next.vert

            if cur_vert == rad_vert and oth_vert != pcv:
                loop = next_loop.link_loop_next
                pcv = oth_vert
                pov = cur_vert
            elif oth_vert == pcv:
                loop = next_loop
                pcv = cur_vert
                pov = oth_vert
            elif cur_vert ==  pcv:
                loop = next_loop.link_loop_radial_next
                pcv = oth_vert
                pov = cur_vert
            else:
                print("Y U NO GO?")
                bpy.ops.wm.report_err(err_type = 'ERROR',
                                      err_message = "ERROR: Wot in Tarnation is this?")
                return {'CANCELLED'}

            reference_list.add(pov.index)
#            ts = time.perf_counter()
            # Check to see if next component matches dead end conditions
            if not ends:
                dead_end = dead_end_vert(prefs, pcv, e_step, starting_vert, partial_list, reference_list)
            else:
                dead_end = dead_end_vert(prefs, pcv, e_step, starting_vert, partial_list, reference_list, ends)
#            te = time.perf_counter()
#            print("dead_end runtime: %.20f sec" % (te - ts))  # Delete me later

            # Add component to list.
            if not prefs.ignore_hidden_geometry and not e_step.hide:  # This is a very un-ideal way to do this.
                partial_list.add(pcv.index)  # It would be better if the dead_end test could break before here.
            elif prefs.ignore_hidden_geometry:
                partial_list.add(pcv.index)

            if dead_end:
                break

        else:  # finite and we've reached an end
            break
    print("Length of partial vertex list:", len(partial_list))
    return partial_list  # Return the completed loop


# Takes a BMesh loop and its connected starting face and returns a loop of face indices until hitting a dead end.
# For a bounded selection between two faces it also requires the two end faces for dead end validation.
def partial_loop_face(prefs, cur_loop, starting_face, reference_list, ends=''):
    partial_list = {starting_face.index}
    while True:
        # Jump to next loop on the same edge and walk two loops forward (opposite edge)
        next_loop = cur_loop.link_loop_radial_next.link_loop_next.link_loop_next
        next_face = next_loop.face

        # Check to see if next component matches dead end conditions
        if not ends:
            dead_end = dead_end_face(prefs, cur_loop, next_loop, next_face, starting_face, partial_list, reference_list)
        else:
            dead_end = dead_end_face(prefs, cur_loop, next_loop, next_face, starting_face, partial_list, reference_list, ends)

        # This probably needs a proper sanity check to make sure there even is a face before we try to call the verts of said face.
        # Same for if the loop even has faces to link to.  Maybe move the edge.link_faces test to the front?
        # I think Loopanar maybe has a manifold check somewhere in the Loop selection (not ring) regarding free-floating edges with no faces.

        # Add component to list.
        if next_face.index not in partial_list:
            if len(next_face.verts) == 4:
                partial_list.add(next_face.index)
            elif prefs.allow_non_quads_at_ends:
                partial_list.add(next_face.index)
        reference_list.add(next_face.index)
        if dead_end:
            break
        # Run this part always
        cur_loop = next_loop
    print("Length of partial face list:", len(partial_list))
    return partial_list


# Takes a loop and reference edge and returns a set of edge indices starting at the edge until reaching a dead end
def partial_loop_edge(prefs, loop, starting_edge, reference_list, ends=''):
    e_step = starting_edge
    pcv = loop.vert  # Previous Current Vert (loop's vert)
    pov = loop.edge.other_vert(loop.vert)  # Previous Other Vert
    partial_list = {starting_edge.index}
    if not ends:
        reference_list.add(pov.index)
    # For these functions that include a reference_list I should test right at the beginning to see if the terminate_self_intersects
    # pref is true and only create and add components to the reference_list if it's true, if that's possible..
    while True:
        next_loop = BM_vert_step_fan_loop(e_step, loop)  # Pass the edge and its starting vert to loop_extension
        if next_loop:  # If loop_extension returns an edge, keep going.
            e_step = next_loop.edge

            # Can't reliably use loop_radial_next.vert as oth_vert because sometimes it's the same vert as cur_vert
            cur_vert = next_loop.vert
            oth_vert = next_loop.edge.other_vert(next_loop.vert)
            rad_vert = next_loop.link_loop_radial_next.vert

            if cur_vert == rad_vert and oth_vert != pcv:
                loop = next_loop.link_loop_next
                pcv = oth_vert
                pov = cur_vert
            elif oth_vert == pcv:
                loop = next_loop
                pcv = cur_vert
                pov = oth_vert
            elif cur_vert ==  pcv:
                loop = next_loop.link_loop_radial_next
                pcv = oth_vert
                pov = cur_vert
            else:
                print("Y U NO GO?")
                bpy.ops.wm.report_err(err_type = 'ERROR',
                                      err_message = "ERROR: Wot in Tarnation is this?")
                return {'CANCELLED'}

            reference_list.add(pov.index)
#            ts = time.perf_counter()
            # Check to see if next component matches dead end conditions
            if not ends:
                dead_end = dead_end_loop(prefs, e_step, pcv, starting_edge, partial_list, reference_list)
            else:
                dead_end = dead_end_loop(prefs, e_step, pcv, starting_edge, partial_list, reference_list, ends)
#            te = time.perf_counter()
#            print("dead_end runtime: %.20f sec" % (te - ts))  # Delete me later

            # Add component to list.
            partial_list.add(e_step.index)
 
            if dead_end:
                break

        else:  # finite and we've reached an end
            break
    print("Length of partial edge list:", len(partial_list))
    return partial_list  # Return the completed loop


# Takes a loop and starting edge and returns a set of edge indicies starting at the edge until reaching a dead end
def partial_ring_edge(prefs, starting_loop, starting_edge, reference_list, ends=''):
    cur_loop = starting_loop
    partial_list = {starting_edge.index}
    while True:
        # Get next components
#        next_loop = ring_extension(cur_loop)
        next_loop = cur_loop.link_loop_radial_next.link_loop_next.link_loop_next
        if next_loop:
            next_edge = next_loop.edge
            next_face = next_loop.face

            # Check to see if next component matches dead end conditions
            if not ends:
                dead_end = dead_end_ring(prefs, next_edge, next_face, starting_edge, partial_list, reference_list)
            else:
                dead_end = dead_end_ring(prefs, next_edge, next_face, starting_edge, partial_list, reference_list, ends)

            # Add component to list.
            if next_edge.index not in partial_list:  # Hold up, do I even need to test this? It's a set, so why bother?
                if len(next_face.verts) == 4:
                    if not prefs.ignore_hidden_geometry and not next_face.hide:  # This is a very un-ideal way to do this.
                        partial_list.add(next_edge.index)  # It would be better if the dead_end test could break before here.
                    elif prefs.ignore_hidden_geometry:
                        partial_list.add(next_edge.index)
                reference_list.add(next_face.index)
            if dead_end:  # I can't place this BEFORE the adding components to lists because it will break bounded selections.
                break
        else:  # finite and we've reached an end
            break
        cur_loop = next_loop
    print("Length of partial edge list:", len(partial_list))
    return partial_list  # Return the completed loop


# Takes an edge and connected vertex and returns a set of boundary edges starting at the edge until reaching a dead end
def partial_loop_edge_boundary(prefs, starting_edge, starting_vert, ends=''):
    cur_edges = [starting_edge]
    final_selection = set()
    visited_verts = {starting_vert}
#    print("==========BEGIN!==========")
#    print("starting_edge:", starting_edge.index)
    loop = 0
    while True:
        edge_verts = [v for e in cur_edges for v in e.verts if v not in visited_verts]
        new_edges = []
        for v in edge_verts:
            linked_edges = {e for e in v.link_edges if e.is_boundary or e.is_wire}  # is_intersect set to > 2
            for e in linked_edges:
#                print("e:", e.index)
                if not ends:
                    dead_end = dead_end_boundary_edge(prefs, e, v, starting_edge, linked_edges, final_selection)
                else:
                    dead_end = dead_end_boundary_edge(prefs, e, v, starting_edge, linked_edges, final_selection, ends)
                if dead_end:  # This might be wrong logic but I need a way to NOT add the edge if it is hidden.
                    visited_verts.add(v)  # but this might leave 1 edge not selected. But it prevents the edge from being used in cur_edges
                else:
                    visited_verts.add(v)
                    if e not in final_selection and not e.is_wire:
                        new_edges.append(e)

        # Idea for insane wild goose chase:
#        linked_edges = [[e for e in v.link_edges if not e.is_manifold] for v in edge_verts]
#        alt_edges = [e for v in edge_verts for x in linked_edges for e in x if not dead_end_boundary_edge(prefs, e, v, startingg_edge, linked_edges) and e.is_boundary and e not in final_selection]

        final_selection.update(new_edges)

        if len(new_edges) == 0:
#            print("Break!")
            break
        else:
#            print("Next Edges: " + str([e.index for e in new_edges]))
            cur_edges = new_edges
            if loop == 1:  # This is a stupid hack but I need to be able to iterate the first edge again
                visited_verts.discard(starting_vert)
#                final_selection.discard(starting_edge)
            loop +=1
#            print("-----Loop-----")
#    print("Boundary edge indices are: " + str(final_selection))
    return final_selection


# ##################### Dead End conditions ##################### #

def dead_end_vert(prefs, vert, edge, starting_vert, vert_list, reference_list, ends=''):
    if not ends:  # For non-bounded selections.
        # Loop is infinite and we're done
        reached_end = vert.index == starting_vert.index
        if reached_end:
            print("Unbounded Infinity?")
            vert_list.add("infinite")  # NOTE: This must be detected and handled/discarded externally.
    else:  # For bounded selections between 2 edges.
        # Looped back on self, or reached other component in a bounded selection
        reached_end = vert.index == ends[0].index or vert.index == ends[1].index
        if reached_end:
            print("Found the end.")
            if vert.index == starting_vert.index:
                print("Bounded is Infinity?")
#                vert_list.add("infinite")  # NOTE: This must be detected and handled/discarded externally.
    # Self-intersecting loop and pref doesn't allow it
    is_intersect = prefs.terminate_self_intersects and vert.index in reference_list
    if is_intersect:  # Should this be removed from the reference_list?
        print("Vert", vert.index, "in reference_list.")
#        reference_list.remove(vert.index)
    # Vertex/edge is hidden and pref to ignore hidden geometry isn't enabled
    is_hidden = not prefs.ignore_hidden_geometry and (vert.hide or edge.hide)
    return reached_end or is_intersect or is_hidden


def dead_end_face(prefs, cur_loop, next_loop, next_face, starting_face, face_list, reference_list, ends=''):
    if not ends:  # For non-bounded selections.
        # Loop is infinite and we're done
        reached_end = next_face.index == starting_face.index
        if reached_end:
            print("Infinity?")
            face_list.add("infinite")  # NOTE: This must be detected and handled/discarded externally.
    else:  # For bounded selections between 2 faces.
        # Looped back on self, or reached other component in a bounded selection
        reached_end = next_face.index == ends[0].index or next_face.index == ends[1].index

    # Self-intersecting loop and pref doesn't allow it
    is_intersect = prefs.terminate_self_intersects and next_face.index in reference_list
#    if is_intersect:  # Delete me later probably. Should this get removed from the reference_list?
#        next_face.tag = False
    # Face is hidden and pref to ignore hidden geometry isn't enabled
    is_hidden = not prefs.ignore_hidden_geometry and next_face.hide
    # Triangle or n-gon
    is_non_quad = len(next_face.verts) != 4
    # Non-manifold OR mesh boundary (neither case is manifold)
#    is_non_manifold = len(cur_loop.edge.link_faces) != 2 or len(next_loop.edge.link_faces) != 2  # This could potentially be replaced by checking if cur_loop == link_loop_radial_next for mesh boundaries, but that would not help for non-manifold. OR we chould just check if loop.edge.is_manifold because nonmanifold and mesh boundary are both considered nonmanifold.
    is_non_manifold = not cur_loop.edge.is_manifold or not next_loop.edge.is_manifold
    return reached_end or is_intersect or is_hidden or is_non_quad or is_non_manifold


def dead_end_loop(prefs, edge, vert, starting_edge, edge_list, reference_list, ends=''):
    if not ends:  # For non-bounded selections.
        # Loop is infinite and we're done
        reached_end = edge.index == starting_edge.index
        if reached_end:
            print("Infinity?")
            edge_list.add("infinite")  # NOTE: This must be detected and handled/discarded externally.
    else:  # For bounded selections between 2 edges.
        # Looped back on self, or reached other component in a bounded selection
        reached_end = edge.index == ends[0].index or edge.index == ends[1].index
        if reached_end:
            print("Found the end.")
            if edge.index == starting_edge.index:
                print("Infinity?")
                edge_list.add("infinite")  # NOTE: This must be detected and handled/discarded externally.

    # Self-intersecting loop and pref doesn't allow it
    is_intersect = prefs.terminate_self_intersects and vert.index in reference_list
    if is_intersect:
        print("intersect")
    # Vertex/edge is hidden and pref to ignore hidden geometry isn't enabled
    is_hidden = not prefs.ignore_hidden_geometry and (vert.hide or edge.hide)
    return reached_end or is_intersect or is_hidden


def dead_end_ring(prefs, edge, face, starting_edge, edge_list, reference_list, ends=''):
    if not ends:  # For non-bounded selections.
        # Loop is infinite and we're done
        reached_end = edge.index == starting_edge.index
        if reached_end:
            print("Infinity?")
            edge_list.add("infinite")  # NOTE: This must be detected and handled/discarded externally.
    else:  # For bounded selections between 2 edges.
        # Looped back on self, or reached other component in a bounded selection
        reached_end = edge.index == ends[0].index or edge.index == ends[1].index
        if reached_end:
            print("Found the end.")
            if edge.index == starting_edge.index:
                print("Infinity?")
                edge_list.add("infinite")  # NOTE: This must be detected and handled/discarded externally.

    # Self-intersecting loop and pref doesn't allow it
    is_intersect = prefs.terminate_self_intersects and face.index in reference_list
#    if is_intersect:  # Delete me later probably.  Should this get removed from the reference_list?
#        face.tag = False
    # Face/edge is hidden and pref to ignore hidden geometry isn't enabled
    is_hidden = not prefs.ignore_hidden_geometry and (face.hide or edge.hide)  # Note: Can't hide an edge connected to a face in Blender without the face also being hidden.
#    # Triangle or n-gon
    is_non_quad = len(face.verts) != 4  # I think the ring_extension may already be taking care of this?  It seems to work fine without this test.
    # Non-manifold OR mesh boundary (neither case is manifold)
    is_non_manifold = not edge.is_manifold

    return reached_end or is_intersect or is_hidden or is_non_quad or is_non_manifold


def dead_end_boundary_edge(prefs, edge, vert, starting_edge, linked_edges, edge_list, ends=''):
    if not ends:  # For non-bounded selections.
        # Loop is infinite and we're done
        reached_end = starting_edge in edge_list and edge.index == starting_edge.index
        if reached_end:
            print("Infinity?")
            edge_list.add("infinite")  # NOTE: This must be detected and handled/discarded externally.

        # Self-intersecting loop and pref doesn't allow it
        is_intersect = prefs.terminate_self_intersects and len([e for e in linked_edges if e.is_boundary]) > 2
    else:  # For bounded selections between 2 edges.
        # Looped back on self, or reached other component in a bounded selection
        reached_end = starting_edge in edge_list and edge.index == ends[0].index or edge.index == ends[1].index
        if reached_end:
            print("Found the end.")
            edge_list.add(edge)  # This is a dumb hack but the upstream function won't work otherwise.
            if starting_edge in edge_list and edge.index == starting_edge.index:
                print("Infinity?")
                edge_list.add("infinite")  # NOTE: This must be detected and handled/discarded externally.

        # For bounded selections, we always terminate here because it's too complicated to grok otherwise
        is_intersect = len([e for e in linked_edges if e.is_boundary]) > 2

    # Vertex/edge is hidden and pref to ignore hidden geometry isn't enabled
    is_hidden = not prefs.ignore_hidden_geometry and (vert.hide or edge.hide)
    # Vertex on the mesh boundary is connected to a wire edge and pref to ignore wires isn't enabled
    is_wire = not prefs.ignore_boundary_wires and any([e for e in linked_edges if e.is_wire])
    return reached_end or is_intersect or is_hidden or is_wire


# ##################### Walker Functions ##################### #

def face_extension(loop):
    # Jump to next loop on the same edge and walk two loops forward (opposite edge)
    next_loop = loop.link_loop_radial_next.link_loop_next.link_loop_next
    return next_loop


# Loop extension converted from Blender's internal functions.
def BM_vert_step_fan_loop(edge, loop):
    if len(loop.vert.link_loops) != 4:
        return None
    e_prev = edge
    if loop.edge == e_prev:
        e_next = loop.link_loop_prev.edge
    elif loop.link_loop_prev.edge == e_prev:
        e_next = loop.edge
    else:
        print("Unable to find a match.")
        return None

    if e_next.is_manifold:
        return BM_edge_other_loop(e_next, loop)
    else:
        print("Nonmanifold edge.")
        return None


def BM_edge_other_loop(edge, loop):
    ### Pseudo-python. (there isn't an "edge.loop" in the bmesh python API so we'd need a bit more work but I'm skipping asserts for now)
    # if edge.loop and edge.loop.link_loop_radial_next != edge.loop:
    # if BM_vert_in_edge(edge, loop.vert) ### I can't actually find where this is defined in the source code.. just several places where it's used.

    if loop.edge == edge:
        l_other = loop
    else:
        l_other = loop.link_loop_prev
    l_other = l_other.link_loop_radial_next

#    if l_other.edge == edge:
#        print("We would assert here.")  # Skipping asserts for now.

    if l_other.vert == loop.vert:
        l_other = l_other.link_loop_prev  # Modified this one spot to get link_loop_prev instead of pass because that seemed to fix at least 1 broken case
#        pass
    elif l_other.link_loop_next.vert == loop.vert:
        l_other = l_other.link_loop_next
    else:
        print("No matche, got stuck!")  # Skipping asserts for now.  We'll just print some nonsense instead.
        return None
    return l_other


# ##################### Loopanar defs ##################### #

def loop_extension(edge, vert):
    candidates = vert.link_edges[:]
    # For certain topology link_edges and link_loops return different numbers.
    # So we have to use link_loops for our length test, otherwise somehow we get stuck in an infinite loop.
    if len(vert.link_loops) == 4 and vert.is_manifold:
        # Note: Performance testing showed cruft to be slightly faster as a list, not a set.
        # About 0.54 sec vs 0.6 sec on a 333k vert mesh with a 34k loop in one way and 17k perpendicular.
        cruft = [edge]  # The next edge obviously can't be the current edge.
        for loop in edge.link_loops:
            # The 'next' and 'prev' edges are perpendicular to the desired loop so we don't want them.
            cruft.extend([loop.link_loop_next.edge, loop.link_loop_prev.edge])
        # Therefore by process of elimination there are 3 unwanted edges in cruft and only 1 possible edge left.
        return [e for e in candidates if e not in cruft][0]
    else:
        return


def loop_end(edge):
    # What's going on here?  This looks like it's assigning both vertices at once from the edge.verts
    v1, v2 = edge.verts[:]
    # And returns only one of them depending on the result from loop_extension?
    # I guess if loop_extension returns true, don't return that one?
    return not loop_extension(edge, v1) or not loop_extension(edge, v2)

def ring_extension(loop):
    if len(loop.face.verts) == 4:
        return loop.link_loop_radial_next.link_loop_next.link_loop_next
    else:
        # Otherwise the face isn't a quad.. return nothing to partial_ring.
        return

# Possible improvements: If ring_end took a loop.. we could determine Border if loop.link_loop_radial_next == loop I think.
# Or, we could knock out border and non_manifold by just checking if the loop.edge.is_manifold
# But the way loopanar is structured we only have edges to work with here.  Otherwise we could loop.face and check the verts.
# Which, itself, complicates whether we're measuring the next face or current face verts.
def ring_end(edge):
    faces = edge.link_faces[:]
    border = len(faces) == 1  # If only one face is connected then this edge must be the border of the mesh.
    non_manifold = len(faces) > 2  # In manifold geometry one edge can only be connected to two faces.
    dead_ends = map(lambda x: len(x.verts) != 4, faces)
    return border or non_manifold or any(dead_ends)



def register():
    for every_class in classes:
        bpy.utils.register_class(every_class)
    register_keymap_keys()


def unregister():
    for every_class in classes:
        bpy.utils.unregister_class(every_class)
    unregister_keymap_keys()


if __name__ == "__main__":
    register()
