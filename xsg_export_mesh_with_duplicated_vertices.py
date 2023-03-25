import bpy
import os, sys
import shutil
from mathutils import *
from math import radians, pi
from .util import Util
from .xsg_export_base import Export_Base
#from bisect import bisect

		
# Mesh implementation of Export_Base
class Export_Mesh(Export_Base):
	def __init__(self, exporter, blender_object):
		Export_Base.__init__(self, exporter, blender_object)

	def __repr__(self):
		return "[Export_Mesh: {}]".format(self.name)

	def Write(self, flags):

		# Current implementation requires an identity transform on skinned mesh as vertices are calculated in world space not skin space.
		blender_armatures = Util.Modifier_Armatures_Collect(self.blender_object)
		if len(blender_armatures) != 0:
			t = Matrix()
		else:
			t = self.exporter.Transform_Convert(self.blender_object.matrix_local)
            
		if (flags & 1) != 0 : # skip position
			t[0][3]=0
			t[1][3]=0
			t[2][3]=0
			
		self.Write_Node_Begin(self.name, t)

		# Generate the export mesh ...

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
			depsgraph = context.evaluated_depsgraph_get() 
			object_eval = self.blender_object.evaluated_get(depsgraph)
			mesh = object_eval.to_mesh()					
			self.Mesh_Write(mesh)
			object_eval.to_mesh_clear()
			
			# Restore the deactivated Modifiers
			for modifier in DeactivatedModifierList:
				modifier.show_viewport = True   
		else:
			mesh = self.blender_object.to_mesh()  # Don't apply modifiers.
			self.Mesh_Write(mesh)
			self.blender_object.to_mesh_clear()
		
		# Cleanup
		bpy.data.meshes.remove(mesh)

		self.Write_Children(flags)
		self.Write_Node_End()

	
	def Mesh_Write(self, mesh):

		class Exporter_Poly:
			def __init__(self, material_index, vertex_indices):
				self.material_index = material_index
				self.vertex_indices = vertex_indices
		
		class Exporter_Mesh:
			def __init__(self):
				self.vertex_positions = []
				self.vertex_normals = []
				self.polygons = []
				self.next_index = 0
		
			def GetIndex(self, position, vnormal, tcoords):
			
				vertex_count = len(self.vertex_positions)
				num_tex_coord_sets = len(tcoords)
				
				for i in range(0, vertex_count): 

					tcoord_match = True
					
					for t in range(0, num_tex_coord_sets):
						current = self.texture_coordinates[t,i]
					
						if current[0] != tcoords[t][0] or current[1] != tcoords[t][1]:
							tcoord_match = False
					
					# TODO: Check within epsilon range for configurations that are close enough but not exactly the same.
					if tcoord_match and self.vertex_positions[i] == position and self.vertex_normals[i] == vnormal :
						return i
				
				# Not found, so add a new entry.
				self.vertex_positions.append(position)
				self.vertex_normals.append(vnormal)				
			
				for t in range(0, num_tex_coord_sets):
					self.texture_coordinates[t, self.next_index] = tcoords[t]
					
				self.next_index = self.next_index + 1
			
				return self.next_index - 1
				

			def GetMatchingVertexIndices(self, position):
			
				# retrieves all indices matching position, used to fix up skinning to duplicated vertices in base mesh.
				vertex_count = len(self.vertex_positions)
				
				vertex_indices = []
				
				for i in range(0, vertex_count): 

					# TODO: Check within epsilon range for configurations that are close enough but not exactly the same.
					if self.vertex_positions[i] == position :
						vertex_indices.append(i)
				
				return vertex_indices

				
			def Convert(self, mesh, exp):
			
				num_tex_coord_sets = len(mesh.uv_layers)

				if num_tex_coord_sets > exp.config.max_tcoord_channels_to_export:
					num_tex_coord_sets = exp.config.max_tcoord_channels_to_export

				# Pre-allocate texture coordinate channel storage.
				self.texture_coordinates = {} 
				
				wm = bpy.context.window_manager
				wm.progress_begin(0, len(mesh.polygons))
				
				poly_counter = 1
				update_counter = 0
				
				for polygon in mesh.polygons :
				
					poly_indices = []
					
					if poly_counter == 100:
						wm.progress_update(update_counter)
						update_counter = update_counter + 1
						poly_counter = 0
						
					poly_counter = poly_counter + 1
					
					vertex_count = len(polygon.vertices)
					
					for face_vertex in range(0, vertex_count): 
					
						vindex = polygon.vertices[face_vertex]
						v = mesh.vertices[vindex]
						
						tcoords = {}
						
						if mesh.uv_textures:
							tindex = polygon.loop_indices[face_vertex]
						
							t = 0
							for ul in mesh.uv_layers:
								tcoords[t] = ul.data[tindex].uv
								t = t + 1
								if t == num_tex_coord_sets:
									break
						
						if polygon.use_smooth :
							compound_index = self.GetIndex(v.co, v.normal, tcoords)
							poly_indices.append(compound_index)
						else:
							compound_index = self.GetIndex(v.co, polygon.normal, tcoords)
							poly_indices.append(compound_index)
							
					self.polygons.append(Exporter_Poly(polygon.material_index,poly_indices))
					
				wm.progress_end()


			def WriteConnectivity(self, file, mtl, material_index):
			
				# Write face vertex indices by material, triangulating n-gons, as is required for the optimized duplicated vertex format of XSG.
				
				found = 0
				
				if mtl == None:
					mtl_name = "default"
				else:
					mtl_name = Util.SafeName(mtl.name)
				
				for poly in self.polygons :
					if poly.material_index != material_index:
						continue
						
					if found == 0:
						file.Write('<faces size=3 material="{}">'.format(mtl_name))
						found = 1
						
					file.Write("{} {} {}  ".format(poly.vertex_indices[0], poly.vertex_indices[1], poly.vertex_indices[2]), Indent=False)
					nvertices = len(poly.vertex_indices)
					
					# triangulate n-gons. 
					# TODO: have only tested quads. might need tweaking to support higher n-gons.
					for i in range(3, nvertices): 
						file.Write("{} {} {}  ".format(poly.vertex_indices[i], poly.vertex_indices[0], poly.vertex_indices[i-1]), Indent=False)

				if found :
					file.Write("</faces>\n", Indent=False)

				
			def Write(self, exp):

				# Write vertex positions - converting from blender coord system to xsg.
				
				exp.file.Write("<position>")	
				for v in self.vertex_positions :
					exp.file.Write("{:f} {:f} {:f}  ".format(v[0], v[2], v[1]), Indent=False)
				exp.file.Write("</position>\n", Indent=False)	
					
				# Write vertex normals - converting coordinate system.
				
				if (len(self.vertex_normals) > 0) :
					exp.file.Write("<normal>")
				
					for n in self.vertex_normals :
						exp.file.Write("{:f} {:f} {:f}  ".format(n[0], n[2], n[1]), Indent=False)
				
					exp.file.Write("</normal>\n", Indent=False)

				# Write texture coordinates sets
				
				num_verts = len(self.vertex_positions)
				
				num_tex_coord_sets = len(mesh.uv_layers)
				if num_tex_coord_sets > exp.config.max_tcoord_channels_to_export:
					num_tex_coord_sets = exp.config.max_tcoord_channels_to_export
				
				for tc in range(0, num_tex_coord_sets): 
					
					exp.file.Write("<texture>")
					
					for v in range(0, num_verts): 
						tcoords = self.texture_coordinates[tc, v]
						exp.file.Write("{:f} {:f}  ".format(tcoords[0], tcoords[1]), Indent=False)

					exp.file.Write("</texture>\n", Indent=False)
				
				# Write mesh connectivity information by material
				
				material_index = 0
				
				if mesh.materials:
					for mtl in mesh.materials :
						self.WriteConnectivity(exp.file, mtl, material_index)
						material_index = material_index + 1
				else:
					self.WriteConnectivity(exp.file, None, 0)

		# Entry point.
					
		# Convert & export mesh ...
		self.exporter.Log("Converting mesh ...")
		export_mesh = Exporter_Mesh()
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
		
					armature_to_influence = bone.matrix_local.inverted()
					world_to_armature     = blender_armature.matrix_world.inverted()
					skinned_mesh_to_world = blender_object.matrix_world

					# BLENDER_MATRIX_MULTIPLY_WEIRDNESS: Blender matrix multiply operates backasswards :)  Doh !
					# Should be: (read left to right)
					#self.skin_to_influence = skinned_mesh_to_world @ world_to_armature @ armature_to_influence
					# In Blunder, you currently have to write the following : (read right to left)
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
								
				# Write the indices of the vertices this bone affects.
				self.exporter.file.Write('<vertex>')
				
				duplicated_weights = []
				
				for index, vertex_index in enumerate(cluster.source_vertex_indices):
					
					matching_vertex_indices = xmesh.GetMatchingVertexIndices(mesh.vertices[vertex_index].co)
					
					for vi in matching_vertex_indices:
						self.exporter.file.Write("{} ".format(vi), Indent=False)
						duplicated_weights.append(cluster.weights[index])
					
					if index != group_vertex_count - 1:
						self.exporter.file.Write(" ", Indent=False)
				
				self.exporter.file.Write('</>\n', Indent=False)
						
				self.exporter.file.Write('<weight>')
				
				# Write the duplicated weights for each the affected vertex and its duplicates.
				for index, vertex_weight in enumerate(duplicated_weights):
				
					self.exporter.file.Write("{:f} ".format(vertex_weight), Indent=False)
					
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