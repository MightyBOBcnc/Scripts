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
    "category": "Mesh",
    "author": "Andreas Strømberg, nemyax, Chris Kohl",
    "description": "Maya-style loop selection for vertices, edges, and faces.",
    "wiki_url": "https://github.com/MightyBOBcnc/Scripts/tree/Loopanar-Hybrid/Blender",
    "tracker_url": "https://github.com/MightyBOBcnc/Scripts/issues",
    "location": "",
    "warning": "Somewhat experimental features. Possible performance issues.",
    "blender": (2, 80, 0),
    "version": (0, 1, 2)
}

# ToDo: 
# Write own select_linked function. :(  We must do so if we want to get rid of all uses of real deselection.  Say one object mesh has multiple detached pieces, each with only a partial selection, and we want to select_linked for only ONE of the pieces.
#     Blender's select_linked will run on ALL of the pieces that have a partial selection, not purely on the active component.
# Find out if there need to be any tests for hidden or instanced geometry when we're doing selections.
#    A quick test with the face loop and boundary loop selection near hidden faces didn't seem to show any issues.  (No hidden components are selected. It seems that hidden components cannot be selected in Blender.)  Still need to test with instanced geometry.
# See if it would be feasible to implement this idea as an optional addon preference: https://blender.community/c/rightclickselect/ltbbbc/
#     HAH, not only is it feasible, this is actually how all of my bmesh code works by default... Crud...
#     So, I imagine the default user expectation is that selections should terminate if they encounter hidden components instead of continuing through them.  
#     So actually I need to implement a "hide" check for our normal selection (if v.hide, if e.hide, if f.hide) and then terminate selection and return early, or consider it a dead end and reverse direction.
# Add some more robust checks to validate against nonmanifold geometry like more than 2 faces connected to 1 edge and such.
#    And--in appropriate places--tests like component.is_manifold, component.is_boundary, and (for edges only, I think) e.is_wire
# Replace remaining shortest_path_select use (bounded faces).
# Do some speed tests on some of these functions to measure performance.  There's always a push/pull between the speed of C when using native Blender operators, the extra overhead of doing real selections and mode switches, and using python bmesh without doing real selections or mode switches.
# Implement deselection for all methods of selection (except maybe select_linked).
#    This is actually going to be problematic because we need to track the most recent DEselected component, which Blender does not do.
#    This addon only executes on double click.  We would have to build a helper function using the @persistent decorator to maintain a deselection list (even if said list is only 2 members long).
#    And we would have to replace the regular view3d.select operator in at least 1 place (whatever the keymap is for deselecting; e.g. Ctrl+Click.. or Shift+Click if it's set to Toggle?)
#    And Blender's wonky Undo system would invalidate the deselection list although that MAY not be a problem for something as simple as tracking only 2 components.
# Find out if these selection tools can be made to work in the UV Editor.
# Something is not working right if you're working on more than one object at a time in edit mode.  It will deselect components on anything but the most recent object you were working on.
#    I checked the original version of the script and this has apparently always been the case and I just didn't notice.  So that's something to investigate now; how to retain selection across multiple objects in edit mode.
#    If I had to guess this is probably because of all the instances where the script runs select_face, select_edge, and select_vert where it deselects everything, and probably also the times where we switch selection modes (vert, edge, face), and also because we're not getting a selection to restore per object.
#    So if we could get everything done with bmesh without doing real selections I *think* we could just add to existing selection which wouldn't clear selections and hopefully then we wouldn't even need to get a list of selected components to restore at all, much less per object.
# Write own loop/ring selection function for wire edges.  Loops will be easy because I don't think we have to worry about normal vector direction?  Rings will be harder because there's no face loop?  Or maybe it's the same with loop radial and then walk forward twice.  We'll see.
# Bounded edge loop selection on a floating edge ring like the Circle primitive type. (Wire edges.)
# Bounded edge loop selection on a mesh's boundary edges. (This is gonna be harder? Need a Loopanar-like solution that can measure gaps.)
#    Note: Interestingly Maya doesn't do bounded vertex loop selection on a boundary loop.  It does a select_linked instead.
# Select linked for vertices?  Maya has this if you double click a vertex or shift+double click a vert that is outside of a vertex loop (same as select_linked for faces, basically).  However, do. I. care?  Do people actually do select_linked with vertices?
# Possible new user preferences:
#    Terminate self-intersecting loops and rings at crossing point.
#        Successfully implemented this for face loops!  (The hardest part will be retrofitting this onto Loopanar for edge loops and rings.)
#        Self-intersects can happen with vertex loops, face loops, edge loops, edge rings, boundary edge loops (although boundary loops would need terrible topology it is still possible), and wire edge loops
#    Perhaps an "Experimental" preference for getting bounded loops off of triangles and n-gons.  Warn that this is slower than quads because we need to test more than 1 or 2 loops (up to N loops.. maybe with a restriction for absurdly large n-gons).  Use a While loop to walk every edge and break early if match found.
#    Allow user to specify which select_linked method they want to use on double click? (from a dropdown list)  Or, instead maybe forcibly pop up the delimit=set() in the corner instead?  Hmm but it doesn't appear to always force the popup?
#    A method and user preference to allow non-manifold edge loop selection?  e.g. a way to select an entire non-manifold loop of edges where an edge loop extrusion has been done in the middle of a grid; should be easy to code, it's the same as the boundary edge code except we ONLY want non-manifold edges.
# Loopanar code could possibly be improved with strategic use of more sets instead of lists in a few places.  I got the two main functions returning sets of indices as their final return but entire_loop and entire_ring might benefit from sets and/or returning indices. (former is probably easier than latter)
#    Loopanar is already very speedy, though, so I don't know how much this may improve it.  But I am doing membership checks outside of Loopanar with lists returned from Loopanar so this would speed that up.

import bpy
import bmesh
from bpy.props import FloatProperty, EnumProperty
import math, mathutils as mu

classes = []

class ContextSelectPreferences(bpy.types.AddonPreferences):
    # this must match the addon name, use '__package__'
    # when defining this in a submodule of a python package.
    bl_idname = __name__

    select_linked_on_double_click: bpy.props.BoolProperty(
        name="Select Linked On Double Click", 
        description="Double clicking on a face or a vertex (if not part of a loop selection) will select all components for that contiguous mesh piece.",
        default=False)
    
    allow_non_quads_at_ends: bpy.props.BoolProperty(
        name="Allow Non-Quads At Start/End Of Face Loops", 
        description="If a loop of faces terminates at a triangle or n-gon, allow that non-quad face to be added to the final loop selection, and allow using that non-quad face to begin a loop selection.", 
        default=True)

    terminate_self_intersects: bpy.props.BoolProperty(
        name="Terminate Self-Intersects At Intersection", 
#        description="If a loop/ring of vertices, edges, or faces circles around and crosses over itself, stop the selection at that location.", 
        description="If a loop of faces circles around and crosses over itself, stop the selection at that location.", # Currently only works with face loops.
        default=False)

    boundary_ignore_wires: bpy.props.BoolProperty(
        name="Ignore Wire Edges On Boundaries", 
        description="If wire edges are attached to a boundary vertex the selection will ignore it, pass through, and continue selecting the boundary loop.",
        default=True)

    leave_edge_active: bpy.props.BoolProperty(
        name="Leave Edge Active After Selections", 
        description="When selecting edge loops or edge rings, the active edge will remain active. NOTE: This changes the behavior of chained neighbour selections to be non-Maya like.",
        default=False)

    def draw(self, context):
        layout = self.layout
        layout.label(text="General Selection:")
        layout.prop(self, "select_linked_on_double_click")
#        layout.prop(self, "terminate_self_intersects") # Final location of this option once I get it working with edges and verts in addition to faces.
        layout.label(text="Edge Selection:")
        layout.prop(self, "boundary_ignore_wires")
        layout.prop(self, "leave_edge_active")
        layout.label(text="Face Selection:")
        layout.prop(self, "allow_non_quads_at_ends")
        layout.prop(self, "terminate_self_intersects") # Temporary location of this option while it currently only works with faces.
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


class OBJECT_OT_context_select(bpy.types.Operator):
    bl_idname = "object.context_select"
    bl_label = "Context Select"
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

    selected_components = [v for v in bm.verts if v.select]# + [f for f in bm.faces if f.select] + [e for e in bm.edges if e.select]

    active_vert = bm.select_history.active
    previous_active_vert = bm.select_history[len(bm.select_history) - 2]
    # Sanity check.  Make sure we're actually working with vertices.
    # A more radical option would be to get the bmesh and the active/previous_active component back in the main class and do bmesh.types.BMComponent checks there instead to determine which maya_N_select to use rather than relying on mesh_select_mode.
    # That could possibly solve the Multi-select conundrum and we maybe wouldn't need to come up with logic to handle mesh_select_mode 1,0,0, 1,1,0, 1,0,1, 1,1,1, 0,1,0, 0,1,1, and 0,0,1 all individually.
    if type(active_vert) is not bmesh.types.BMVert or type(previous_active_vert) is not bmesh.types.BMVert:
        return {'CANCELLED'}
    
    relevant_neighbour_verts = get_neighbour_verts(active_vert)
    
    adjacent = False
    if previous_active_vert.index in relevant_neighbour_verts:
        adjacent = True
    
    if not previous_active_vert.index == active_vert.index:
        if adjacent:
            # Instead of looping through vertices we totally cheat and use the two adjacent vertices to get an edge and then use that edge to get an edge loop.
            # The select_flush_mode (which we must do anyway) near the end of maya_vert_select will handle converting the edge loop back into vertices.
            active_edge = [e for e in active_vert.link_edges[:] if e in previous_active_vert.link_edges[:]][0]
            if active_edge.is_boundary:
                print("Selecting Boundary Edges Then Verts")
                boundary_edges = get_boundary_edge_loop(active_edge)
                for i in boundary_edges:
                    bm.edges[i].select = True
            else:
                print("Selecting Edge Loop Then Verts")
                loop_edges = entire_loop(active_edge)
                for e in loop_edges:
                    e.select = True
        #Section to handle partial vertex loops (select verts between 2 endpoint verts)
        #else:
            #I suppose I could take the 2 verts (previous_active_vert and active_vert) and convert+expend them INDIVIDUALLY into Edges (similar to the relevant_neighbours, each of these conversions should be their own list), then turn those edges into loop_multi loops as sets?
            #For any edges that are in both of those sets that determines the loop that we use and discard any other edges.  But this might have issues with my Loop_Test_object.obj test file where some faces loop back on themselves?
            #Now from that loop we.. somehow use the two vertices and/or pseudo-relevant_neighbour lists from above.. to figure out what is between the verts..
            
            #Or we might just be able to utilize the Loopanar code for edges between two selected edges and just convert the two verts into edges, do the sets overlap check to determine the loop, then keep the 4 edges that are in common with that loop and run the Loopanar part.
            #Then deselect the outer two edges which were beyond the vertices and convert the edges back to vertices.. but I already see a problem if the partial vertex loop starts or ends at anything other than a quad intersection it won't expand so we can't discard what will be the real end..
            # Okay, logic could go... if the start/end vertex is not shared by 2 edges from the edge list, then keep it because that means it's on the end.  If it is shared by 2 edges, get those 2 edges.  The other_vert of one of those 2 edges will, itself, not be shared.  That is the edge to remove.  
            # The other edge should be inside the loop and both of its vertices should be shared verts. (If terminate_self_intersects is on then we want to keep the vert that is connected to 3 selected edges)
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

    bm.select_history.add(active_vert) #Re-add active_vert to history to keep it active.
    bm.select_flush_mode()
    bmesh.update_edit_mesh(me)
    return {'FINISHED'}

def maya_face_select(context):
    prefs = context.preferences.addons[__name__].preferences
    me = context.object.data
    bm = bmesh.from_edit_mesh(me)

    if len(bm.select_history) == 0:
        return {'CANCELLED'}

    selected_components = [f for f in bm.faces if f.select]# + [e for e in bm.edges if e.select] + [v for v in bm.verts if v.select]

    active_face = bm.select_history.active
    previous_active_face = bm.select_history[len(bm.select_history) - 2]
    # Sanity check.  Make sure we're actually working with faces.
    if type(active_face) is not bmesh.types.BMFace or type(previous_active_face) is not bmesh.types.BMFace:
        return {'CANCELLED'}
    
    relevant_neighbour_faces = get_neighbour_faces(active_face)
    
    if len(active_face.verts) != 4 and len(previous_active_face.verts) != 4:
        quads = (0,0)
    elif len(active_face.verts) == 4 and len(previous_active_face.verts) == 4:
        quads = (1,1)
    elif len(active_face.verts) == 4 and len(previous_active_face.verts) != 4:
        quads = (1,0)
    elif len(active_face.verts) != 4 and len(previous_active_face.verts) == 4:
        quads = (0,1)
    
    adjacent = False
    if previous_active_face.index in relevant_neighbour_faces:
        adjacent = True
    
    a_edges = active_face.edges
    p_edges = previous_active_face.edges
    if adjacent:
        ring_edge = [e for e in a_edges if e in p_edges][0] # Need to test what happens if two quads share two edges.  Testing on the Suzanne monkey nose seems to work just fine.  Maya seems to go nuts on this type of topology selection.  Winner: Blender?
    elif not adjacent:
        if quads == (1,1) or quads == (1,0) or quads == (0,0): # I hate including 0,0 in here but corner_vert assignment will break, otherwise.
            ring_edge = a_edges[0]                             # Idea for future: If quads is 0,0, test length of active_face.verts and previous_active_face.verts.. the smaller of the two (or first if same length) will be the one that gets ring_edge.
        elif quads == (0,1):                                   # Then add "experimental" add-on preference for bounded loop tests from every edge of a triangle or n-gon. Use a While loop to walk forward on the edges until we get a loop that contains both faces and then break (so as to not get more loops).
            ring_edge = p_edges[0]                             # Actually, now that I think about it a While loop might be more efficient for the normal case of only testing 2 loops anyway, rather than writing two sections of code (one for loop 1 and one for loop 2). Sigh.. another rewrite incoming, lol.

    corner_vert = ring_edge.verts[0] # Note: In theory it shouldn't matter which vertex we choose as the basis for the other_edge.
    if quads == (1,1) or quads == (1,0) or quads == (0,0):
        other_edge = [e for e in a_edges if e != ring_edge and (e.verts[0].index == corner_vert.index or e.verts[1].index == corner_vert.index)][0]
    elif quads == (0,1):
        other_edge = [e for e in p_edges if e != ring_edge and (e.verts[0].index == corner_vert.index or e.verts[1].index == corner_vert.index)][0]

    """New Code."""
    if not previous_active_face.index == active_face.index and not quads == (0,0): # LOL I FOUND AN ISSUE. If you select 1 face and then Shift+Double Click on EMPTY SPACE it will trigger select_linked (if the pref is true) because LMB with no modifiers is the only keymap entry that has "deselect on nothing" by default. This is actually true in Maya, too. Modifier+LMB in Maya doesn't deselect on empty. Can I even do anything?
        if adjacent and (quads == (1,1) or prefs.allow_non_quads_at_ends):
            print("Selecting Face Loop 1")
            loop1_faces = face_loop_from_edge(ring_edge)
            print("Selecting Final Face Loop")
            for f in loop1_faces: # We already have the loop, so just select it.
                bm.faces[f].select = True
        elif not adjacent and (quads == (1,1) or prefs.allow_non_quads_at_ends):
            print("Trying Face Loop 1")
            loop1_faces = face_loop_from_edge(ring_edge)
            # If we are lucky then both faces will be in the first loop and we won't even have to test a second loop. (Save time on very dense meshes with LONG face loops.)
            if active_face.index in loop1_faces and previous_active_face.index in loop1_faces:
                print("Selecting Shortest Face Path")
                select_face(active_face)
                previous_active_face.select = True
                """(This is not a reliable method because shortest_path_select can leave the loop to take shortcuts.)"""
                bpy.ops.mesh.shortest_path_select(use_face_step=False, use_topology_distance=True) # Using topology distance seems to catch more cases which makes this slightly better?
            # If they weren't both in the first loop tested, try a second loop perpendicular to the first.
            else:
                print("Not in Loop 1.  Trying Face Loop 2")
                loop2_faces = face_loop_from_edge(other_edge)
                if active_face.index in loop2_faces and previous_active_face.index in loop2_faces:
                    print("Selecting Shortest Face Path")
                    select_face(active_face)
                    previous_active_face.select = True
                    """(This is not a reliable method because shortest_path_select can leave the loop to take shortcuts.)"""
                    bpy.ops.mesh.shortest_path_select(use_face_step=False, use_topology_distance=True) # Using topology distance seems to catch more cases which makes this slightly better?
                # If neither loop contains both faces, select linked.
                else:
                    if prefs.select_linked_on_double_click:
                        print("Not in Loop 1 or Loop 2")
                        print("Selecting Linked")
                        select_face(active_face) # Sadly this is necessary because select_linked will fire for EVERY mesh piece with a partial selection instead of only the active component.
                        bpy.ops.mesh.select_linked() # If you don't supply a delimit method it just grabs all geometry, which nicely bypasses the flipped normals issue from before.
        else: # Catchall for if not prefs.allow_non_quads_at_ends
            if prefs.select_linked_on_double_click:
                print("Selecting Linked")
                select_face(active_face)
                bpy.ops.mesh.select_linked()
    else:
        if prefs.select_linked_on_double_click:
            print("Selecting Linked")
            select_face(active_face)
            bpy.ops.mesh.select_linked()


        #If we convert to edges first we might be able to use the Loopanar ring completion to get the edges between and then convert to verticies and finally back to contained faces.
        #Nope, the ring selection gets extended from all edges of both faces except for the direction parallel to the correct ring (that part works right).
        #Perhaps instead do a full loop from all 4 edges of the first (or second, doesn't matter) face individually and then if any of those loop edges are in both of the faces then we know that is the proper direction.
        #And once we have the proper direction use the OTHER two edges from each original face to make the Loopanar ring selection.
        #Ugh, even that will run into a problem with faces that have loops that go back onto themselves (see Loop_Test_object.obj in my Documents\maya\projects\default\scenes folder).
        #Unless.. okay there may be a fix for that... if.. only 2 edges on each each face have a loop in common and neither of those edges share a vertex, we're golden.  Just select and use the OTHER two edges for our ring.
        #If each face has 3 shared loop edges in common then the one edge that shares a vertex with the other 2 edges is actually the one we can use to do our ring since it's effectively the same thing as step 2 above.
        #If each face has all 4 edges sharing a loop with all 4 edges of the other face then maybe we can try doing multiple ring selections, convert to vert, convert back to face, then count the length of each ring to face conversion and pick the shortest one as our bounded selection.
        #If the lengths are all the same, though, best we can do is throw our hands up in the air and select everything I guess?  Maya actually does something like this on  my test shape, although it selects only 2 bounded face loops instead of all 3 of them (a complete ring).

    for component in selected_components:
        component.select = True

    bm.select_history.add(active_face)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(me)
    return {'FINISHED'}

def maya_edge_select(context):
    prefs = context.preferences.addons[__name__].preferences
    me = context.object.data
    bm = bmesh.from_edit_mesh(me)

    if len(bm.select_history) == 0:
        return {'CANCELLED'}

    #Everything that is currently selected.
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
    
    """New Code."""
    #If the previous edge and current edge are different we are doing a Shift+Double Click selection. This could be a complete edge ring/loop, or partial ring/loop.
    if not previous_active_edge.index == active_edge.index:
        if adjacent:
            # If a vertex is shared then the active_edge and previous_active_edge are physically connected. We want to select a full edge loop.
            if any([v for v in active_edge.verts if v in previous_active_edge.verts]):
                if not active_edge.is_boundary:
                    print("Selecting Edge Loop")
                    loop_edges = entire_loop(active_edge)
                    for e in loop_edges:
                        e.select = True
                elif active_edge.is_boundary:
                    print("Selecting Boundary Edges")
                    boundary_edges = get_boundary_edge_loop(active_edge)
                    for i in boundary_edges:
                        bm.edges[i].select = True
            # If they're not connected but still adjacent then we want a full edge ring.
            else:
                print("Selecting Edge Ring")
                ring_edges = entire_ring(active_edge)
                for e in ring_edges:
                    e.select = True
        # If we're not adjacent we have to test for bounded selections.
        elif not adjacent:
            test_loop_edges = entire_loop(active_edge) # Modification: if active_edge.is_boundary then the test_loop_edges needs to use get_boundary_edge_loop, otherwise if it's not boundary then go ahead and use entire_loop.
            if previous_active_edge in test_loop_edges:
                if not active_edge.is_boundary:
                    print("Selecting Bounded Edge Loop")
                    new_sel = select_bounded_loop(opr_selection)
                    for i in new_sel:
                        bm.edges[i].select = True
#                elif active_edge.is_boundary:
#                This section for later when we work out how to do bounded selection on a boundary loop, if possible.  (urgh, gonna need one for e.is_wire too)
#                We would maybe actually have to check FIRST if the active_edge.is_boundary, and then use that to determine whether to use select_bounded_loop(active_edge) or get_boundary_edge_loop(active_edge) to get the test_loop_edges.
#                Only then could we test if previous_active_edge in test_loop_edges to determine if we're doing a bounded loop selection.  And if not, then move on to the test_ring_edges selection.
            # If we're not in the loop test selection, try a ring test selection.
            elif previous_active_edge not in test_loop_edges:
                test_ring_edges = entire_ring(active_edge)
                if previous_active_edge in test_ring_edges:
                    print("Selecting Bounded Edge Ring")
                    new_sel = select_bounded_ring(opr_selection)
                    for i in new_sel:
                        bm.edges[i].select = True
                # If we're not in the test_loop_edges and not in the test_ring_edges we're adding a new loop selection somewhere else on the mesh.
                else:
                    if active_edge.is_boundary:
                        print("End of Line - Selecting Boundary Edges")
                        boundary_edges = get_boundary_edge_loop(active_edge)
                        for i in boundary_edges:
                            bm.edges[i].select = True
                    elif active_edge.is_wire:
                        print("End of Line - Selecting Wire Edges")
                        bpy.ops.mesh.edgering_select('INVOKE_DEFAULT', ring=False) # Need to get rid of this and write our own operator, otherwise we can't use the addon preference for terminate_self_intersects
                    else:
                        print("End of Line - Selecting Edge Loop")
                        loop_edges = entire_loop(active_edge)
                        for e in loop_edges:
                            e.select = True
    # I guess clicking an edge twice makes the previous and active the same?  Or maybe the selection history is only 1 item long.  Therefore we must be selecting a new loop that's not related to any previous selected edge.
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

    #Finally, in addition to the new selection we made, re-select anything that was selected back when we started.
    for component in selected_components:
        component.select = True

    bm.select_history.clear() # I have no idea why this matters for edges and not for verts/faces, but it seems that it does.
    if prefs.leave_edge_active:
        bm.select_history.add(active_edge) # Re-adding the active_edge to keep it active changes the way chained selections work in a way that is not like Maya so it is a user preference now.
    bm.select_flush_mode()
    bmesh.update_edit_mesh(me)
    return {'FINISHED'}


# Hey what this?
# https://developer.blender.org/diffusion/B/browse/master/release/scripts/startup/bl_operators/bmesh/find_adjacent.py


# Takes a vertex and return a set of indicies for adjacent vertices.
def get_neighbour_verts(vertex):
    edges = vertex.link_edges[:]
    relevant_neighbour_verts = {v.index for e in edges for v in e.verts[:] if v != vertex}
    return relevant_neighbour_verts

# Takes a face and return a set of indicies for connected faces.
def get_neighbour_faces(face):
    face_edges = face.edges[:]
    relevant_neighbour_faces = {f.index for e in face_edges for f in e.link_faces[:] if f != face}
    return relevant_neighbour_faces

# Takes an edge and return a set of indicies for nearby edges.
# Will return some 'oddball' or extra edges if connected topology is triangles or poles.
# This is no worse than the old bpy.ops.mesh.select_more(use_face_step=True) method which actually returned MORE edges than this new method.
def get_neighbour_edges(edge):
    edge_loops = edge.link_loops[:]
    edge_faces = edge.link_faces[:] # Check here for more than 2 connected faces?
    face_edges = {e for f in edge_faces for e in f.edges[:]}
    
    if len(edge_loops) == 0:
        ring_edges = []
    # For the next 2 elif checks, link_loop hopping is only technically accurate for quads.
    elif len(edge_loops) == 1:
        ring_edges = [edge_loops[0].link_loop_radial_next.link_loop_next.link_loop_next.edge.index]
    elif len(edge_loops) > 1: # This could use a more robust check for nonmanifold geo (more than 2 faces to 1 edge).
        ring_edges = [edge_loops[0].link_loop_radial_next.link_loop_next.link_loop_next.edge.index, edge_loops[1].link_loop_radial_next.link_loop_next.link_loop_next.edge.index]
    # loop_edges returns a lot of edges if the active_edge has 1 vert connected to a pole, such as the cap of a UV Sphere. But it doesn't seem problematic.
    # e not in face_edges coincidentally removes the starting edge which is what we wanted anyway.
    loop_edges = [e.index for v in edge.verts for e in v.link_edges[:] if e not in face_edges]
    
    relevant_neighbour_edges = set(ring_edges + loop_edges)
    return relevant_neighbour_edges


def select_edge(edge):
    bpy.ops.mesh.select_all(action='DESELECT')
    edge.select = True


def select_vert(vertex):
    bpy.ops.mesh.select_all(action='DESELECT')
    vertex.select = True


def select_face(face):
    bpy.ops.mesh.select_all(action='DESELECT')
    face.select = True

# Takes a boundary edge and returns a set of indices for other boundary edges that are contiguous with it in the same boundary "loop".
def get_boundary_edge_loop(edge):
    prefs = bpy.context.preferences.addons[__name__].preferences
    cur_edges = [edge]
    final_selection = set()
    visited_verts = set()
#    print("==========BEGIN!==========")
#    print("Starting Edge: " + str(cur_edges[0].index))
    while True:
        for e in cur_edges:
            final_selection.add(e.index)
        edge_verts = {v for e in cur_edges for v in e.verts[:]}
        if not prefs.boundary_ignore_wires: # This is one of the places where I should test performance. This logic would be slower, I imagine, and having random wires is an edge case, I imagine, so setting the pref to True by default might be more performant.  Anyone who needs the edge case can disable it.
            new_edges = []
            for v in edge_verts:
                if v.index not in visited_verts:
                    linked_edges = v.link_edges[:]
                    for e in linked_edges:
                        if not any([e for e in linked_edges if e.is_wire]):
                            if e.is_boundary and e.index not in final_selection:
                                new_edges.append(e)
                visited_verts.add(v.index)
        elif prefs.boundary_ignore_wires:
            new_edges = [e for v in edge_verts for e in v.link_edges[:] if e.is_boundary and e.index not in final_selection]
#        print("New Edges: " + str([e.index for e in new_edges]))
        
        if len(new_edges) == 0:
#            print("Break!")
            break
        else:
#            print("Next Edges: " + str([e.index for e in new_edges]))
            cur_edges = new_edges
#            print("-----Loop-----")
#    print("Boundary edge indices are: " + str(final_selection))
    return final_selection

# This takes two faces and gives a bounded ring of edges between them if they are in the same quad loop of faces.
# Or more precisely, it will once I finish writing it.  Right now it doesn't do anything.
def edge_ring_from_faces(bm, active_face, previous_active_face):
    edge_ring = []
    a_edges = active_face.edges
    p_edges = previous_active_face.edges

    a_corner_vert = active_face.verts[0]
    p_corner_vert = previous_active_face.verts[0]
    
    a_edge1 = a_corner_vert.link_edges[0]
    a_edge2 = a_corner_vert.link_edges[1]
    
    p_edge1 = p_corner_vert.link_edges[0]
    p_edge2 = p_corner_vert.link_edges[1]
    
    a_ring1 = select_bounded_ring(a_edge1)
    a_ring2 = select_bounded_ring(a_edge2)
    
    p_ring1 = select_bounded_ring(p_edge1)
    p_ring2 = select_bounded_ring(p_edge2)
    
#    correct_ring = [e for e in _something_ if e in _something_else_ and e in a_edges and e in p_edges] # What we want are the 4 edges from the two faces that are in two (or, god help us, more) of the test edge rings.  That determines the 4 (or more..) edges that will be passed to Loopanar.
    # Probably need to use sets for comparison.

# Actually I thought of a better way to get a face loop for testing bounded selection that doesn't require a separate function to get a ring from 2 faces and then get faces from the ring.
# We also don't need to test 4 times.  Only 2, at most, and if the first test returns true we can skip doing the second test which means better performance!  (Note: Unless ugly edge cases happen; I'm designing for happy path first and then edge cases can be dealt with.)
# 1. Use the simple loop ring traversal method starting from a_edge1 (using code that can 'going_forward' and then go backward if reaching a dead end).
# 2. Every time we jump to the next loop, see if the loop.face is the previous_active_face. (Maybe also maintain a list of loops already visited similar to def walk_boundary here: https://github.com/BenjaminSauder/EdgeFlow/blob/master/util.py so that we don't waste time testing places we've checked already.)
# 3. If we reach the end and get no match, do it again using a_edge2.
# 4. If we get no match for either test, run faces_select_linked_flat back in the main class because it's not a bounded face.
# 5. If we do get a match, though, then we know which loop of faces is the correct direction.  Now we begin the work of determining the shortest number of faces between the active_face and previous_active_face (like whatever Loopanar is doing to determine gaps in group_unselected).
# 6. There might be a clever way to reduce the work for this step.  Instead of starting over from scratch now that we know which edge/loop corresponds to the proper direction..
#    We actually started building a list of faces back during the While Loop in step 2.
#    If we reach the previous_active_face on the first try (while going_forward), either because it's the correct direction or because the loop is infinite, then we already have one of our 'gaps' in a list of faces already (or whatever group_unselected is doing).
#    If we reach a dead end and have to reverse direction I'm not sure if we need to discard the list and start over in the other direction or if the built list is still useful later for the gap stuff ("these faces are definitely useless") and we should keep it while starting a second list.
#    Keeping it in a list of lists is probably the better idea.  Each list is a 'fragment'
#    If we have to continue to step 3. then the list(s) do have to be discarded and started over.
# 7. So we keep the list(s) from step 2 or 3 and now we do whatever the gaps stuff in group_unselected is and build another list of faces in the opposite direction and then do the comparison or whatever to determine which is shorter.  
#    I haven't closely inspected what group_unselected does and how the 'gaps' stuff works.
# 8. Return the correct faces for selection.
# 
# Additional idea: During the building of the loop, test to see if previous_active_face is the next_face (next_loop.face).  If true then in theory we can break?  
    
    return edge_ring


# Takes an edge and returns a loop of face indices (as a set) for the ring of that edge.
def face_loop_from_edge(edge):
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
        if next_face.index in face_list and prefs.terminate_self_intersects:
            dead_end = True
        elif next_face.index not in face_list:
            if len(next_face.verts) == 4:
                face_list.add(next_face.index)
            elif len(next_face.verts) != 4 and prefs.allow_non_quads_at_ends:
                face_list.add(next_face.index)

        # This probably needs a proper sanity check to make sure there even is a face before we try to call the verts of said face.
        # Same for if the loop even has faces to link to.  Maybe move the edge.link_faces test to the front?
        # I think Loopanar maybe has a manifold check somewhere in the Loop selection (not ring) regarding free-floating edges with no faces.
        # One of the very first things we should probably do with the edge passed to the function is see if that edge is manifold.

        # If this is true then we've looped back to the beginning and are done
        if next_loop == first_loop:
            break
        # If we reach a dead end because the next face is a tri or n-gon, or the next edge is boundary or nonmanifold.
        elif len(next_face.verts) != 4 or len(next_loop.edge.link_faces) != 2 or dead_end:
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


######################Loopanar defs######################

def loop_extension(edge, vert):
    candidates = vert.link_edges[:] # For some topology link_edges and link_loops returns a different number.
    if len(vert.link_loops) == 4 and vert.is_manifold: # So we have to use link_loops for our length test, otherwise somehow we end up inside an infinite loop.
        cruft = [edge] # The next edge obviously can't be the current edge.
        for l in edge.link_loops:
            cruft.extend([l.link_loop_next.edge, l.link_loop_prev.edge]) # The 'next' and 'prev' edges are perpendicular to the desired loop so we don't want them.
        return [e for e in candidates if e not in cruft][0] # Therefore by process of elimination there are 3 unwanted edges in cruft and only 1 possible edge left.
    else:
        return

def loop_end(edge):
    v1, v2 = edge.verts[:] # What's going on here?  This looks like it's assigning both vertices at once from the edge.verts
    return not loop_extension(edge, v1) \
        or not loop_extension(edge, v2)

def ring_extension(edge, face):
    if len(face.verts) == 4:
        target_verts = [v for v in face.verts if v not in edge.verts] #Get the only 2 verts that are not in the edge we start with.
        return [e for e in face.edges if #Give us the edge if..
            target_verts[0] in e.verts and #The first vertex from target_verts is part of the edge (e, since we're iterating all 4 edges)..
            target_verts[1] in e.verts][0] #The second vertex from target_verts is part of the same edge.. and specifically return the first edge [0]
            #Return that edge back to partial_ring
            #Side note: I guess Maya has an extra check around in here that if the face already has 2 edges selected (or 'marked' for selection) then it's time to terminate the extension.  You'll end up with 3 edges selected (from the previous extension) if a ring loops back across the same face.
            #Or more like if the face is already selected or marked then stop.  You don't have to test number of edges that way which would be slower.
    else:
        return # Return nothing to partial_ring

def ring_end(edge):
    faces = edge.link_faces[:]
    border = len(faces) == 1 #If only one face is connected then this edge must be the border of the mesh.
    non_manifold = len(faces) > 2 #In manifold geometry one edge can only be connected to two faces.
    dead_ends = map(lambda x: len(x.verts) != 4, faces)
    return border or non_manifold or any(dead_ends)

def entire_loop(edge):
    e = edge
    v = edge.verts[0]
    loop = [edge]
    going_forward = True
    while True:
        ext = loop_extension(e, v) # Pass the edge and its starting vert to loop_extension
        if ext: # If loop_extension returns an edge, keep going.
            if going_forward:
                if ext == edge: # infinite; we've reached our starting edge and are done
                    return [edge] + loop + [edge] # Why the heck are we returning the loop and edge twice?  Loop already has edge in it.  Why not just the loop?
                else: # continue forward
                    loop.append(ext)
            else: # continue backward
                loop.insert(0, ext)
            v = ext.other_vert(v)
            e = ext
        else: # finite and we've reached an end
            if going_forward: # the first end
                going_forward = False
                e = edge
                v = edge.verts[1]
            else: # the other end
                return loop # Return the completed partial loop

def partial_ring(edge, face):
    part_ring = []
    e, f = edge, face
    while True:
        ext = ring_extension(e, f) # Pass the edge and face to ring_extension
        if not ext:
            break
        part_ring.append(ext)
        if ext == edge: # infinite; we've reached our starting edge and are done
            break
        if ring_end(ext): # Pass the edge returned from ring_extension to check if it is the end.
            break
        else:
            f = [x for x in ext.link_faces if x != f][0]
            e = ext
    return part_ring #return partial ring to entire_ring

def entire_ring(edge):
    fs = edge.link_faces #Get faces connected to this edge.
    ring = [edge]
    if len(fs) and len(fs) < 3: # First check to see if there is ANY face connected to the edge (because Blender allows for floating edges, e.g. the Ring primitive type). If there's at least 1 face, then only 2 faces are allowed to be connected to 1 edge in manifold geometry to continue.
        dirs = [ne for ne in [partial_ring(edge, f) for f in fs] if ne] #ne must stand for Next Edge? Take the edge from the input, and a face from fs and pass it to partial_ring..
        if dirs:
            if len(dirs) == 2 and set(dirs[0]) != set(dirs[1]):
                [ring.insert(0, e) for e in dirs[1]]
            ring.extend(dirs[0])
    return ring #return ring back to complete_associated_rings

def complete_associated_loops(edges):
    loops = []
    for e in edges:
        if not any([e in l for l in loops]):
            loops.append(entire_loop(e))
    return loops

def complete_associated_rings(edges):
    rings = []
    for e in edges:
        if not any([e in r for r in rings]): #Why is this line needed? It seems to be "if the edge is not in any of the rings in rings[]" but rings[] is empty.. because we just created it a moment ago.. Oh, it looks like complete_associated_rings gets re-used in another operator in Loopanar so that's why.
            rings.append(entire_ring(e))
    return rings #return rings back to select_bounded_ring

def group_unselected(edges, ends):
    gaps = [[]]
    for e in edges:
#        if not e.select: # We don't care about what's already selected because we do not want to invoke the multi-selection that Loopanar does by default.
        if e not in ends: # We only care about the gap between the two separated edges that we used to start the selection.
            gaps[-1].extend([e])
        else:
            gaps.append([])
    return [g for g in gaps if g != []]

# Takes two separated loop edges and returns a set of indices for edges in the shortest loop between them.
def select_bounded_loop(opr_selection):
    for l in complete_associated_loops(opr_selection):
        gaps = group_unselected(l, opr_selection)
        new_sel = set()
        if l[0] == l[-1]: # loop is infinite
            sg = sorted(gaps,
                key = lambda x: len(x),
                reverse = True)
            if len(sg) > 1 and len(sg[0]) > len(sg[1]): # single longest gap
                final_gaps = sg[1:]
            else:
                final_gaps = sg
        else: # loop is finite
            tails = [g for g in gaps
                if any(map(lambda x: loop_end(x), g))]
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
def select_bounded_ring(opr_selection):
    for r in complete_associated_rings(opr_selection):
        gaps = group_unselected(r, opr_selection)
        new_sel = set()
        if r[0] == r[-1]: # ring is infinite
            sg = sorted(gaps,
                key = lambda x: len(x),
                reverse = True)
            if len(sg) > 1 and len(sg[0]) > len(sg[1]): # single longest gap
                final_gaps = sg[1:]
            else: # Otherwise the lengths must be identical and there is no single longest gap?
                final_gaps = sg
        else: # ring is finite
            tails = [g for g in gaps
                if any(map(lambda x: ring_end(x), g))] # Any group of unselected edges starting at one of the opr_selection edges and extending all the way to a dead end.
            nontails = [g for g in gaps if g not in tails] # Any group between the edges in opr_selection.
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
