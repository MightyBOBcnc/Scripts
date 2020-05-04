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
    "version": (0, 1, 0)
}

# ToDo: 
# Find out if there need to be any tests for hidden or instanced geometry when we're doing selections.
#    A quick test with the face loop and boundary loop selection near hidden faces didn't seem to show any issues.
# Replace remaining shortest_path_select use (bounded faces).
# Do some speed tests on some of these functions to measure performance.  There's always a push/pull between the speed of C when using native Blender operators, the extra overhead of doing real selections and mode switches, and using python bmesh without doing real selections or mode switches.
# Implement deselection for all methods of selection (except maybe select_linked).
#    This is actually going to be problematic because we need to track the most recent DEselected component, which Blender does not do.
#    This addon only executes on double click.  We would have to build a helper function using the @persistent decorator to maintain a deselection list (even if said list is only 2 members long).
#    And we would have to replace the regular view3d.select operator in at least 1 place (whatever the keymap is for deselecting; e.g. Ctrl+Click.. or Shift+Click if it's set to Toggle?)
#    And Blender's wonky Undo system would invalidate the deselection list although that MAY not be a problem for something as simple as tracking only 2 components.
# Find out if these selection tools can be made to work in the UV Editor.
# See if it would be feasible to implement this idea as an optional addon preference: https://blender.community/c/rightclickselect/ltbbbc/
# Something is not working right if you're working on more than one object at a time in edit mode.  It will deselect components on anything but the most recent object you were working on.
#    I checked the original version of the script and this has apparently always been the case and I just didn't notice.  So that's something to investigate now; how to retain selection across multiple objects in edit mode.
#    If I had to guess this is probably because of all the instances where the script runs select_face, select_edge, and select_vert where it deselects everything, and probably also the times where we switch selection modes (vert, edge, face), and also because we're not getting a selection to restore per object.
#    So if we could get everything done with bmesh without doing real selections I *think* we could just add to existing selection which wouldn't clear selections and hopefully then we wouldn't even need to get a list of selected components to restore at all, much less per object.

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
        name="Select Linked Faces On Double Click", default=False)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "select_linked_on_double_click")
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
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        prefs = context.preferences.addons[__name__].preferences
        if context.object.mode == ObjectMode.EDIT:
            # Checks if we are in vertex selection mode.
            if context.tool_settings.mesh_select_mode[0]:
                return maya_vert_select(context)

            # Checks if we are in edge selection mode.
            if context.tool_settings.mesh_select_mode[1]:
                return maya_edge_select(context)

            # Checks if we are in face selection mode.
            if context.tool_settings.mesh_select_mode[2]:
                if context.area.type == 'VIEW_3D':
                    return maya_face_select(context, prefs)
                elif context.area.type == 'IMAGE_EDITOR':
                    bpy.ops.uv.select_linked_pick(extend=False)

        return {'FINISHED'}
classes.append(OBJECT_OT_context_select)

def maya_vert_select(context):
    me = context.object.data
    bm = bmesh.from_edit_mesh(me)

    if len(bm.select_history) == 0:
        return {'CANCELLED'}

    selected_components = [v for v in bm.verts if v.select]# + [f for f in bm.faces if f.select] + [e for e in bm.edges if e.select]

    active_vert = bm.select_history.active
    previous_active_vert = bm.select_history[len(bm.select_history) - 2]

    relevant_neighbour_verts = get_neighbour_verts(active_vert)

    select_vert(active_vert)
    if not previous_active_vert.index == active_vert.index:
        if previous_active_vert.index in relevant_neighbour_verts:

            active_edge = [e for e in active_vert.link_edges[:] if e in previous_active_vert.link_edges[:]][0]
            
            # Instead of looping through vertices we totally cheat and use the two adjacent vertices to get an edge and then use that edge to get an edge loop.
            # The select_flush_mode near the end of maya_vert_select will handle converting the edge loop back into vertices.
            if active_edge.is_boundary:
                print("Selecting Boundary Edges Then Verts")
                boundary_edges = get_boundary_edge_loop(active_edge)
                for e in boundary_edges:
                    e.select = True
            else:
                print("Selecting Edge Loop Then Verts")
                active_edge.select = True
                bpy.ops.mesh.loop_multi_select('INVOKE_DEFAULT', ring=False)

        #Section to handle partial vertex loops (select verts between 2 endpoint verts)
        #else:
            #I suppose I could take the 2 verts (previous_active_vert and active_vert) and convert+expend them INDIVIDUALLY into Edges (similar to the relevant_neighbours, each of these conversions should be their own list), then turn those edges into loop_multi loops as sets?
            #For any edges that are in both of those sets that determines the loop that we use and discard any other edges.  But this might have issues with my Loop_Test_object.obj test file where some faces loop back on themselves?
            #Now from that loop we.. somehow use the two vertices and/or pseudo-relevant_neighbour lists from above.. to figure out what is between the verts..
            
            #Or we might just be able to utilize the Loopanar code for edges between two selected edges and just convert the two verts into edges, do the sets overlap check to determine the loop, then keep the 4 edges that are in common with that loop and run the Loopanar part.
            #Then deselect the outer two edges which were beyond the vertices and convert the edges back to vertices.. but I already see a problem if the partial vertex loop starts or ends at anything other than a quad intersection it won't expand so we can't discard what will be the real end..
    else:
        bm.select_history.add(active_vert)

    for component in selected_components:
        component.select = True

    bm.select_history.add(active_vert) #Re-add active_vert to history to keep it active.
    bm.select_flush_mode()
    bmesh.update_edit_mesh(me)
    return {'FINISHED'}

def maya_face_select(context, prefs):
    me = context.object.data
    bm = bmesh.from_edit_mesh(me)

    if len(bm.select_history) == 0:
        return {'CANCELLED'}

    selected_components = [f for f in bm.faces if f.select]# + [e for e in bm.edges if e.select] + [v for v in bm.verts if v.select]

    active_face = bm.select_history.active
    previous_active_face = bm.select_history[len(bm.select_history) - 2]

    quads = True
    if not len(active_face.verts) == 4 or not len(previous_active_face.verts) == 4:
        quads = False

    select_face(active_face) # Need to get rid of as many of these as possible.  DE-selection should ideally never need to be done at all.

    relevant_neighbour_faces = get_neighbour_faces(active_face)
    
    a_edges = active_face.edges
    p_edges = previous_active_face.edges
    if previous_active_face.index in relevant_neighbour_faces:
        ring_edge = [e for e in a_edges if e in p_edges][0] # Need to test what happens if two quads share two edges.  Testing on the Suzanne monkey nose seems to work just fine.  Maya seems to go nuts on this type of topology selection.  Winner: Blender?
    elif not previous_active_face.index in relevant_neighbour_faces:
        ring_edge = a_edges[0]

    corner_vert = ring_edge.verts[0] # Note: In theory it shouldn't matter which vertex we choose as the basis for the other_edge because loop_multi_select appears to be robust. For example, it will work on a boundary edge or from a triangle's edge just fine.
    other_edge = [e for e in a_edges if e != ring_edge and (e.verts[0].index == corner_vert.index or e.verts[1].index == corner_vert.index)][0]

#    If getting a full loop of faces is a performance issue on heavy meshes, and doing it twice is worse, maybe limit these to like 500 faces?  Most sane modeling tasks won't involve doing a bounded face loop selection with hundreds of faces between the active and previous face.
#    This does mean, however, that later in the script we can't just select a list that was already created.. we'd have to do more selections again.. 

    select_face(active_face) # This one might be unavoidable due to using shortest_path_select, but we might be able to move it inside of the elif section for that section only and don't need it for a normal loop.

    """New Code."""
    if not previous_active_face.index == active_face.index:
        if previous_active_face.index in relevant_neighbour_faces:
            print("Selecting Face Loop 1")
            loop1_faces = face_loop_from_edge(ring_edge)
            print("Selecting Final Face Loop")
            for f in loop1_faces: # We already have the loop, so just select it.
                bm.faces[f].select = True
        if not previous_active_face.index in relevant_neighbour_faces and quads == True:
            print("Selecting Face Loop 1")
            loop1_faces = face_loop_from_edge(ring_edge)
            # If we are lucky then both faces will be in the first loop and we won't even have to test a second loop. (Save time on very dense meshes with LONG face loops.)
            if previous_active_face.index in loop1_faces:
                print("Selecting Shortest Face Path")
                previous_active_face.select = True
                """(This is not a reliable method because shortest_path_select can leave the loop to take shortcuts.)"""
                bpy.ops.mesh.shortest_path_select(use_face_step=False, use_topology_distance=True) # Using topology distance seems to catch more cases which makes this slightly better?
            # If they weren't both in the first loop tested, try a second loop perpendicular to the first.
            else:
                print("Selecting Face Loop 2")
                loop2_faces = face_loop_from_edge(other_edge)
                if previous_active_face.index in loop2_faces:
                    print("Selecting Shortest Face Path")
                    previous_active_face.select = True
                    """(This is not a reliable method because shortest_path_select can leave the loop to take shortcuts.)"""
                    bpy.ops.mesh.shortest_path_select(use_face_step=False, use_topology_distance=True) # Using topology distance seems to catch more cases which makes this slightly better?
                # If it's in neither loop, select linked.
                else:
                    if prefs.select_linked_on_double_click:
                        print("Selecting Linked Faces")
                        bpy.ops.mesh.faces_select_linked_flat(sharpness=180.0)
        # If the active face isn't a quad we would have to test N loops (more than 2) which is too much.  If previous active isn't a quad it's no big deal, but... 
        # ...it would be weird if you could do a bounded face loop selection one way and not the other.  Therefore if either isn't a quad we refuse to test and just select linked (this is consistent with Maya).
        elif not previous_active_face.index in relevant_neighbour_faces and quads == False:
            if prefs.select_linked_on_double_click:
                print("Selecting Linked Faces")
                bpy.ops.mesh.faces_select_linked_flat(sharpness=180.0)
    else:
        if prefs.select_linked_on_double_click:
            print("Selecting Linked Faces")
            bpy.ops.mesh.faces_select_linked_flat(sharpness=180.0)


        #If we convert to edges first we might be able to use the Loopanar ring completion to get the edges between and then convert to verticies and finally back to contained faces.
        #Nope, the ring selection gets extended from all edges of both faces except for the direction parallel to the correct ring (that part works right).
        #Perhaps instead do a full loop from all 4 edges of the first (or second, doesn't matter) face individually and then if any of those loop edges are in both of the faces then we know that is the proper direction.
        #And once we have the proper direction use the OTHER two edges from each original face to make the Loopanar ring selection.
        #Ugh, even that will run into a problem with faces that have loops that go back onto themselves (see Loop_Test_object.obj in my Documents\maya\projects\default\scenes folder).
        #Unless.. okay there may be a fix for that... if.. only 2 edges on each each face have a loop in common and neither of those edges share a vertex, we're golden.  Just select and use the OTHER two edges for our ring.
        #If each face has 3 shared loop edges in common then the one edge that shares a vertex with the other 2 edges is actually the one we can use to do our ring since it's effectively the same thing as step 2 above.
        #If each face has all 4 edges sharing a loop with all 4 edges of the other face then maybe we can try doing multiple ring selections, convert to vert, convert back to face, then count the length of each ring to face conversion and pick the shortest one as our bounded selection.
        #If the lengths are all the same, though, best we can do is throw our hands up in the air and select everything I guess?  Maya actually does something like this on  my test shape, although it selects only 2 bounded face loops instead of all 3 of them (a complete ring).
#            bpy.ops.mesh.faces_select_linked_flat(sharpness=180.0)
            # Does running the extra code to check the angle make this slower than just selecting anything that's connected until we run out of stuff to select?  
            # On the one hand it's running in C so it's faster than python, but on the other hand it's doing extra stuff we don't need.  So would doing the 'simple' method in python be slower than the 'complex' method in C?
            
            #bpy.ops.mesh.select_linked(delimit={'NORMAL'})
            #If a mesh has any faces with flipped/reversed normals then this won't select the full mesh chunk.  
            #There doesn't seem to be a way to delimit by geometry that isn't connected.  Delimit by UV shells won't work.  
            #The mesh separate by loose parts operator somehow has logic for this.. maybe something can be gleaned from the C code.

    for component in selected_components:
        component.select = True

    bm.select_history.add(active_face)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(me)
    return {'FINISHED'}

def maya_edge_select(context):
    me = context.object.data
    bm = bmesh.from_edit_mesh(me)

    if len(bm.select_history) == 0:
        return {'CANCELLED'}

    #Everything that is currently selected.
    selected_components = [e for e in bm.edges if e.select]# + [f for f in bm.faces if f.select] + [v for v in bm.verts if v.select]

    active_edge = bm.select_history.active
    previous_active_edge = bm.select_history[len(bm.select_history) - 2]
    opr_selection = [active_edge, previous_active_edge]

    #Deselect everything except the active edge.
    select_edge(active_edge)
    #Select an edge ring to get a list of edges.
    bpy.ops.mesh.edgering_select('INVOKE_DEFAULT', ring=True) # Would be interesting to test the performance difference between edgering_select and Loopanar here.
    ring_edges = {e.index for e in bm.edges if e.select}
    #Deselect everything except the active edge.
    select_edge(active_edge)

    #If the previous edge and current edge are different we are doing a Shift+Double Click selection? This could be a complete edge ring/loop, or partial ring/loop.
    if not previous_active_edge.index == active_edge.index:
        #If the previous edge is in the ring test selection we want some sort of ring selection.
        if previous_active_edge.index in ring_edges:
            neighbour_edges = get_neighbour_edges(active_edge)

            #Edges that are both in the neighbor edges and the test ring selection and aren't the active edge.
            relevant_neighbour_edges = {e for e in neighbour_edges if e in ring_edges and not e == active_edge.index}
#            relevant_neighbour_edges = {e for e in neighbour_edges if not e == active_edge.index}

            #If the previous edge is in the relevant neighbor edges that means it's right next to it which means we want a full ring selection.
            if previous_active_edge.index in relevant_neighbour_edges:
                print("Selecting Edge Ring")
                bpy.ops.mesh.edgering_select('INVOKE_DEFAULT', ring=True)
            #If it isn't then it must be further away and we want only a partial ring between it and the active.
            else:
                previous_active_edge.select = True
                #Use Loopanar code here instead of shortest_path_select
                print("Selecting Bounded Edge Ring")
                new_sel = select_bounded_ring(opr_selection)
                for e in new_sel:
                    e.select = True

            bm.select_history.clear()

        #If the previous edge is not in the ring test selection we must have selected two edges in the same loop--not ring--and must therefore want some sort of loop selection.
        else:
            #Select an edge loop to get a list of edges.
            bpy.ops.mesh.edgering_select('INVOKE_DEFAULT', ring=False)
            loop_edges = {e.index for e in bm.edges if e.select}

            # If active_edge is boundary, redirect to the boundary edge loop function.
            if previous_active_edge.index in loop_edges and not active_edge.is_boundary:
                #Deselect everything except the active edge.
                select_edge(active_edge)

                neighbour_edges = get_neighbour_edges(active_edge)
                #Edges that are both in the neighbor edges and the test loop selection and aren't the active edge.
                relevant_neighbour_edges = {e for e in neighbour_edges if e in loop_edges and not e == active_edge.index}
#                relevant_neighbour_edges = {e for e in neighbour_edges if not e == active_edge.index}

                #If the previous edge is in the relevant neighbor edges that means it's right next to it which means we want a full loop selection.
                if previous_active_edge.index in relevant_neighbour_edges:
                    print("Selecting Edge Loop")
                    bpy.ops.mesh.edgering_select('INVOKE_DEFAULT', ring=False)
                #If it isn't then it must be further away and we want only a partial loop between it and the active.
                else:
                    previous_active_edge.select = True
                    #Use Loopanar code here instead of shortest_path_select
                    print("Selecting Bounded Edge Loop")
                    new_sel = select_bounded_loop(opr_selection)
                    for e in new_sel:
                        e.select = True

            elif active_edge.is_boundary:
                print("Selecting Boundary Edges")
                boundary_edges = get_boundary_edge_loop(active_edge)
                for e in boundary_edges:
                    e.select = True

            bm.select_history.clear()
    #I guess clicking an edge twice makes the previous and active the same?  Therefore we must be selecting a new loop that's not related to any previous selected edge.
    else:
        if active_edge.is_boundary:
            print("Selecting Boundary Edges")
            boundary_edges = get_boundary_edge_loop(active_edge)
            for e in boundary_edges:
                e.select = True
        else:
            print("Selecting Edge Loop")
            bpy.ops.mesh.edgering_select('INVOKE_DEFAULT', ring=False)
        bm.select_history.clear() #Why are we clearing this history instead of adding the active edge to the history? Doesn't seem to be a problem, though.  Maybe so we can have contiguous face loop selection on the next ring edge like Maya?  If so it isn't working.

    #Finally, in addition to the new selection we made, re-select anything that was selected back when we started.
    for component in selected_components:
        component.select = True

    bm.select_history.add(active_edge)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(me)
    return {'FINISHED'}

# Take a vertex and return a list of indicies for connected vertices.
def get_neighbour_verts(vertex):
    edges = vertex.link_edges[:]
    neighbour_verts = {v.index for e in edges for v in e.verts[:]}
    relevant_neighbour_verts = [v for v in neighbour_verts if not v == vertex.index]
    return relevant_neighbour_verts

# Take a face and return a list of indicies for connected faces.
def get_neighbour_faces(face):
    face_edges = face.edges[:]
    neighbour_faces = {f.index for e in face_edges for f in e.link_faces[:]}
    relevant_neighbour_faces = [f for f in neighbour_faces if not f == face.index]
    return relevant_neighbour_faces

# Take an edge and return a list of indicies for nearby edges.
# Will return some 'oddball' or extra edges if connected topology is triangles or poles.
# This is no worse than the old bpy.ops.mesh.select_more(use_face_step=True) method which actually returned MORE edges than this new method.
def get_neighbour_edges(edge):
    edge_loops = edge.link_loops[:]
    edge_faces = edge.link_faces[:]
    face_edges = {e for f in edge_faces for e in f.edges[:]}
    if len(edge_loops) == 0:
        ring_edges = []
    # For the next 2 elif checks, link_loop hopping is only technically accurate for quads.
    elif len(edge_loops) == 1:
        ring_edges = [edge_loops[0].link_loop_radial_next.link_loop_next.link_loop_next.edge.index]
    elif len(edge_loops) > 1:
        ring_edges = [edge_loops[0].link_loop_radial_next.link_loop_next.link_loop_next.edge.index, edge_loops[1].link_loop_radial_next.link_loop_next.link_loop_next.edge.index]
    # This returns a lot of edges if the active_edge has 1 vert connected in pole, such as the cap of a UV Sphere. But it doesn't seem problematic.
    loop_edges = [e.index for v in edge.verts for e in v.link_edges[:] if e not in face_edges]
    
    neighbour_edges = set(ring_edges + loop_edges)
    return neighbour_edges


def select_edge(edge):
    bpy.ops.mesh.select_all(action='DESELECT')
    edge.select = True


def select_vert(vertex):
    bpy.ops.mesh.select_all(action='DESELECT')
    vertex.select = True


def select_face(face):
    bpy.ops.mesh.select_all(action='DESELECT')
    face.select = True

# This takes a boundary edge and returns a list of other boundary edges that are contiguous with it in the same boundary "loop".
"""This should probably return a list of indices instead of the edges themselves."""
def get_boundary_edge_loop(active_edge):
    first_edge = active_edge
    cur_edge = active_edge
    final_selection = []
#    print("==========BEGIN!==========")
#    print("Starting Edge= " + str(cur_edge.index))
    while True:
        final_selection.append(cur_edge)
        edge_verts = cur_edge.verts
        new_edges = []
        # From vertices in the current edge get connected edges if they're boundary.
        new_edges = [e for v in edge_verts for e in v.link_edges[:] if e.is_boundary and e != cur_edge and not e in final_selection]
#        print("New Edges= " + str([e.index for e in new_edges]))
        
        if len(new_edges) == 0 or new_edges[0] == first_edge:
            break
        else:
#            print("Next Edge= " + str(new_edges[0].index))
            cur_edge = new_edges[0]
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

# This takes a ring of edges that you have already determined to be valid and returns the loop of faces that match the ring.
# Could probably use some sanity checks to ensure the ring isn't an empty list, or whether faces are all quads and such.
def face_loop_from_edge_ring(edge_ring):
    face_loop = []
    faces = []

    for e in edge_ring:
        connected_faces = e.link_faces[:]
        for f in connected_faces:
            if f not in faces:
                faces.append(f)

    for f in faces:
        connected_edges = f.edges[:]
        in_ring = []
        for e in connected_edges:
            if e in edge_ring:
                in_ring.append(e)
        if len(in_ring) >= 2 and len(in_ring) <= 4:
            face_loop.append(f)
    return face_loop

# Takes an edge and returns a loop of face indices for the ring of that edge.
def face_loop_from_edge(edge):
    loop = edge.link_loops[0]
    first_loop = loop
    cur_loop = loop
    face_list = []
    going_forward = True
    while True:
        # Jump to next loop on the same edge and walk two loops forward (opposite edge)
        next_loop = cur_loop.link_loop_radial_next.link_loop_next.link_loop_next

        next_face = next_loop.face
#        if len(next_face.verts) == 4 and next_face.index not in face_list:
        if next_face.index not in face_list:
            face_list.append(next_face.index)

        # This probably needs a proper sanity check to make sure there even is a face before we try to call the verts of said face.
        # Same for if the loop even has faces to link to.  Maybe move the edge.link_faces test to the front?
        # I think Loopanar maybe has a manifold check somewhere in the Loop selection (not ring) regarding free-floating edges with no faces.

        # If this is true then we've looped back to the beginning and are done
        if next_loop == first_loop:
            break
        # If we reach a dead end because the next face is a tri or n-gon, or the next edge is the mesh boundary
        elif len(next_face.verts) != 4 or len(next_loop.edge.link_faces) != 2:
            # If going_forward then this is the first dead end and we want to go the other way
            if going_forward:
                going_forward = False
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
    candidates = vert.link_edges[:]
#    if len(vert.link_loops) == 4 and vert.is_manifold:
    if len(candidates) == 4 and vert.is_manifold: # AFAIK the length of candidates should be the same as vert.link_loops which means we can just check length of candidates instead of performing an extra operation of getting vert_link_loops.
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

def group_unselected(edges):
    gaps = [[]]
    for e in edges:
        if not e.select:
            gaps[-1].extend([e])
        else:
            gaps.append([])
    return [g for g in gaps if g != []]

def select_bounded_loop(opr_selection):
    for l in complete_associated_loops(opr_selection):
        gaps = group_unselected(l)
        new_sel = []
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
            new_sel.extend(g)
    return new_sel

def select_bounded_ring(opr_selection):
    for r in complete_associated_rings(opr_selection):
        gaps = group_unselected(r)
        new_sel = []
        if r[0] == r[-1]: # ring is infinite
            sg = sorted(gaps,
                key = lambda x: len(x),
                reverse = True)
            if len(sg) > 1 and len(sg[0]) > len(sg[1]): # single longest gap
                final_gaps = sg[1:]
            else:
                final_gaps = sg
        else: # ring is finite
            tails = [g for g in gaps
                if any(map(lambda x: ring_end(x), g))]
            nontails = [g for g in gaps if g not in tails]
            if nontails:
                final_gaps = nontails
            else:
                final_gaps = gaps
        for g in final_gaps:
            new_sel.extend(g)
    return new_sel


def register():
    for every_class in classes:
        bpy.utils.register_class(every_class)


def unregister():
    for every_class in classes:
        bpy.utils.unregister_class(every_class)


if __name__ == "__main__":
    register()
