################################################################################################################################
#
# Copyright (c) 2019, Advance Software Limited. All rights reserved.
#
# Redistribution and use in source and binary forms with or without
# modification are permitted provided that the following conditions are met:
#
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#
#    * Redistributions in binary form must reproduce the above copyright
#      notice, this list of conditions and the following disclaimer in the
#      documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL ADVANCE SOFTWARE LIMITED BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# ------------------------------------------------------------------------------------------------------------------------------
#
# Blender -> eXtendable Scene Graph 3D web (XSG) file format.
#
#           For use in the <><> Infinity 3D web browser and any other applications which wish to use the format.
#           XSG is an open file format. This exporter creates XSG in text format.
#
#           You can run infinity -c myfile.xsg to encode a text format xsg file as created by this
#           exporter to its optimized binary (fastinfoset) equivalent.
#           Binary encoding is recommended for general use because files are smaller and load faster.
#
#           Infinity ships with a tool called editxsg which converts binary xsg files to 
#           their text equivalent to enable edit/inspect, then re-encodes back to binary.
#
# Author  : Advance Software Limited.
#         
# Contact : support@advance-software.com
#
#################################################################################################################################


import bpy

from mathutils import Vector, Matrix
from itertools import repeat

from .util import Util
from .xsg_export_base import Export_Base


# Notes :
#
# 1. Blender uses the right hand coordinate system with the Z axis pointing upwards whereas Infinity uses a left hand 
#    coordinate system where +z runs into the screen and y is up. This exporter converts between the two.
#
# 2. Support for all Infinity material pats (specular, lightmap, constant, normal, etc. has not yet been added. 
# 
# 3. Support for all Blender material types has not yet been added - feel free to contribute any additional required configurations.
#
# 4. Support for Infinity procedural textures such as webpage textures not yet supported - implement via texture user defined properties.
#
# 5. Blender implements scene x-ref feature via link -> group. Place whatever you want to link into the same
#    group and link it into parent scene.
#


# Takes a list, sorts it & returns equivalent sorted list with duplicates removed.
# TODO: check for equivalence within some threshold.


def sort_and_remove_duplicates(seq):
	
	seq.sort()
	checked = []
	last = None
	
	for e in seq:
	
		if e != last:
			checked.append(e)
			last = e;
		
	return checked

	
# TODO: Replace with a faster version. This is first pass to get it working.
# TODO[OPT] : this is slow, replace with binary search when working.

def Find_Sorted(key, seq):

	index = 0
	
	for e in seq:
		if key == e:
			return index
	
		index = index+1
		
	return -1
	

		
# Mesh implementation of Export_Base
class Export_Mesh(Export_Base):
	def __init__(self, exporter, blender_object):
		Export_Base.__init__(self, exporter, blender_object)

	def __repr__(self):
		return "[Export_Mesh: {}]".format(self.name)

	def Write(self):

		# Current implementation requires an identity transform on skinned mesh as vertices are calculated in world space not skin space.
		blender_armatures = Util.Modifier_Armatures_Collect(self.blender_object)
		if len(blender_armatures) != 0:
			t = Matrix()
		else:
			t = self.exporter.Transform_Convert(self.blender_object.matrix_local)
			
		self.Write_Node_Begin(self.name, t)

		# Figure out which mesh we need for export ...
		
		was_edit_mode = False

		if hasattr(bpy.context, 'edit_object') :
			if self.blender_object == bpy.context.edit_object :
				#mesh = bmesh.from_edit_mesh(self.blender_object.data)
				#self.exporter.config.report({'WARNING'}, "Mesh in edit mode detected - switching it to edit mode for export.")
				
				# Rather than grab edit mode bmesh data which differs from standard object mode mesh data and parse
				# differently, we instead just switch the edit mode mesh to object mode and grab its mesh data as normal.
				bpy.ops.object.editmode_toggle()
				was_edit_mode = True

		if self.exporter.config.apply_modifiers:
			
			# Certain modifiers shouldn't be applied in some cases.  Deactivate them until after mesh generation is complete
			DeactivatedModifierList = []
			
			# If we're exporting skinning information, don't apply armature modifiers to the mesh - they're applied run-time to skin the mesh.
			DeactivatedModifierList = [modifier
				for modifier in self.blender_object.modifiers
				if modifier.type == 'ARMATURE' and \
				modifier.show_viewport]
			
			for modifier in DeactivatedModifierList:
				modifier.show_viewport = False
				
			# Apply modifiers - invoke to_mesh() for evaluated object.
			depsgraph = bpy.context.evaluated_depsgraph_get() 
			object_eval = self.blender_object.evaluated_get(depsgraph)
			mesh = object_eval.to_mesh()

			self.Mesh_Write(mesh, object_eval)
			
			object_eval.to_mesh_clear()			

			
			# Restore the deactivated Modifiers
			for modifier in DeactivatedModifierList:
				modifier.show_viewport = True   
		else:
			mesh = self.blender_object.to_mesh()  # Don't apply modifiers.
			self.Mesh_Write(mesh, self.blender_object)
			self.blender_object.to_mesh_clear()
			
		
		# Switch back to edit mode if we toggled out of it to grab mesh data.
		if was_edit_mode :
			bpy.ops.object.editmode_toggle()

		self.Write_Children()
		self.Write_Node_End()

	
	def Mesh_Write(self, mesh, bobj):

		class Exporter_Poly:
				def __init__(self, material_index, vertex_indices, normal_indices, texture_indices):
					self.material_index = material_index
					self.vertex_indices = vertex_indices
					self.normal_indices = normal_indices
					self.texture_indices = texture_indices


		class Exporter_Mesh:
			def __init__(self):
				self.vertex_positions = []
				self.vertex_normals = []
				self.polygons = []
				self.next_index = 0
		
			def CollectVertexData(self, mesh, bobj, exp):
			
				num_tex_coord_sets = len(bobj.data.uv_layers)

				if num_tex_coord_sets > exp.config.max_tcoord_channels_to_export:
					num_tex_coord_sets = exp.config.max_tcoord_channels_to_export

				wm = bpy.context.window_manager
				wm.progress_begin(0, len(mesh.polygons))
				
				poly_counter = 1
				update_counter = 0
				
				normals = []
				tcoords = [[] for i in repeat(None, num_tex_coord_sets)]
				
				# Create component lists
				
				for polygon in mesh.polygons :
				
					poly_indices = []
					
					if poly_counter == 100:
						wm.progress_update(update_counter)
						update_counter = update_counter + 1
						poly_counter = 0
						
					poly_counter = poly_counter + 1
					
					vertex_count = len(polygon.vertices)
					
					for face_vertex in range(0, vertex_count): 
					
						#if mesh.uv_textures:

						tindex = polygon.loop_indices[face_vertex]
						t = 0
						
						for ul in mesh.uv_layers:
							
							tcoords[t].insert(0, ul.data[tindex].uv)
							t = t + 1
							
							if t == num_tex_coord_sets:
								break
						
						if polygon.use_smooth:
							vindex = polygon.vertices[face_vertex]
							v = mesh.vertices[vindex]
							normals.insert(0, v.normal)
						elif face_vertex == 0:
							normals.insert(0, polygon.normal)
							
				# Sort normals and remove duplicates
				self.vertex_normals = sort_and_remove_duplicates(normals)
				
				#print("normal_count :")
				#print(len(self.vertex_normals))
				#print("\n")

				#print("num_tex_coord_sets: {}".format(num_tex_coord_sets))
				
				self.texture_coordinates = [[] for i in repeat(None, num_tex_coord_sets)]

				# Sort tcoords and remove duplicates
				for t in range(0, num_tex_coord_sets):
					#print("here : {}".format(t))
					self.texture_coordinates[t] = sort_and_remove_duplicates(tcoords[t])
					#print("tcoord[{}].count : {}\n".format(t, len(self.texture_coordinates[t])))
			
				wm.progress_end()				

				
			def Convert(self, mesh, exp):
			
				num_tex_coord_sets = len(mesh.uv_layers)

				if num_tex_coord_sets > exp.config.max_tcoord_channels_to_export:
					num_tex_coord_sets = exp.config.max_tcoord_channels_to_export

				wm = bpy.context.window_manager
				wm.progress_begin(0, len(mesh.polygons))
				
				poly_counter = 1
				update_counter = 0
				
				for polygon in mesh.polygons :
				
					if poly_counter == 100:
						wm.progress_update(update_counter)
						update_counter = update_counter + 1
						poly_counter = 0
						
					poly_counter = poly_counter + 1
					
					vertex_count = len(polygon.vertices)

					vertex_indices = []
					normal_indices = []

					# array of lists for n texture coordinate sets.
					texture_indices = [[] for i in repeat(None, num_tex_coord_sets)]
					
					#print("\n\n[poly]\n")
					
					for face_vertex in range(0, vertex_count) : 
					
						vindex = polygon.vertices[face_vertex]
						vertex_indices.append(vindex)
						
						# normal
						if polygon.use_smooth :
							vindex = polygon.vertices[face_vertex]
							v = mesh.vertices[vindex]
							index = Find_Sorted(v.normal, self.vertex_normals)
							normal_indices.append(index)
						else:
							index = Find_Sorted(polygon.normal, self.vertex_normals) # TODO[OPT]: Only need to calc on first vert.
							normal_indices.append(index)

						#print("fv: {}\n".format(face_vertex))
							
						# texture coordinates 
						
						#if mesh.uv_textures:
						
						blender_tindex = polygon.loop_indices[face_vertex]
					
						t = 0
						for ul in mesh.uv_layers :
							#print("t (channel): {}\n".format(t))
							tcoords = ul.data[blender_tindex].uv
							#print("tcoords: {}\n".format(tcoords))
							xmesh_tindex = Find_Sorted(tcoords, self.texture_coordinates[t])
							#print("xmesh_tindex: {}\n".format(xmesh_tindex))
							dest = texture_indices[t]
							dest.append(xmesh_tindex)
							#print("texture_indices[t]: {}\n".format(dest))
							t = t + 1
							if t == num_tex_coord_sets:
								break
					
					#print(texture_indices)
							
					self.polygons.append(Exporter_Poly(polygon.material_index, vertex_indices, normal_indices, texture_indices))
					
				wm.progress_end()
					
					
			def WriteConnectivity_NonQuad(self, exp, material_index):
			
				# Write face vertex indices matching this material_index, 
				# triangulating non-quad n-gons as is necessary for the current version of xsg.	
				# When this extends, convex n-gons only. Split any concave ngons.
				
				found = False
				
				# position

				for poly in self.polygons :
				
					if poly.material_index != material_index : continue
						
					nvertices = len(poly.vertex_indices)

               # Ignore disconnected edges & points.
					if nvertices < 3 : continue
					
               # Quads are processed seperately.
					if nvertices == 4 : continue
						
					if found != True:
						found = True
						exp.file.Write('<faces size=3>\n')
						exp.file.Indent()
						exp.file.Write('<position>')
					
					exp.file.Write("{} {} {}  ".format(poly.vertex_indices[0], poly.vertex_indices[1], poly.vertex_indices[2]), Indent=False)
						
					# triangulate n-gons. 
					for i in range(3, nvertices): 
						exp.file.Write("{} {} {}  ".format(poly.vertex_indices[i], poly.vertex_indices[0], poly.vertex_indices[i-1]), Indent=False)

				if found:
					exp.file.Write("</position>\n", Indent=False)
				
			
				if found:

					# normal
				
					exp.file.Write('<normal>')
				
					for poly in self.polygons :
						
						if poly.material_index != material_index : continue
							
						nvertices = len(poly.normal_indices)
						
						if nvertices == 4 : continue

						exp.file.Write("{} {} {}  ".format(poly.normal_indices[0], poly.normal_indices[1], poly.normal_indices[2]), Indent=False)
						
						# triangulate n-gons. 
						# TODO: have only tested quads. might need tweaking to support higher n-gons.
						for i in range(3, nvertices): 
							exp.file.Write("{} {} {}  ".format(poly.normal_indices[i], poly.normal_indices[0], poly.normal_indices[i-1]), Indent=False)

					exp.file.Write("</normal>\n", Indent=False)
				
					# texture coordinates

					if len(self.texture_coordinates) > 0 :
					
						num_tex_coord_sets = len(mesh.uv_layers)
						
						if num_tex_coord_sets > exp.config.max_tcoord_channels_to_export:
							num_tex_coord_sets = exp.config.max_tcoord_channels_to_export						
						
						for t in range(0, num_tex_coord_sets): 
					
							exp.file.Write('<texture>')
							
							for poly in self.polygons :
								
								if poly.material_index != material_index : continue
								
								texture_indices = poly.texture_indices[t]
								
								nvertices = len(texture_indices)

								if nvertices == 4 : continue
								
								exp.file.Write("{} {} {}  ".format(texture_indices[0], texture_indices[1], texture_indices[2]), Indent=False)
									
								# triangulate n-gons. 
								for i in range(3, nvertices): 
									exp.file.Write("{} {} {}  ".format(texture_indices[i], texture_indices[0], texture_indices[i-1]), Indent=False)

							exp.file.Write("</texture>\n", Indent=False)
						
					exp.file.Unindent()
					exp.file.Write("</faces>\n")										

			
			def WriteConnectivity_Quad(self, exp, material_index):
			
				# Write quad face vertex indices matching this material_index
				
				found = 0
				
				found = False;
				
				# position
			
				for poly in self.polygons :
					
					if poly.material_index != material_index : continue
						
					nvertices = len(poly.vertex_indices)

					if nvertices != 4 : continue
						
					if found != True :
						found = True
						exp.file.Write('<faces size=4>\n')
						exp.file.Indent()
						exp.file.Write('<position>')
								
					exp.file.Write("{} {} {} {}  ".format(poly.vertex_indices[0], poly.vertex_indices[1], poly.vertex_indices[2], poly.vertex_indices[3]), Indent=False)
					
				if found:
					exp.file.Write("</position>\n", Indent=False)
				
				
				# normal
				if found:
					exp.file.Write('<normal>')
						
					for poly in self.polygons :
					
						if poly.material_index != material_index : continue

						nvertices = len(poly.normal_indices)

						if nvertices != 4 : continue
							
						exp.file.Write("{} {} {} {}  ".format(poly.normal_indices[0], poly.normal_indices[1], poly.normal_indices[2], poly.normal_indices[3]), Indent=False)

					exp.file.Write("</normal>\n", Indent=False)
				
				
				# texture
					
				if len(self.texture_coordinates) > 0 :
				
					if found:
					
						num_tex_coord_sets = len(mesh.uv_layers)
						
						if num_tex_coord_sets > exp.config.max_tcoord_channels_to_export:
							num_tex_coord_sets = exp.config.max_tcoord_channels_to_export
						
						for t in range(0, num_tex_coord_sets): 

							exp.file.Write('<texture>')
							
							for poly in self.polygons :
								
								if poly.material_index != material_index : continue
								
								texture_indices = poly.texture_indices[t]

								nvertices = len(texture_indices)
								
								if nvertices != 4 : continue
								
								exp.file.Write("{} {} {} {}  ".format(texture_indices[0], texture_indices[1], texture_indices[2], texture_indices[3]), Indent=False)
							
							exp.file.Write("</texture>\n", Indent=False)

				if found:
					exp.file.Unindent()
					exp.file.Write("</faces>\n")										

				
			def Write_Vertex_Normals(self, exp):

				# Write vertex normals - converting coordinate system.
				
				if (len(self.vertex_normals) > 0) :
					exp.file.Write("<normal>")
				
					for n in self.vertex_normals :
						exp.file.Write("{:f} {:f} {:f}  ".format(n[0], n[2], n[1]), Indent=False)
				
					exp.file.Write("</normal>\n", Indent=False)

				
			def Connectivity_Write(self, exp, mtl_name, material_index):
				exp.file.Write('<material id="{}">\n'.format(mtl_name))
				exp.file.Indent()
				self.WriteConnectivity_Quad(exp, material_index)
				self.WriteConnectivity_NonQuad(exp, material_index)
				exp.file.Unindent()
				exp.file.Write('</material>\n')					

			
			def Write(self, exp):

				# Write vertex positions - converting from Blender coord system to xsg.
				
				exp.file.Write("<position>")	
				for v in mesh.vertices :
					exp.file.Write("{:f} {:f} {:f}  ".format(v.co.x, v.co.z, v.co.y), Indent=False)
					
				exp.file.Write("</position>\n", Indent=False)

				self.Write_Vertex_Normals(exp)
			
				# Write texture coordinates
				
				num_tex_coord_sets = len(self.texture_coordinates)
				
				if num_tex_coord_sets > exp.config.max_tcoord_channels_to_export:
					num_tex_coord_sets = exp.config.max_tcoord_channels_to_export
				
				for t in range(0, num_tex_coord_sets) :

					exp.file.Write("<texture>")
					
					for t in self.texture_coordinates[t]:
						exp.file.Write("{:f} {:f}  ".format(t.x, t.y), Indent=False)

					exp.file.Write("</texture>\n", Indent=False)
				
				counter=1
				
				if mesh.materials:
					material_index = 0
					for mtl in mesh.materials :
						
						if mtl != None :
							mtl_name = Util.SafeName(mtl.name)
						else:
							mtl_name = "default_{}".format(counter)
							counter = counter + 1
							
						self.Connectivity_Write(exp, mtl_name, material_index)
						material_index = material_index + 1
				else:
					self.Connectivity_Write(exp, "default", 0)
					

		# Entry point.
					
		# Convert & export mesh ...
		self.exporter.Log("Converting mesh ...")
		export_mesh = Exporter_Mesh()
		
		export_mesh.CollectVertexData(mesh, bobj, self.exporter)
		export_mesh.Convert(mesh, self.exporter)
	
		self.exporter.file.Write("<mesh>\n")
		self.exporter.file.Indent()

		self.Modifier_Skinning_Write(mesh, export_mesh)
		export_mesh.Write(self.exporter)
		
		# TODO: port		
		#self.Mesh_WriteVertexColours(mesh)
			
		self.exporter.file.Unindent()
		self.exporter.file.Write("</mesh>\n".format(self.name))

		self.exporter.Log("ok")

	
	def Modifier_Skinning_Write(self, mesh, xmesh):
		# A cluster contains vertex indices and weights for the vertices that this influence affects.
		# Also calculates the skin_to_influence transform at the time the skin was applied.
		
		def matrix_difference(mat_src, mat_dst):
			mat_dst_inv = mat_dst.inverted()
			return mat_dst_inv @ mat_src
		
		class Cluster:
				def __init__(self, blender_object, blender_armature, influence_id):
					self.influence_id = influence_id
					self.name = Util.SafeName(influence_id)
					
					self.source_vertex_indices = []
					self.weights = []
					
					bone = blender_armature.data.bones[influence_id]
					
					# skin_to_influence transforms skinned mesh vertices into the coordinate system of the influence (bone)
					# when weights were applied - the rest transform.
					# weighted accumulation of vertex positions is then applied to skinned mesh vertices by transforming them from the 
					# bone's space into world space at run time to effect the skinned mesh operation.
					
					# Because skinned mesh vertices are transformed into world space, any transform directly applied to the
					# skinned mesh node is skipped in the export to ensure a correct result.
		
					bone_matrix = Matrix()

					#if bone.parent:
					#	bone_matrix = bone.matrix_local @ bone.parent.matrix_local.inverted()
					#else:
					bone_matrix = bone.matrix_local
		
					armature_to_influence = bone_matrix.inverted();
					world_to_armature     = blender_armature.matrix_world.inverted()
					skinned_mesh_to_world = blender_object.matrix_world

					# BLENDER_MATRIX_MULTIPLY_WEIRDNESS: Blender matrix multiply operates backasswards :)  Doh !
					# Should be: (read left to right)
					#self.skin_to_influence = skinned_mesh_to_world @ world_to_armature @ armature_to_influence
					# In Blunder, transforms are evaluated right to left.
					self.skin_to_influence = armature_to_influence @ world_to_armature @ skinned_mesh_to_world
					
				def AddVertex(self, index, weight):
					self.source_vertex_indices.append(index)
					self.weights.append(weight)
		

		# Although multiple armature objects are gathered, only one armature per mesh is supported.

		blender_armatures = Util.Modifier_Armatures_Collect(self.blender_object)
		
		for blender_armature in blender_armatures:
		
			# TODO: Prevent nulls ending up here - this happens when all bones are removed from a skin leaving a regular mesh.
			if not blender_armature:
				continue
				
			# Determine the names of the skinning influence clusters.
			pose_influence_ids = [bone.name for bone in blender_armature.pose.bones]
			cluster_names = [group.name for group in self.blender_object.vertex_groups]
			used_influence_ids = set(pose_influence_ids).intersection(cluster_names)
			
			# Create a skinning cluster for each influence (bone).
			skinning_clusters = [Cluster(self.blender_object,
				blender_armature, influence_id) for influence_id in used_influence_ids]
			
			# Map Blender's internal group indexing to clusters.
			group_index_to_skinning_clusters = {group.index : cluster
				for group in self.blender_object.vertex_groups
				for cluster in skinning_clusters
				if group.name == cluster.influence_id}
			
			maximum_influences_per_vertex = 0
			
			for index, vertex in enumerate(mesh.vertices):
				vertex_weight_total = 0.0
				vertex_influences = 0
				
				# Sum up the weights of groups that correspond to skin influences.
				for vertex_group in vertex.groups:
					cluster = group_index_to_skinning_clusters.get(vertex_group.group)
					if cluster is not None:
						vertex_weight_total += vertex_group.weight
						vertex_influences += 1
				
				if vertex_influences > maximum_influences_per_vertex:
					maximum_influences_per_vertex = vertex_influences
				
				# Add the vertex to the cluster it belongs to, normalizing each contribution's weight.
				for vertex_group in vertex.groups:
					cluster = group_index_to_skinning_clusters.get(vertex_group.group)
					if cluster is not None:
						weight = vertex_group.weight / vertex_weight_total
						cluster.AddVertex(index, weight)
			
			# TODO: fixup following xsg upgrade to add modifier layer. Drops straight into mesh for current spec.
			#self.exporter.file.Write('<modifier type="skin" ',)
			#self.exporter.file.Write('vmax="{}" '.format(maximum_influences_per_vertex), Indent=False)
			#self.exporter.file.Write(' total="{}"'.format(len(skinning_clusters)), Indent=False)
			#self.exporter.file.Write(">\n", Indent=False)
			#self.exporter.file.Indent()
			
			for cluster in skinning_clusters:
				self.exporter.file.Write('<influence id="{}'.format(cluster.name))
				
				group_vertex_count = len(cluster.source_vertex_indices)
				self.exporter.file.Write('" vertices="{}" '.format(group_vertex_count), Indent=False)
				
				# Write the skin to influence transform at time skin is applied
				t = self.exporter.Transform_Convert(cluster.skin_to_influence) 
				Util.Transform_Write(self.exporter.file, t)
				self.exporter.file.Write(">\n", Indent=False)

				self.exporter.file.Indent()
								
				# Write the indices of the vertices this influence affects.
				self.exporter.file.Write('<vertex>')
				
				for index, vertex_index in enumerate(cluster.source_vertex_indices):
					
					self.exporter.file.Write("{}".format(vertex_index), Indent=False)
					
					if index != group_vertex_count - 1:
						self.exporter.file.Write(" ", Indent=False)
				
				self.exporter.file.Write('</>\n', Indent=False)
						
				self.exporter.file.Write('<weight>')
				
				# Write weight for each the affected vertex
				for index, vertex_index in enumerate(cluster.source_vertex_indices):
				
					self.exporter.file.Write("{:f} ".format(cluster.weights[index]), Indent=False)
					
					if index != group_vertex_count - 1:
						self.exporter.file.Write(" ", Indent=False)

				self.exporter.file.Write('</>\n', Indent=False)

				self.exporter.file.Unindent()
				self.exporter.file.Write('</influence>\n')
			
			# TODO: Enable when modifier element has been added to xsg.
			#self.exporter.file.Unindent()
			#self.exporter.file.Write('</modifier>\n')
								
 
   # TODO: complete this.		
	def Mesh_WriteVertexColours(self, mesh):
		# If there are no vertex colors, don't write anything
		if len(mesh.vertex_colors) == 0:
			return
		
		# Gather the colors of each vertex
		vertex_colour_layer = mesh.vertex_colors.active
		vertex_colours = [vertex_colour_layer.data[Index].color for Index in
			range(0,len(mesh.vertices))]
		VertexColorCount = len(vertex_colours)
		
		self.exporter.file.Write("<color>\n".format(self.name))
		self.exporter.file.Indent()
		
		# Write the vertex colors for each vertex index.
		for index, color in enumerate(vertex_colours):
			self.exporter.file.Write("{:f} {:f} {:f}".format(color[0], color[1], color[2]))
			
			if index != VertexColorCount - 1:
				self.exporter.file.Write("  ", Indent=False)
		
		self.exporter.file.Unindent()
		self.exporter.file.Write("</color>\n", Indent=False)
