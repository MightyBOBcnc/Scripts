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
    "warning": "",
    "blender": (2, 80, 0),
    "version": (0, 0, 5)
}

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
        name="Select Linked On Double Click", default=False)

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
                bpy.ops.object.mode_set(mode='OBJECT')
                selected_edges = [e for e in context.object.data.edges if e.select]

                # Switch back to edge mode
                bpy.ops.object.mode_set(mode='EDIT')
                context.tool_settings.mesh_select_mode = (False, True, False)

                if len(selected_edges) > 0:
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
        return {'CANCELLED'} #Used to return FINISHED but I think CANCELLED is the proper return?

    selected_components = [e for e in bm.edges if e.select] + [f for f in bm.faces if f.select] + [v for v in bm.verts if v.select]

    active_vert = bm.select_history.active
    previous_active_vert = bm.select_history[len(bm.select_history) - 2]

    select_vert(active_vert)

    neighbour_verts = get_neighbour_verts(bm)

    relevant_neighbour_verts = [v for v in neighbour_verts if not v == active_vert.index]

    select_vert(active_vert)
    if not previous_active_vert.index == active_vert.index:
        if previous_active_vert.index in relevant_neighbour_verts:
            previous_active_vert.select = True
            bm.select_flush_mode() #Without flushing the next operator won't recognize that there's anything to convert from vert to edge?
            bpy.ops.mesh.select_mode('INVOKE_DEFAULT', use_extend=False, use_expand=False, type='EDGE')
            
            active_edge = [e for e in bm.edges if e.select][0]
            
            if active_edge.is_boundary:
                print("Selecting Boundary Edges Then Verts")
                boundary_edges = get_boundary_edge_loop(active_edge)
                for e in boundary_edges:
                    e.select = True
                #Might need to flush again before converting back?
                bpy.ops.mesh.select_mode('INVOKE_DEFAULT', use_extend=False, use_expand=False, type='VERT')
                bm.select_history.add(active_vert) #Re-add active_vert to history to keep it active.
            else:
                print("Selecting Edge Loop Then Verts")
                bpy.ops.mesh.loop_multi_select('INVOKE_DEFAULT', ring=False)
                bpy.ops.mesh.select_mode('INVOKE_DEFAULT', use_extend=False, use_expand=False, type='VERT')
                bm.select_history.add(active_vert) #Re-add active_vert to history to keep it active.
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

    bmesh.update_edit_mesh(me)
    return {'FINISHED'}

def maya_face_select(context, prefs):
    me = context.object.data
    bm = bmesh.from_edit_mesh(me)

    if len(bm.select_history) == 0:
        return {'CANCELLED'} #Used to return FINISHED but I think CANCELLED is the proper return?

    selected_components = [e for e in bm.edges if e.select] + [f for f in bm.faces if f.select] + [v for v in bm.verts if v.select]

    active_face = bm.select_history.active
    previous_active_face = bm.select_history[len(bm.select_history) - 2]

    select_face(active_face)

    neighbour_faces = get_neighbour_faces(bm)

    relevant_neighbour_faces = [f for f in neighbour_faces if not f == active_face.index]

    select_face(active_face)

    bpy.ops.mesh.edgering_select('INVOKE_DEFAULT', ring=False)
    loop_faces = [f.index for f in bm.faces if f.select]

    select_face(active_face)        
    
    #ring=True because in some cases trying to grab loops when there are triangles touching the active_face will not result in proper selection.
    bpy.ops.mesh.loop_multi_select('INVOKE_DEFAULT', ring=True)
    #First select mode conversion has to be to Edge instead of Verts because Blender is stupid and if you have vertices selected that encompass a triangle that touches the active_face it will select that triangle because it is 'bounded' which is dead wrong.
    bpy.ops.mesh.select_mode('INVOKE_DEFAULT', use_extend=False, use_expand=False, type='EDGE')
    bpy.ops.mesh.select_mode('INVOKE_DEFAULT', use_extend=False, use_expand=False, type='FACE')
    two_loop_faces = [f.index for f in bm.faces if f.select]

    select_face(active_face)

    if previous_active_face.index in loop_faces and not previous_active_face.index == active_face.index:
        if previous_active_face.index in relevant_neighbour_faces:
            bpy.ops.mesh.edgering_select('INVOKE_DEFAULT', ring=True) #I have no idea if changing this from False to True has any implications.  I haven't seen any as of yet.
        elif active_face.index in two_loop_faces:
            previous_active_face.select = True
            """(This is not a reliable method because shortest_path_select can leave the loop to take shortcuts.)"""
            bpy.ops.mesh.shortest_path_select(use_face_step=True)
    elif previous_active_face.index in two_loop_faces and not previous_active_face.index == active_face.index: 
        if active_face.index in two_loop_faces:
            previous_active_face.select = True
            """(This is not a reliable method because shortest_path_select can leave the loop to take shortcuts.)"""
            bpy.ops.mesh.shortest_path_select(use_face_step=True)
            #If we convert to edges first we might be able to use the Loopanar ring completion to get the edges between and then convert to verticies and finally back to contained faces.
            #Nope, the ring selection gets extended from all edges of both faces except for the direction parallel to the correct ring (that part works right).
            #Perhaps instead do a full loop from all 4 edges of the first (or second, doesn't matter) face individually and then if any of those loop edges are in both of the faces then we know that is the proper direction.
            #And once we have the proper direction use the OTHER two edges from each original face to make the Loopanar ring selection.
            #Ugh, even that will run into a problem with faces that have loops that go back onto themselves (see Loop_Test_object.obj in my Documents\maya\projects\default\scenes folder).
            #Unless.. okay there may be a fix for that... if.. only 2 edges on each each face have a loop in common and neither of those edges share a vertex, we're golden.  Just select and use the OTHER two edges for our ring.
            #If each face has 3 shared loop edges in common then the one edge that shares a vertex with the other 2 edges is actually the one we can use to do our ring since it's effectively the same thing as step 2 above.
            #If each face has all 4 edges sharing a loop with all 4 edges of the other face then maybe we can try doing multiple ring selections, convert to vert, convert back to face, then count the length of each ring to face conversion and pick the shortest one as our bounded selection.
            #If the lengths are all the same, though, best we can do is throw our hands up in the air and select everything I guess?  Maya actually does something like this on  my test shape, although it selects only 2 bounded face loops instead of all 3 of them (a complete ring).
    else:
        if prefs.select_linked_on_double_click:
            bpy.ops.mesh.select_linked(delimit={'NORMAL'}) 
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
        return {'CANCELLED'} #Used to return FINISHED but I think CANCELLED is the proper return?

    #Everything that is currently selected.
    selected_components = {e for e in bm.edges if e.select} | {f for f in bm.faces if f.select} | {v for v in bm.verts if v.select}

    active_edge = bm.select_history.active
    previous_active_edge = bm.select_history[len(bm.select_history) - 2]
    opr_selection = []
    opr_selection.append(active_edge)
    opr_selection.append(previous_active_edge)

    #Deselect everything except the active edge.
    select_edge(active_edge)
    #Select an edge ring to get a list of edges.
    bpy.ops.mesh.edgering_select('INVOKE_DEFAULT', ring=True)
    ring_edges = {e.index for e in bm.edges if e.select}
    #Deselect everything except the active edge.
    select_edge(active_edge)

    #If the previous edge and current edge are different we are doing a Shift+Double Click selection? This could be a complete edge ring/loop, or partial ring/loop.
    if not previous_active_edge.index == active_edge.index:
        #If the previous edge is in the ring test selection we want some sort of ring selection.
        if previous_active_edge.index in ring_edges:
            neighbour_edges = get_neighbour_edges(bm)

            #Edges that are both in the neighbor edges and the test ring selection and aren't the active edge.
            relevant_neighbour_edges = {e for e in neighbour_edges if e in ring_edges and not e == active_edge.index}

            #Deselect everything except the active edge again.
            select_edge(active_edge)
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

            if previous_active_edge.index in loop_edges:
                #Deselect everything except the active edge.
                select_edge(active_edge)

                neighbour_edges = get_neighbour_edges(bm)
                #Edges that are both in the neighbor edges and the test loop selection and aren't the active edge.
                relevant_neighbour_edges = {e for e in neighbour_edges if e in loop_edges and not e == active_edge.index}

                #Deselect everything except the active edge.
                select_edge(active_edge)
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
        bm.select_history.clear() #Why are we clearing this history instead of adding the active edge to the history? Doesn't seem to be a problem, though.

    #Finally, in addition to the new selection we made, re-select anything that was selected back when we started.
    for component in selected_components:
        component.select = True

    bm.select_history.add(active_edge)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(me)
    return {'FINISHED'}

def get_neighbour_verts(bm):
    bpy.ops.mesh.select_more(use_face_step=False)
    neighbour_verts = [vert.index for vert in bm.verts if vert.select]
    return neighbour_verts


def get_neighbour_faces(bm):
    bpy.ops.mesh.select_more(use_face_step=False)
    neighbour_faces = [face.index for face in bm.faces if face.select]
    return neighbour_faces


def get_neighbour_edges(bm):
    #We must use face step in order to get the edges on the other side of the connected faces to find out if they're in the ring.
    bpy.ops.mesh.select_more(use_face_step=True)
    neighbour_edges = [e.index for e in bm.edges if e.select]
    return neighbour_edges


def select_edge(active_edge):
    bpy.ops.mesh.select_all(action='DESELECT')
    active_edge.select = True


def select_vert(active_vert):
    bpy.ops.mesh.select_all(action='DESELECT')
    active_vert.select = True


def select_face(active_face):
    bpy.ops.mesh.select_all(action='DESELECT')
    active_face.select = True


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
#            print("i is: " + str(i))
            break
        else:
#            print("Next Edge= " + str(new_edges[0].index))
            cur_edge = new_edges[0]
    return final_selection

######################Loopanar defs######################

def loop_extension(edge, vert):
    candidates = vert.link_edges[:]
    if len(vert.link_loops) == 4 and vert.is_manifold:
        cruft = [edge]
        for l in edge.link_loops:
            cruft.extend([l.link_loop_next.edge, l.link_loop_prev.edge])
        return [e for e in candidates if e not in cruft][0]
    else:
        return

def loop_end(edge):
    v1, v2 = edge.verts[:]
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
    else:
        return

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
        ext = loop_extension(e, v)
        if ext:
            if going_forward:
                if ext == edge: # infinite
                    return [edge] + loop + [edge]
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
                return loop

def partial_ring(edge, face):
    part_ring = []
    e, f = edge, face
    while True:
        ext = ring_extension(e, f)
        if not ext:
            break
        part_ring.append(ext)
        if ext == edge:
            break
        if ring_end(ext):
            break
        else:
            f = [x for x in ext.link_faces if x != f][0]
            e = ext
    return part_ring #return partial ring to entire_ring

def entire_ring(edge):
    fs = edge.link_faces #Get faces connected to this edge.
    ring = [edge]
    if len(fs) and len(fs) < 3: #Only 2 faces are allowed to be connected to 1 edge in manifold geometry.
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
