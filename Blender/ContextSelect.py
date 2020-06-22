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
    "description": "Maya-style loop selection for vertices, edges, and faces.",
    "author": "Andreas Strømberg, nemyax, Chris Kohl",
    "version": (0, 1, 5),
    "blender": (2, 80, 0),
    "location": "",
    "warning": "Dev Branch. Somewhat experimental features. Possible performance issues.",
    "wiki_url": "https://github.com/MightyBOBcnc/Scripts/tree/Loopanar-Hybrid/Blender",
    "tracker_url": "https://github.com/MightyBOBcnc/Scripts/issues",
    "category": "Mesh"
}

# ToDo: 
# Write own select_linked function. :(  We must do so if we want to get rid of all uses of real deselection.  Say one object mesh has multiple detached pieces, each with only a partial selection, and we want to select_linked for only ONE of the pieces.
#     Blender's select_linked will run on ALL of the pieces that have a partial selection, not purely on the active component.
# Fully implement checks for hidden geometry and prefs.ignore_hidden_geometry option. (Still need to test with instanced geometry.)
#     And then tell this guy about it: https://blender.community/c/rightclickselect/ltbbbc/
# Add some more robust checks to validate against nonmanifold geometry like more than 2 faces connected to 1 edge and such.
#    And--in appropriate places--tests like component.is_manifold, component.is_boundary, and (for edges only, I think) e.is_wire
# Do some speed tests on some of these functions to measure performance.  There's always a push/pull between the speed of C when using native Blender operators, the extra overhead of doing real selections and mode switches, and using python bmesh without doing real selections or mode switches.
# Implement deselection for all methods of selection (except maybe select_linked).
#    This is actually going to be problematic because we need to track the most recent DEselected component, which Blender does not do.
#    This addon only executes on double click.  We would have to build a helper function using the @persistent decorator to maintain a deselection list (even if said list is only 2 members long).
#    And we would have to replace the regular view3d.select operator in at least 1 place (whatever the keymap is for deselecting; e.g. Ctrl+Click.. or Shift+Click if it's set to Toggle?)
#    And Blender's wonky Undo system would invalidate the deselection list although that MAY not be a problem for something as simple as tracking only 2 components.
# Find out if these selection tools can be made to work in the UV Editor. (NOTE: Probably need to set double click and shift double click operators for the UV section if the key map editor)
# Something is not working right if you're working on more than one object at a time in edit mode.  It will deselect components on all objects that aren't the most recent object you were working on.
#    I checked the original version of the script and this has apparently always been the case and I just didn't notice.  So that's something to investigate now; how to retain selection across multiple objects in edit mode.
#    If I had to guess this is probably because of all the instances where the script runs select_face, select_edge, and select_vert where it deselects everything, and probably also the times where we switch selection modes (vert, edge, face), and also because we're not getting a selection to restore per object.
#    So if we could get everything done with bmesh without doing real selections I *think* we could just add to existing selection which wouldn't clear selections and hopefully then we wouldn't even need to get a list of selected components to restore at all, much less per object.
# Write own loop/ring selection function for wire edges.  Loops will be easy because I don't think we have to worry about normal vector direction?  Rings will be harder because there's no face loop?  Or maybe it's the same with loop radial and then walk forward twice.  We'll see.
#    After looking into this, this is actually much harder than I thought it would be.  Rings might be impossible, loops are HARD unless it's just a single loop (only 2 edges per vertex like the Circle object).  Will need extra steps and 2 or 3-level deep testing.
# Bounded edge loop selection on a floating edge ring like the Circle primitive type. (Wire edges.)
# Bounded edge loop selection on a mesh's boundary edges. (This is gonna be harder? Need a Loopanar-like solution that can measure gaps.)
#    Note: Interestingly Maya doesn't do bounded vertex loop selection on a boundary loop.  It does a select_linked instead.
# Possible new user preferences:
#    Terminate self-intersecting loops and rings at crossing point.
#        Successfully implemented this for face loops and bounded vertices!  (The hardest part will be retrofitting this onto Loopanar for edge loops and rings.)
#        Self-intersects can happen with vertex loops, face loops, edge loops, edge rings, boundary edge loops (although boundary loops would need terrible topology it is still possible), and wire edge loops
#        Self-intersect at a boundary edge could be a +-shaped cross like extruding edges straight up from a grid, or it could be like deleting two diagonal quads in a grid so that 1 vert is shared by 2 diagonals but all 4 edges are boundary.
#    Allow user to specify which select_linked method they want to use on double click? (from a dropdown list)  Or, instead maybe forcibly pop up the delimit=set() in the corner instead?  Hmm but it doesn't appear to always force the popup?
#    A method and user preference to allow non-manifold edge loop selection?  e.g. a way to select an entire non-manifold loop of edges where an edge loop extrusion has been done in the middle of a grid; should be easy to code, it's the same as the boundary edge code except we ONLY want non-manifold edges.
#    Preference to not use bm.select_flush_mode() at the end of the functions? This would make it sort of more like Maya but in order to make it truly like Maya you'd have to replace all the regular view3d.select operators as well.
# Consolidate redundant code.  I still haven't figured out a proper way to do this since the main loop-getting functions are almost identical but with different methods for getting the next component and testing for dead ends...
# Investigate adding keymap entries automatically in the add-on preferences and/or the main keymap preferences.  What I know for certain is that the way Cirno's Box Select X-Ray add-on seems extraordinarily complicated and straight up does not work when I try to use his add-on (I always have to hard-code my defaults).
# Investigate doing our own raycasting. 
#    This would be needed if we want DEselection because Blender has no 'deselection history' list. Unless we want to compare the selection history for every view3d.select click but that would be much messier.
#    It is also a solution for the bug where double clicking on empty space causes a selection (although that one could alternatively be solved by adding 'deselect on nothing' to the default view3d.select keymap entries).
# Loopanar code could possibly be improved with strategic use of more sets instead of lists in a few places.  I got the two main functions returning sets of indices as their final return but entire_loop and entire_ring might benefit from sets and/or returning indices. (former is probably easier than latter)
#    Loopanar is already very speedy, though, so I don't know how much this may improve it.  But I am doing membership checks outside of Loopanar with lists returned from Loopanar so this would speed that up.
# Extension methods: manifold vertex, boundary vertex, wire vertex, nonmanifold vertex if I'm feeling spicy || manifold edge loop, manifold edge ring, boundary edge loop, wire edge loop, nonmanifold edge loop if I'm feeling spicy || face loop
#    Note, however, that the vertex extensions are basically the same thing as the edge loop extensions.

import bpy
import bmesh
import time

classes = []


class ContextSelectPreferences(bpy.types.AddonPreferences):
    # this must match the addon name, use '__package__'
    # when defining this in a submodule of a python package.
    bl_idname = __name__

    select_linked_on_double_click: bpy.props.BoolProperty(
        name="Select Linked On Double Click", 
        description="Double clicking on a face or a vertex (if not part of a loop selection) "
                    + "will select all components for that contiguous mesh piece.",
        default=False)

    allow_non_quads_at_ends: bpy.props.BoolProperty(
        name="Allow Non-Quads At Start/End Of Face Loops", 
        description="If a loop of faces terminates at a triangle or n-gon, "
                    + "allow that non-quad face to be added to the final loop selection, "
                    + "and allow using that non-quad face to begin a loop selection. "
                    + "NOTE: For bounded face selection the starting OR ending face must be a quad.",
        default=True)

    terminate_self_intersects: bpy.props.BoolProperty(
        name="Terminate Self-Intersects At Intersection", 
#        description="If a loop/ring of vertices, edges, or faces circles around and crosses over itself, "
#                    + "stop the selection at that location.", 
        description="If a loop of faces circles around and crosses over itself, "
                    + "stop the selection at that location.",  # Currently only works with face loops.
        default=False)

    boundary_ignore_wires: bpy.props.BoolProperty(
        name="Ignore Wire Edges On Boundaries", 
        description="If wire edges are attached to a boundary vertex the selection will ignore it, "
                    + "pass through, and continue selecting the boundary loop.",
        default=True)

    leave_edge_active: bpy.props.BoolProperty(
        name="Leave Edge Active After Selections", 
        description="When selecting edge loops or edge rings, the active edge will remain active. "
                    + "NOTE: This changes the behavior of chained neighbour selections to be non-Maya like.",
        default=False)

    ignore_hidden_geometry: bpy.props.BoolProperty(
        name="Ignore Hidden Geometry", 
#        description="Loop selections will ignore hidden components and continue through to the other side.",
        description="Loop selections will ignore hidden faces and continue the selection on the other side.",
        default=False)
    
    return_single_loop: bpy.props.BoolProperty(
        name="Select Single Bounded Loop", 
#        description="Loop selections will ignore hidden components and continue through to the other side.",
        description="For bounded face selections, if there are multiple equal-length paths between the start and "
                    + "end face, select only one loop instead of all possible loops.",
        default=False)

    def draw(self, context):
        layout = self.layout
        layout.label(text="General Selection:")
        layout.prop(self, "select_linked_on_double_click")
#        layout.prop(self, "terminate_self_intersects")  # Final location of this option once I get it working with edges and verts in addition to faces.
#        layout.prop(self, "ignore_hidden_geometry")  # Final location of this option once I get it working with edges and verts in addition to faces.
#        layout.prop(self, "return_single_loop")  # Final location of this option once I get it working with edges and verts in addition to faces.
        layout.label(text="Edge Selection:")
        layout.prop(self, "leave_edge_active")
        layout.prop(self, "boundary_ignore_wires")
        layout.label(text="Face Selection:")
        layout.prop(self, "allow_non_quads_at_ends")
        layout.prop(self, "terminate_self_intersects")  # Temporary location of this option while it currently only works with faces.
        layout.prop(self, "ignore_hidden_geometry")  # Temporary location of this option while it currently only works with faces.
        layout.prop(self, "return_single_loop")  # Temporary location of this option while it currently only works with faces.
classes.append(ContextSelectPreferences)


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
    bl_options = {'REGISTER', 'UNDO'} # Do we actually need the REGISTER option?

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        if context.object.mode == ObjectMode.EDIT: # Isn't there a specific edit_mesh mode? 'edit' is more generic?
            # Checks if we are in vertex selection mode.
            if context.tool_settings.mesh_select_mode[0]: # Since it's a tuple maybe I could test if mesh_select_mode == (1,0,0) ?
                return maya_vert_select(context)

            # Checks if we are in edge selection mode.
            if context.tool_settings.mesh_select_mode[1]:
                return maya_edge_select(context)

            # Checks if we are in face selection mode.
            if context.tool_settings.mesh_select_mode[2]:
                if context.area.type == 'VIEW_3D':
                    return maya_face_select(context)
                elif context.area.type == 'IMAGE_EDITOR':
                    bpy.ops.uv.select_linked_pick(extend=False)
        return {'FINISHED'}
classes.append(OBJECT_OT_context_select)


def maya_vert_select(context):
    prefs = context.preferences.addons[__name__].preferences
    me = context.object.data
    bm = bmesh.from_edit_mesh(me)

    if len(bm.select_history) == 0:
        return {'CANCELLED'}

    # It takes about 0.043 seconds to get this list on a 333k vertex mesh.
    selected_components = [v for v in bm.verts if v.select]# + [f for f in bm.faces if f.select] + [e for e in bm.edges if e.select]

    active_vert = bm.select_history.active
    previous_active_vert = bm.select_history[len(bm.select_history) - 2]
    # Sanity check.  Make sure we're actually working with vertices.
    # A more radical option would be to get the bmesh and the active/previous_active component back in the main class and do bmesh.types.BMComponent checks there instead to determine which maya_N_select to use rather than relying on mesh_select_mode.
    # That could possibly solve the Multi-select conundrum and we maybe wouldn't need to come up with logic to handle mesh_select_mode 1,0,0, 1,1,0, 1,0,1, 1,1,1, 0,1,0, 0,1,1, and 0,0,1 all individually.
    # 
    # Also if I get my bmesh back in the main class I could move the if len(bm.select_history) == 0: test up there as well.
    # 
    # Maybe the way to do it would be, if active and previous are the same type, use that appropriate maya_N_select.  If they are different, return cancelled UNLESS the active is an edge, in which case, fire off maya_edge_select with special logic 
    # to skip all the tests and just select an edge loop (since it's a double click).  I could restructure that function to use Modes (loop, ring, bounded?) perhaps.  Even if I don't this will be the most complicated function of the 3 just due to the many different edge types and selections.
    if type(active_vert) is not bmesh.types.BMVert or type(previous_active_vert) is not bmesh.types.BMVert:
        return {'CANCELLED'}

    relevant_neighbour_verts = get_neighbour_verts(active_vert)

    adjacent = False
    if previous_active_vert.index in relevant_neighbour_verts:
        adjacent = True

    if not previous_active_vert.index == active_vert.index:
        if adjacent:
            # Instead of looping through vertices we totally cheat and use the two adjacent vertices to get an edge
            # and then use that edge to get an edge loop. The select_flush_mode (which we must do anyway)
            # near the end of maya_vert_select will handle converting the edge loop back into vertices.
            active_edge = [e for e in active_vert.link_edges[:] if e in previous_active_vert.link_edges[:]][0]
            if active_edge.is_boundary:
                print("Selecting Boundary Edges Then Verts")
                boundary_edges = get_boundary_edge_loop(active_edge)
                for i in boundary_edges:
                    bm.edges[i].select = True
            elif active_edge.is_manifold:
                print("Selecting Edge Loop Then Verts")
                loop_edges = entire_loop(active_edge)
                for e in loop_edges:
                    e.select = True
        #Section to handle partial vertex loops (select verts between 2 endpoint verts)
        elif not adjacent:
            bounded_sel = get_bounded_selection(bm, active_vert, previous_active_vert, mode = 'VERT')
            if bounded_sel != "no_selection":
                print("Selecting Bounded Vertices")
                for i in bounded_sel:
                    bm.verts[i].select = True
            # If no loop contains both vertices, select linked.
            elif bounded_sel == "no_selection" and prefs.select_linked_on_double_click:
                print("No Bounded Selection")
                print("Selecting Linked")
                select_vert(active_vert)
                bpy.ops.mesh.select_linked()
        else:
            if prefs.select_linked_on_double_click:
                print("Selecting Linked")
                select_vert(active_vert)
                bpy.ops.mesh.select_linked()
    else:
        if prefs.select_linked_on_double_click:
            print("Selecting Linked")
            select_vert(active_vert)
            bpy.ops.mesh.select_linked()

    for component in selected_components:
        component.select = True

    bm.select_history.add(active_vert)  # Re-add active_vert to history to keep it active.
    bm.select_flush_mode()
    bmesh.update_edit_mesh(me)
    return {'FINISHED'}


def maya_face_select(context):
    prefs = context.preferences.addons[__name__].preferences
    me = context.object.data
    bm = bmesh.from_edit_mesh(me)

    if len(bm.select_history) == 0:
        return {'CANCELLED'}

    # It takes about 0.044 seconds to get this list on a 333k face mesh.
    selected_components = [f for f in bm.faces if f.select]# + [e for e in bm.edges if e.select] + [v for v in bm.verts if v.select]

    active_face = bm.select_history.active
    previous_active_face = bm.select_history[len(bm.select_history) - 2]
    # Sanity check.  Make sure we're actually working with faces.
    if type(active_face) is not bmesh.types.BMFace or type(previous_active_face) is not bmesh.types.BMFace:
        return {'CANCELLED'}

    relevant_neighbour_faces = get_neighbour_faces(active_face)

    if len(active_face.verts) != 4 and len(previous_active_face.verts) != 4:
        quads = (0, 0)
    elif len(active_face.verts) == 4 and len(previous_active_face.verts) == 4:
        quads = (1, 1)
    elif len(active_face.verts) == 4 and len(previous_active_face.verts) != 4:
        quads = (1, 0)
    elif len(active_face.verts) != 4 and len(previous_active_face.verts) == 4:
        quads = (0, 1)

    adjacent = False
    if previous_active_face.index in relevant_neighbour_faces:
        adjacent = True

    if not previous_active_face.index == active_face.index and not quads == (0, 0):  # LOL I FOUND AN ISSUE. If you select 1 face and then Shift+Double Click on EMPTY SPACE it will trigger select_linked (if the pref is true) because LMB with no modifiers is the only keymap entry that has "deselect on nothing" by default. This is actually true in Maya, too. Modifier+LMB in Maya doesn't deselect on empty. Can I even do anything?
        if adjacent and (quads == (1, 1) or prefs.allow_non_quads_at_ends):
            print("Selecting Face Loop")
            a_edges = active_face.edges
            p_edges = previous_active_face.edges
            ring_edge = [e for e in a_edges if e in p_edges][0]
            loop_faces = face_loop_from_edge(ring_edge)
            for i in loop_faces:
                bm.faces[i].select = True  # It only takes about 0.0180 sec to set 34,000 faces as selected.
        elif not adjacent and (quads == (1, 1) or prefs.allow_non_quads_at_ends):
            print("Faces Not Adjacent. Trying Bounded Selection")
            bounded_sel = get_bounded_selection(bm, active_face, previous_active_face, mode = 'FACE')
            if bounded_sel != "no_selection":
                print("Selecting Bounded Faces")
                for i in bounded_sel:
                    bm.faces[i].select = True
            # If no loop contains both faces, select linked.
            elif bounded_sel == "no_selection" and prefs.select_linked_on_double_click:
                    print("No Bounded Selection")
                    print("Selecting Linked")
                    select_face(active_face)  # Sadly this is necessary because select_linked will fire for EVERY mesh piece with a partial selection instead of only the active component.
                    bpy.ops.mesh.select_linked()  # If you don't supply a delimit method it just grabs all geometry, which nicely bypasses the flipped normals issue from before.
        else:  # Catchall for if not prefs.allow_non_quads_at_ends
            if prefs.select_linked_on_double_click:
                print("Selecting Linked")
                select_face(active_face)
                bpy.ops.mesh.select_linked()
    else:
        if prefs.select_linked_on_double_click:
            print("Selecting Linked")
            select_face(active_face)
            bpy.ops.mesh.select_linked()

    for component in selected_components:
        component.select = True

#    time_start = time.time()
    bm.select_history.add(active_face)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(me)  # Takes about 0.0310 sec to both Flush and Update the mesh on a 333k face mesh.
#    print("Time to Flush and update_edit_mesh: %.4f sec" % (time.time() - time_start))
    return {'FINISHED'}


def maya_edge_select(context):
    prefs = context.preferences.addons[__name__].preferences
    me = context.object.data
    bm = bmesh.from_edit_mesh(me)

    if len(bm.select_history) == 0:
        return {'CANCELLED'}
    
    # Everything that is currently selected.
    # It takes about 0.094 seconds to get this list on a 666k edge mesh.
    selected_components = [e for e in bm.edges if e.select]# + [f for f in bm.faces if f.select] + [v for v in bm.verts if v.select]

    active_edge = bm.select_history.active
    previous_active_edge = bm.select_history[len(bm.select_history) - 2]
    # Sanity check.  Make sure we're actually working with edges.
    if type(active_edge) is not bmesh.types.BMEdge or type(previous_active_edge) is not bmesh.types.BMEdge:
        return {'CANCELLED'}

    relevant_neighbour_edges = get_neighbour_edges(active_edge)
    opr_selection = [active_edge, previous_active_edge]

    adjacent = False
    if previous_active_edge.index in relevant_neighbour_edges:
        adjacent = True

    #If the previous edge and current edge are different we are doing a Shift+Double Click selection.
    # This could be a complete edge ring/loop, or partial ring/loop.
    if not previous_active_edge.index == active_edge.index:
        if adjacent:
            # If a vertex is shared then the active_edge and previous_active_edge are physically connected.
            # We want to select a full edge loop.
            if any([v for v in active_edge.verts if v in previous_active_edge.verts]):
                if active_edge.is_manifold:
                    print("Selecting Edge Loop")
                    loop_edges = entire_loop(active_edge)
                    for e in loop_edges:
                        e.select = True
                elif active_edge.is_boundary:
                    print("Selecting Boundary Edges")
                    boundary_edges = get_boundary_edge_loop(active_edge)
                    for i in boundary_edges:
                        bm.edges[i].select = True
                elif active_edge.is_wire:
                    print("Selecting Wire Edges")
                    bpy.ops.mesh.edgering_select('INVOKE_DEFAULT', ring=False)
            # If they're not connected but still adjacent then we want a full edge ring.
            else:
                print("Selecting Edge Ring")
                ring_edges = entire_ring(active_edge)
                for e in ring_edges:
                    e.select = True
        # If we're not adjacent we have to test for bounded selections.
        elif not adjacent:
            if active_edge.is_manifold:
                print("Attempting Manifold Bounded Edge Selection")
                new_sel = get_bounded_selection(bm, active_edge, previous_active_edge, mode = 'EDGE')
                if new_sel != "no_selection":
                    for i in new_sel:
                        bm.edges[i].select = True
                # For an edge that has loop of 36,000 and ring of 18,000: 0.68 to 0.697 sec compared to 0.75 to 0.79 for the old Loopanar way.
                else:
                    print("End of Line - Selecting Edge Loop")
                    loop_edges = entire_loop(active_edge)
                    for e in loop_edges:
                        e.select = True
#            elif active_edge.is_boundary:
#            elif active_edge.is_wire:
            # Clean this up after we have working bounded selection for boundary and wire.
            # If I keep all my bounded selection code inside get_bounded_selection, then really I only need to run one line...
            # elif not adjacent:
                # new_sel = get_bounded_selection(bm, active_edge, previous_active_edge, mode = 'EDGE')
                    # if new_sel != "no_selection":
                        # for i in new_sel:
                            # bm.edges[i].select = True
                    # else:
                        # if active_edge.is_manifold:
                            # end of line for manifold
                        # elif active_edge.is_boundary:
                            # end of line for boundary
                        # elif active_edge.is_wire:
                            # end of line for wire
            else:
                if active_edge.is_boundary:
                    print("End of Line - Selecting Boundary Edges")
                    boundary_edges = get_boundary_edge_loop(active_edge)
                    for i in boundary_edges:
                        bm.edges[i].select = True
                elif active_edge.is_wire:
                    print("End of Line - Selecting Wire Edges")
                    bpy.ops.mesh.edgering_select('INVOKE_DEFAULT', ring=False) # Need to get rid of this and write our own operator, otherwise we can't use the addon preference for terminate_self_intersects and it also doesn't work with multiple objects in edit mode without us checking Shift events.
    # I guess clicking an edge twice makes the previous and active the same? Or maybe the selection history is
    # only 1 item long.  Therefore we must be selecting a new loop that's not related to any previous selected edge.
    else:
        if active_edge.is_boundary:
            print("Skip Tests - Selecting Boundary Edges")
            boundary_edges = get_boundary_edge_loop(active_edge)
            for i in boundary_edges:
                bm.edges[i].select = True
        elif active_edge.is_wire:
            print("Skip Tests - Selecting Wire Edges")
            bpy.ops.mesh.edgering_select('INVOKE_DEFAULT', ring=False) # Need to get rid of this and write our own operator, otherwise we can't use the addon preference for terminate_self_intersects
        else:
            print("Skip Tests - Selecting Edge Loop")
            loop_edges = entire_loop(active_edge)
            for e in loop_edges:
                e.select = True

    # Finally, in addition to the new selection we made, re-select anything that was selected back when we started.
    for component in selected_components:
        component.select = True

    # I have no idea why clearing history matters for edges and not for verts/faces, but it seems that it does.
    bm.select_history.clear()
    # Re-adding the active_edge to keep it active alters the way chained selections work
    # in a way that is not like Maya so it is a user preference now.
    if prefs.leave_edge_active:
        bm.select_history.add(active_edge)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(me)
    return {'FINISHED'}


# Hey what this?
# https://developer.blender.org/diffusion/B/browse/master/release/scripts/startup/bl_operators/bmesh/find_adjacent.py


# Takes a vertex and returns a set of indicies for adjacent vertices.
def get_neighbour_verts(vertex):
    edges = vertex.link_edges[:]  # There's no nonmanifold check
    relevant_neighbour_verts = {v.index for e in edges for v in e.verts[:] if v != vertex}
    return relevant_neighbour_verts


# Takes a face and returns a set of indicies for connected faces.
def get_neighbour_faces(face):
    face_edges = face.edges[:]  # There's no nonmanifold check
    relevant_neighbour_faces = {f.index for e in face_edges for f in e.link_faces[:] if f != face}
    return relevant_neighbour_faces


# Takes an edge and returns a set of indicies for nearby edges.
# Optionally takes a mode and will return only components for that mode, otherwise returns all.
def get_neighbour_edges(edge, mode = ''):
    prefs = bpy.context.preferences.addons[__name__].preferences
    if mode not in ['', 'LOOP', 'RING']:
        bpy.ops.wm.report_err(err_type = 'ERROR_INVALID_INPUT',
                              err_message = "ERROR: get_neighbour_edges mode must be one of: "
                              + "'', 'LOOP', or 'RING'")
        return {'CANCELLED'}
    edge_loops = edge.link_loops[:]  # There are a couple of manifold checks below but there could stand to be more.
    edge_faces = edge.link_faces[:]
    face_edges = {e for f in edge_faces for e in f.edges[:]}

    ring_edges = []
    if len(edge_faces) == 1 or len(edge_faces) == 2:
        for f in edge_faces:
            if len(f.verts) == 4:
                # Get the only 2 verts that are not in the edge we start with.
                target_verts = [v for v in f.verts if v not in edge.verts]
                # Add the only edge that corresponds to those two verts.
                ring_edges.extend([e.index for e in f.edges
                                  if target_verts[0] in e.verts and target_verts[1] in e.verts])

    if edge.is_manifold:
        # Vertices connected to more or less than 4 edges are disqualified.
        loop_edges = [e.index for v in edge.verts for e in v.link_edges[:]
                     if len(v.link_edges[:]) == 4 and e.is_manifold and e not in face_edges]
    elif edge.is_boundary:
        edge_verts = edge.verts[:]
        if not prefs.boundary_ignore_wires:
            loop_edges = []
            for v in edge_verts:
                linked_edges = v.link_edges[:]
                for e in linked_edges:
                    if not any([e for e in linked_edges if e.is_wire]):
                        if e.is_boundary and e is not edge:
                            loop_edges.append(e.index)
        elif prefs.boundary_ignore_wires:
            loop_edges = [e.index for v in edge_verts for e in v.link_edges[:]
                         if e.is_boundary and e is not edge]
    # There may be more than we can do with wires but for now this will have to do.
    elif edge.is_wire:
        loop_edges = []
        for vert in edge.verts:
            linked_edges = vert.link_edges[:]
            if len(vert.link_edges) == 2:
                loop_edges.extend([e.index for e in linked_edges if e.is_wire and e is not edge])
    # Nonmanifold
    elif len(edge_faces) > 2:
        loop_edges = [e.index for v in edge.verts for e in v.link_edges[:]
                     if not e.is_manifold and not e.is_wire and e not in face_edges]
                     
    print("Edge Faces: " + str([f.index for f in edge_faces]))
    print("Face Edges: " + str([e.index for e in face_edges]))
    print("Loop Edges: " + str(loop_edges))
    print("Ring Edges: " + str(ring_edges))
    relevant_neighbour_edges = set(ring_edges + loop_edges)
    if mode == '':
        return relevant_neighbour_edges  # Returns a set.
    elif mode == 'LOOP':
        return loop_edges  # Returns a list, not a set. This is intentional.
    elif mode == 'RING':
        return ring_edges  # Returns a list, not a set. This is intentional.


def select_edge(edge):
    bpy.ops.mesh.select_all(action='DESELECT')
    edge.select = True


def select_vert(vertex):
    bpy.ops.mesh.select_all(action='DESELECT')
    vertex.select = True


def select_face(face):
    bpy.ops.mesh.select_all(action='DESELECT')
    face.select = True


# Takes a boundary edge and returns a set of indices for other boundary edges
# that are contiguous with it in the same boundary "loop".
def get_boundary_edge_loop(edge):
    prefs = bpy.context.preferences.addons[__name__].preferences
    cur_edges = [edge]
    final_selection = {edge.index}
    visited_verts = set()
#    print("==========BEGIN!==========")
#    print("Starting Edge: " + str(cur_edges[0].index))
    while True:
        edge_verts = {v for e in cur_edges for v in e.verts[:]}
        if not prefs.boundary_ignore_wires: # This is one of the places where I should test performance. This logic would be slower, I imagine, and having random wires is an edge case, I imagine, so setting the pref to True by default might be more performant.  Anyone who needs the edge case can disable it.
            new_edges = []
            for v in edge_verts:
                if v.index not in visited_verts:
                    linked_edges = v.link_edges[:]
#                    if len([e.index for e in linked_edges if e.is_boundary]) > 2:  # This check only to be used for bounded boundary edge loop selection.
#                        print("Butt:", [e.index for e in linked_edges if e.is_boundary])
                    for e in linked_edges:
                        if not any([e for e in linked_edges if e.is_wire]):
                            if e.is_boundary and e.index not in final_selection:
                                new_edges.append(e)
                visited_verts.add(v.index)
        elif prefs.boundary_ignore_wires:
            new_edges = [e for v in edge_verts for e in v.link_edges[:]
                         if e.is_boundary and e.index not in final_selection]
#        print("New Edges: " + str([e.index for e in new_edges]))

        for e in new_edges:
            final_selection.add(e.index)

        if len(new_edges) == 0:
#            print("Break!")
            break
        else:
#            print("Next Edges: " + str([e.index for e in new_edges]))
            cur_edges = new_edges
#            print("-----Loop-----")
#    print("Boundary edge indices are: " + str(final_selection))
    return final_selection


# Takes two components of the same type and returns a set of indices that are bounded between those two components.
def get_bounded_selection(bmesh, component1, component2, mode):
    prefs = bpy.context.preferences.addons[__name__].preferences

    if not component1 or not component2 or component1.index == component2.index:
        bpy.ops.wm.report_err(err_type = 'ERROR_INVALID_INPUT',
                              err_message = "ERROR: You must supply two components of the same type and a mode.")
        return {'CANCELLED'}
    if mode not in ['VERT', 'EDGE', 'FACE']:
        bpy.ops.wm.report_err(err_type = 'ERROR_INVALID_INPUT',
                              err_message = "ERROR: get_bounded_selection mode must be one of "
                              + "'VERT', 'EDGE', or 'FACE'")
        return {'CANCELLED'}
    if type(component1) != type(component2):
        bpy.ops.wm.report_err(err_type = 'ERROR_INVALID_INPUT',
                              err_message = "ERROR: Both components must be the same type and "
                              + "must match the supplied mode.")
        # Fuck me if someone supplies a manifold edge and a wire edge.
        return {'CANCELLED'}

    ends = [component1, component2]
    bm = bmesh
    if mode == 'VERT':
        # Not implemented yet but if the len(v.link_edges) for one of the verts is 3 and the other is 4
        # we could maybe use the n=3 vert as the starting vert.
        if len(ends[0].link_edges) == 4:
            starting_vert = ends[0]
        elif len(ends[0].link_edges) != 4 and len(ends[1].link_edges) == 4:
            starting_vert = ends[1]
        elif len(ends[0].link_edges) != 4 and len(ends[1].link_edges) != 4:  # We have no valid path forward for boundary loops and wire loops.  We'll add those later on.  First I just want to get this working with manifold vert loops.
            return "no_selection"

        connected_loops = get_bounded_verts_manifold(ends, starting_vert, prefs)

    if mode == 'EDGE':
        # Unlike face mode, edge mode has to contend with several different ways to advance through the loops to get lists.
        # So we can't just blindly fire off a set of the 2 loop edges and 2 ring edges, we actually need order.
        # The main two are loop and ring, but later on I also want to deal with boundary, and possibly wire and nonmanifold.
        if len(ends[0].link_faces) == 2:
            starting_edge = ends[0]
        elif len(ends[0].link_faces) != 2 and len(ends[1].link_faces) == 2:
            starting_edge = ends[1]
        elif len(ends[0].link_faces) != 2 and len(ends[1].link_faces) != 2:  # This doesn't leave any path forward for wire, boundary, or non-manifold.
            return "no_selection"

        loop_dirs = [bm.edges[i] for i in get_neighbour_edges(starting_edge, mode='LOOP')]  # edges
        ring_dirs = [bm.edges[i] for i in get_neighbour_edges(starting_edge, mode='RING')]  # edges
        
        connected_loops = []
        if len(loop_dirs):
            connected_loops = get_bounded_edge_loop_manifold(ends, starting_edge, loop_dirs, prefs)
        if len(connected_loops) > 0:
            # Maya's behavior is that if there is a positive match for a bounded loop selection then
            # return the loop selection. It doesn't care if there's an equal-length ring selection too.
            pass
        elif len(ring_dirs):
            connected_loops = get_bounded_edge_ring_manifold(ends, starting_edge, ring_dirs, prefs)

    if mode == 'FACE':
        # Not implemented yet but if one of the faces is a triangle and the other is a quad we could use the triangle
        # as our starting_face if the pref allows cause n=3 instead of n=4 to find out if the other face is connected
        if not prefs.allow_non_quads_at_ends and (len(ends[0].verts) != 4 or len(ends[1].verts) != 4):
            return "no_selection"
        if len(ends[0].verts) == 4:
            starting_face = ends[0]
        elif len(ends[0].verts) != 4 and len(ends[1].verts) == 4:
            starting_face = ends[1]
        else:
#            print("Neither face is a quad.")
            return "no_selection"

        connected_loops = get_bounded_faces(ends, starting_face, prefs)

    connected_loops.sort(key = lambda x: len(x))
#    print([len(r) for r in connected_loops])
    if len(connected_loops) == 0:
        return "no_selection"
    elif len(connected_loops) == 1:
        return {i for i in connected_loops[0]}
    # If multiple bounded loop candidates of identical length exist, this pref returns only the first loop.
    elif prefs.return_single_loop and len(connected_loops) > 1:
        return {i for i in connected_loops[0]}
    else:
        return {i for loop in connected_loops if len(loop) == len(connected_loops[0]) for i in loop}


# Takes 2 separated verts, and which vert to start with, and returns a list of loop lists of vertex indices.
def get_bounded_verts_manifold(ends, starting_vert, prefs):
    candidate_dirs = starting_vert.link_edges[:]  # edges
    starting_component = candidate_dirs[0]  # edge
    max_iteration = len(candidate_dirs) - 1

    cur_edge = starting_component
    cur_vert = [v for v in cur_edge.verts if v is not starting_vert][0]
    partial_list = {starting_vert.index}
    connected_loops = []
    dead_end = False
    cur_iteration = 0
#    print("===Starting While Loop===")
#    print("Iteration:", cur_iteration)
#    time_start = time.time()
    while True:
        # Get next components
        next_edge = loop_extension(cur_edge, cur_vert)
        if next_edge:
            next_vert = next_edge.other_vert(cur_vert)
        else:
            dead_end = True

        # Looped back on self, or reached other component
        if cur_vert.index == ends[0].index or cur_vert.index == ends[1].index:
            dead_end = True
        # Self-intersecting loop and pref doesn't allow it
        if prefs.terminate_self_intersects and cur_vert.index in partial_list:
            dead_end = True
        # Vertex/edge is hidden and pref to ignore hidden geometry isn't enabled
        if not prefs.ignore_hidden_geometry and (cur_vert.hide or cur_edge.hide):
            dead_end = True

        # Add component to list.
        if cur_vert.index not in partial_list:
            partial_list.add(cur_vert.index)

        if dead_end:
            dead_end = False  # Reset dead_end so we can continue to the next loop
            cur_iteration += 1
            if ends[0].index in partial_list and ends[1].index in partial_list:
                connected_loops.append([c for c in partial_list])
            # Jump to the next candidate direction.
            if cur_iteration <= max_iteration:
#                print("Iteration:", cur_iteration)
                next_edge = candidate_dirs[cur_iteration]
                next_vert = [v for v in next_edge.verts if v is not starting_vert][0]
                partial_list = {starting_vert.index}
            else:
                break
        # Run this part always
        cur_edge = next_edge
        cur_vert = next_vert

    return connected_loops


# Takes 2 separated faces, and which face to start with, and returns a list of loop lists of face indices.
def get_bounded_faces(ends, starting_face, prefs):
    # Must use the face's loops instead of its edges because edge's loop[0] could point to a different face.
    candidate_dirs = starting_face.loops[:]
    max_iteration = len(candidate_dirs) - 1

    loop = candidate_dirs[0]
    cur_loop = loop
    partial_list = {starting_face.index}
    connected_loops = []
    dead_end = False
    cur_iteration = 0
    while True:
        # Jump to next loop on the same edge and walk two loops forward (opposite edge)
        next_loop = cur_loop.link_loop_radial_next.link_loop_next.link_loop_next
        next_face = next_loop.face
        
        # Looped back on self, or reached other component
        if next_face.index == ends[0].index or next_face.index == ends[1].index:
            dead_end = True

        # Self-intersecting loop and pref doesn't allow it
        if prefs.terminate_self_intersects and next_face.index in partial_list:
            dead_end = True
        # Face is hidden and pref to ignore hidden geometry isn't enabled
        if not prefs.ignore_hidden_geometry and next_face.hide:
            dead_end = True
        # Triangle or n-gon
        if len(next_face.verts) != 4:
            dead_end = True
        # Non-manifold OR mesh boundary
        if len(cur_loop.edge.link_faces) != 2 or len(next_loop.edge.link_faces) != 2:
            dead_end = True

        # Add component to list.
        if next_face.index not in partial_list:
            if len(next_face.verts) == 4:
                partial_list.add(next_face.index)
            elif prefs.allow_non_quads_at_ends:
                partial_list.add(next_face.index)

        if dead_end:
            dead_end = False  # Reset dead_end so we can continue to the next loop
            cur_iteration += 1
            if ends[0].index in partial_list and ends[1].index in partial_list:
                connected_loops.append([c for c in partial_list])
            # Jump to the next candidate direction.
            if cur_iteration <= max_iteration:
                partial_list = {starting_face.index}
                next_loop = candidate_dirs[cur_iteration]
            else:
                break
        # Run this part always
        cur_loop = next_loop

    return connected_loops


# Takes 2 separated edges, and which edge to start with, and returns a list of loop lists of edge indices.
def get_bounded_edge_loop_manifold(ends, starting_edge, loop_dirs, prefs):
    starting_component = loop_dirs[0]  # edge
    starting_vert = [v for v in starting_edge.verts if v in starting_component.verts][0]  # vert
    max_iteration = len(loop_dirs) - 1

#    print("starting_edge:", starting_edge)
#    print("loop_dirs:", loop_dirs)
#    print("starting_component:", starting_component)
#    print("starting_vert:", starting_vert)

    cur_edge = starting_edge
    cur_vert = starting_vert
    partial_list = {cur_edge.index}
    reference_list = {cur_vert.index}
    connected_loops = []
    dead_end = False
    cur_iteration = 0
    print("===Starting While Loop===")
    print("Loop Iteration:", cur_iteration)
#    time_start = time.time()
    while True:
        # Get next components
        next_edge = loop_extension(cur_edge, cur_vert)
        #print("next_edge is:", next_edge.index)
        if next_edge:
            next_vert = next_edge.other_vert(cur_vert)
            #print("next_vert is:", next_vert.index)
        else:
            dead_end = True

        # Looped back on self, or reached other component
        if next_edge and (next_edge.index == ends[0].index or next_edge.index == ends[1].index):
            dead_end = True
        # Self-intersecting loop and pref doesn't allow it
        if next_edge and prefs.terminate_self_intersects:
            if next_vert.index in reference_list:
                dead_end = True
        # Vertex/edge is hidden and pref to ignore hidden geometry isn't enabled
        if not prefs.ignore_hidden_geometry: 
            if (cur_vert.hide or cur_edge.hide):
                dead_end = True

        # Add component to list.
        if next_edge and next_edge.index not in partial_list:
            partial_list.add(next_edge.index)
#            print("Adding", next_edge.index, "to partial_list")
            reference_list.add(next_vert.index)
#            print("Adding", next_vert.index, "to reference_list")

        if dead_end:
            dead_end = False  # Reset dead_end so we can continue to the next loop
            cur_iteration += 1
            if ends[0].index in partial_list and ends[1].index in partial_list:
                connected_loops.append([c for c in partial_list])
            # Jump to the next candidate direction.
            if cur_iteration <= max_iteration:
                print("Loop Iteration:", cur_iteration)
                next_edge = starting_edge
                next_vert = [v for v in next_edge.verts if v is not starting_vert][0]
                partial_list = {starting_edge.index}
                reference_list = {next_vert.index}
            else:
                break
        # Run this part always
        cur_edge = next_edge
        cur_vert = next_vert

    return connected_loops


# Takes 2 separated edges, and which edge to start with, and returns a list of ring lists of edge indices.
def get_bounded_edge_ring_manifold(ends, starting_edge, ring_dirs, prefs):
    starting_face = starting_edge.link_faces[0]
#    max_iteration = len(ring_dirs) - 1
    if len(starting_face.verts) != 4:
        max_iteration = len(ring_dirs)
    else:
        max_iteration = len(ring_dirs) - 1

#    print("starting_edge:", starting_edge)
#    print("ring_dirs:", ring_dirs)
#    print("starting_component:", starting_component)
#    print("starting_vert:", starting_vert)

    cur_edge = starting_edge
    cur_face = starting_face
    partial_list = {cur_edge.index}
    reference_list = {cur_face.index}
    connected_loops = []
    dead_end = False
    cur_iteration = 0
    print("===Starting While Loop===")
    print("Ring Iteration:", cur_iteration)
#    time_start = time.time()
    while True:
        # Get next components
        next_edge = ring_extension(cur_edge, cur_face)
        if next_edge:
            linked_faces = next_edge.link_faces
            if len(linked_faces) == 2:
                next_face = [f for f in linked_faces if f is not cur_face][0]
        else:
            dead_end = True

        # Looped back on self, or reached other component
        if next_edge and (next_edge.index == ends[0].index or next_edge.index == ends[1].index):
            dead_end = True
        # Self-intersecting loop and pref doesn't allow it
        if next_edge and prefs.terminate_self_intersects:
            if next_face and next_face.index in reference_list:
                dead_end = True
        # Vertex/edge is hidden and pref to ignore hidden geometry isn't enabled
        if not prefs.ignore_hidden_geometry: 
            if (cur_face.hide or cur_edge.hide):
                dead_end = True

        # Add component to list.
        if next_edge and next_edge.index not in partial_list:
            partial_list.add(next_edge.index)
#            print("Adding", next_edge.index, "to partial_list")
            if 'next_face' in locals():
                reference_list.add(next_face.index)
#                print("Adding", next_face.index, "to reference_list")

        if dead_end:
            dead_end = False  # Reset dead_end so we can continue to the next loop
            cur_iteration += 1
            if ends[0].index in partial_list and ends[1].index in partial_list:
                connected_loops.append([c for c in partial_list])
            # Jump to the next candidate direction.
            if cur_iteration <= max_iteration:
                print("Ring Iteration:", cur_iteration)
                next_edge = starting_edge
                next_face = starting_edge.link_faces[cur_iteration]
                partial_list = {starting_edge.index}
#                reference_list = {starting_face.index}
                reference_list = {next_face.index}
            else:
                break
        # Run this part always
        cur_edge = next_edge
        if 'next_face' in locals():
            cur_face = next_face

    return connected_loops


# Takes an edge and returns a loop of face indices (as a set) for the ring direction of that edge.
def face_loop_from_edge(edge):
    if len(edge.link_faces) > 2:
        return []

    prefs = bpy.context.preferences.addons[__name__].preferences
    loop = edge.link_loops[0]
    first_loop = loop
    cur_loop = loop
    face_list = set()  # Checking for membership in sets is faster than lists []
    going_forward = True
    dead_end = False
    while True:
        # Jump to next loop on the same edge and walk two loops forward (opposite edge)
        next_loop = cur_loop.link_loop_radial_next.link_loop_next.link_loop_next
        next_face = next_loop.face

        # If this is true then we've looped back to the beginning and are done
        if next_loop == first_loop:
            break

        # Self-intersecting loop and pref doesn't allow it
        if prefs.terminate_self_intersects and next_face.index in face_list:
            dead_end = True
        # Face is hidden and pref to ignore hidden geometry isn't enabled
        if not prefs.ignore_hidden_geometry and next_face.hide:
            dead_end = True
        # Triangle or n-gon
        if len(next_face.verts) != 4:
            dead_end = True
        # Non-manifold OR mesh boundary
        if len(cur_loop.edge.link_faces) != 2 or len(next_loop.edge.link_faces) != 2:
            dead_end = True

        # Add component to list.
        if next_face.index not in face_list:
            if len(next_face.verts) == 4:
                face_list.add(next_face.index)
            elif prefs.allow_non_quads_at_ends:
                face_list.add(next_face.index)

        # This probably needs a proper sanity check to make sure there even is a face before we try to call the verts of said face.
        # Same for if the loop even has faces to link to.  Maybe move the edge.link_faces test to the front?
        # I think Loopanar maybe has a manifold check somewhere in the Loop selection (not ring) regarding free-floating edges with no faces.

        if dead_end:
            # If going_forward then this is the first dead end and we want to go the other way
            if going_forward:
                going_forward = False
                dead_end = False
                # Return to the starting edge and go the other way
                if len(edge.link_loops) > 1:
                    next_loop = edge.link_loops[1]
                else:
                    break
            # If not going_forward then this is the last dead end and we're done
            else:
                break
        # Run this part always
        cur_loop = next_loop
    return face_list


def face_extension(loop):
    # Jump to next loop on the same edge and walk two loops forward (opposite edge)
    next_loop = loop.link_loop_radial_next.link_loop_next.link_loop_next
    return next_loop.face

# ##################### Loopanar defs ##################### #

def loop_extension(edge, vert):
    candidates = vert.link_edges[:]
    # For certain topology link_edges and link_loops return different numbers.
    # So we have to use link_loops for our length test, otherwise somehow we get stuck in an infinite loop.
    if len(vert.link_loops) == 4 and vert.is_manifold:
        # Note: Performance testing showed cruft to be slightly faster as a list, not a set.
        # About 0.54 sec vs 0.6 sec on a 333k vert mesh with a 34k loop ine one way and 17k perpendicular.
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

def ring_extension(edge, face):
    if len(face.verts) == 4:
        # Get the only 2 verts that are not in the edge we start with.
        target_verts = [v for v in face.verts if v not in edge.verts]
        # Return the only edge that corresponds to those two verts back to partial_ring.
        """This is a prime location to test the performance difference between this loopanar way of getting the next edge by its verts compared to the way I get the next loop from my face_loop_from_edge function."""
        return [e for e in face.edges if target_verts[0] in e.verts and target_verts[1] in e.verts][0]
        # Side note: I guess Maya has an extra check around in here that if the face already has 2 edges selected (or 'marked' for selection) then it's time to terminate the extension.  You'll end up with 3 edges selected (from the previous extension) if a ring loops back across the same face.
        # Or more like if the face is already selected or marked then stop.  You don't have to test number of edges that way which would be slower.
        # Or, since it's a ring, you could grab target_verts[0], get the edge that isn't the starting edge (perpendicular) and see if it or its index is in the list already.
        # Ah feck this would have to be done at a higher level due to how Loopanar is structured.. like.. in partial_ring. Like right after ext = ring_extension(e, f) you'd need a new if check and a break.
    else:
        # Otherwise the face isn't a quad.. return nothing to partial_ring.
        return


def ring_end(edge):
    faces = edge.link_faces[:]
    border = len(faces) == 1  # If only one face is connected then this edge must be the border of the mesh.
    non_manifold = len(faces) > 2  # In manifold geometry one edge can only be connected to two faces.
    dead_ends = map(lambda x: len(x.verts) != 4, faces)
    return border or non_manifold or any(dead_ends)


def entire_loop(edge):
    e = edge
    v = edge.verts[0]
    loop = [edge]
    going_forward = True
    while True:
        ext = loop_extension(e, v)  # Pass the edge and its starting vert to loop_extension
        if ext:  # If loop_extension returns an edge, keep going.
            if going_forward:
                if ext == edge:  # infinite; we've reached our starting edge and are done
                    # Why are we returning the loop and edge twice?  Loop already has edge in it.  Why not just loop?
                    return [edge] + loop + [edge]
                else:  # continue forward
                    loop.append(ext)
            else:  # continue backward
                loop.insert(0, ext)
            v = ext.other_vert(v)
            e = ext
        else:  # finite and we've reached an end
            if going_forward:  # the first end
                going_forward = False
                e = edge
                v = edge.verts[1]
            else:  # the other end
                return loop  # Return the completed loop


def partial_ring(edge, face):
    part_ring = []
    e, f = edge, face
    while True:
        ext = ring_extension(e, f)  # Pass the edge and face to ring_extension
        if not ext:
            break
        part_ring.append(ext)
        if ext == edge:  # infinite; we've reached our starting edge and are done
            break
        if ring_end(ext):  # Pass the edge returned from ring_extension to check if it is the end.
            break
        else:
            f = [x for x in ext.link_faces if x != f][0]
            e = ext
    return part_ring  # return partial ring to entire_ring


def entire_ring(edge):
    fs = edge.link_faces  # Get faces connected to this edge.
    ring = [edge]
    # First check to see if there is ANY face connected to the edge (because Blender allows for floating edges.
    # If there's at least 1 face, then make sure only 2 faces are connected to 1 edge (manifold geometry) to continue.
    if len(fs) and len(fs) < 3:
        # Nested list comprehension. Takes a bit to mentally unpack. First it runs partial_ring per face in fs..
        # which means it returns a list of lists. ne must stand for Next Edge? ne is a list so there are 2 ne at most.
        # Take the edge from the input, and a face from fs and pass it to partial_ring..
        # If there's a returned list.. for ne in that ring, insert all edges from 1 at the front, and 0 at the end.
        dirs = [ne for ne in [partial_ring(edge, f) for f in fs] if ne]
        if dirs:
            if len(dirs) == 2 and set(dirs[0]) != set(dirs[1]):  # if two lists insert first list at front
                [ring.insert(0, e) for e in dirs[1]]
            ring.extend(dirs[0])  # always extend ring with first partial list
    return ring  # return ring back to complete_associated_rings


def complete_associated_loops(edges):
    loops = []
    for e in edges:
        if not any([e in loop for loop in loops]):
            loops.append(entire_loop(e))
    return loops


def complete_associated_rings(edges):
    rings = []
    for e in edges:
        # At first glance this line doesn't seem to matter because rings is empty but once we start
        # adding rings to it then I believe it's needed to prevent duplicates (why not a set?)
        if not any([e in r for r in rings]):
            rings.append(entire_ring(e))
    return rings  # return rings back to select_bounded_ring


def group_unselected(edges, ends):
    gaps = [[]]
    for e in edges:
#        if not e.select:  # We don't care about what's already selected.
        if e not in ends:  # We only care about the gap between the two ends that we used to start the selection.
            gaps[-1].extend([e])
        else:
            gaps.append([])
    return [g for g in gaps if g != []]


# Takes two separated loop edges and returns a set of indices for edges in the shortest loop between them.
def select_bounded_loop(edges):
    for l in complete_associated_loops(edges):
        gaps = group_unselected(l, edges)
        new_sel = set()
        if l[0] == l[-1]:  # loop is infinite
            sg = sorted(gaps,
                        key = lambda x: len(x),
                        reverse = True)
            if len(sg) > 1 and len(sg[0]) > len(sg[1]):  # single longest gap
                final_gaps = sg[1:]
            else:
                final_gaps = sg
        else:  # loop is finite
            tails = [g for g in gaps if any(map(lambda x: loop_end(x), g))]
            nontails = [g for g in gaps if g not in tails]
            if nontails:
                final_gaps = nontails
            else:
                final_gaps = gaps
        for g in final_gaps:
            for e in g:
                new_sel.add(e.index)
    return new_sel


# Takes two separated ring edges and returns a set of indices for edges in the shortest ring between them.
def select_bounded_ring(edges):
    for r in complete_associated_rings(edges):
        gaps = group_unselected(r, edges)
        new_sel = set()
        if r[0] == r[-1]:  # ring is infinite
            sg = sorted(gaps,
                        key = lambda x: len(x),
                        reverse = True)
            if len(sg) > 1 and len(sg[0]) > len(sg[1]):  # single longest gap
                final_gaps = sg[1:]
            else:  # Otherwise the lengths must be identical and there is no single longest gap?
                final_gaps = sg
        else:  # ring is finite
            # Tails = any group of unselected edges starting at one of the starting edges
            # and extending all the way to a dead end.
            tails = [g for g in gaps if any(map(lambda x: ring_end(x), g))]
            nontails = [g for g in gaps if g not in tails]  # Any group between the edges in starting edges.
            if nontails:
                final_gaps = nontails
            else:
                final_gaps = gaps
        for g in final_gaps:
            for e in g:
                new_sel.add(e.index)
    return new_sel


def register():
    for every_class in classes:
        bpy.utils.register_class(every_class)


def unregister():
    for every_class in classes:
        bpy.utils.unregister_class(every_class)


if __name__ == "__main__":
    register()
