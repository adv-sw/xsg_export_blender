################################################################################################################################
#
# Copyright (c) 2020 - 2022, Advance Software Limited. All rights reserved.
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
# Blender -> eXtendable Scene Graph (XSG) 3D web file format.
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
import os, sys
import shutil

import mathutils
import math

from mathutils import Vector, Matrix

from .util import Util
from .file import File

from .xsg_export_base import Export_Base

from .xsg_export_material import Export_Material

from .xsg_export_mesh import Export_Mesh
#from .xsg_export_mesh_with_duplicated_vertices import Export_Mesh

from .xsg_export_animation import Animation, Keyframe, AnimationGenerator, Animation_Convert_Default, AnimationGenerator_Group, Animation_Convert_Armature, AnimationSet, AnimationWriter, JoinedSetAnimationWriter, SplitSetAnimationWriter


# Notes :
#
# 1. Blender uses the right hand coordinate system with the Z axis pointing upwards whereas Infinity uses a left hand 
#    coordinate system where +z runs into the screen and y is up. This exporter converts between the two.
#
# 2. Support for all Infinity material parts (specular, lightmap, constant, normal, etc. has not yet been added. 
# 
# 3. Support for all Blender material types has not yet been added - feel free to contribute any additional required configurations.
#
# 4. Support for Infinity procedural textures such as webpage textures not yet supported - implement via texture user defined properties.
#
# 5. Blender implements scene x-ref feature via link -> group. Place whatever you want to link into the same
#    group and link it into parent scene.
#


class XSG_Export:


   # TODO: Does not work (3.01), so can't currently export from outliner selection
	def Selected_Outliner(self):
		# Set the area to the outliner
		prev_type = bpy.context.area.type 
		bpy.context.area.type = 'OUTLINER'
		# Grab selection
		ids = bpy.context.selected_ids
		names = [o.name for o in ids]
		print (names)
		# Reset the area 
		bpy.context.area.type = prev_type  


	def __init__(self, config, context):
		self.config = config
		self.context = context

		config.apply_modifiers = True
		config.export_actions_as_sets = False
		config.max_tcoord_channels_to_export = 2

		self.flip_axis_transform = Util.GetTransform_FlipAxis()
		self.flip_axis_transform_inverse = self.flip_axis_transform.inverted()
		self.Log("<><> eXtendable Scene Graph export\n")

		self.references = []
		self.root = os.path.dirname(bpy.data.filepath)

		# Experimental - selection from outliner
		#self.Selected_Outliner()

		# Export Scene Recursively
		if self.config.selected_only:
			export_list = list(self.context.selected_objects)
		else:
			export_list = list(self.context.scene.objects)

		if self.config.seperate:
			for export in export_list:
				name = export.name.replace("/", "_") # Normalize identifier
				path = os.path.dirname(self.config.filepath) + "/" + name + ".xsg"
				self.Convert_Scene(bpy.data.filepath, path, [export], 1)
		else:
			self.Convert_Scene(bpy.data.filepath, self.config.filepath, export_list, 0)

	#def Export_Referenced_Objects(self, export_dir): # This version not currently used as can't currently access linked scene's custom properties whilst parent is loaded.

	#	while len(self.references) != 0 :

			# Copy any references from previous export so next one can create its own reference list.
	#		references = list(self.references)

			# Clear working references list ready for current iteration's contribution.
	#		self.references = []

	#		for ref in references:

	#			robj = ref[0]
	#			path = ref[1]

				# Morph Blender group filepath into absolute xsg path
	#			relative_id = remove_prefix(robj.instance_collection.library.filepath, "//")
	#			id, extension = os.path.splitext(relative_id)
	#			id += '.xsg'
	#			export_path = export_dir + id

				# Access linked group hierarchy ...
	#			robj.dupli_list_create(scene)
	#			objs = [(dobj.object) for dobj in robj.dupli_list]
	#			robj.dupli_list_clear()

				# Can't do this yet as no scene access as of 2.79
				#self.Convert_Scene(asset_path, export_path, objs, robj.instance_collection.scene, 0)


	# [WORKAROUND] : Export referenced objects via scene load/unload method.
	def SceneLoad_Export_Referenced_Objects(self, src_dir, export_dir): 

		# This currently has to be done by loading the xref'd scene as primary so we can access its scene user defined properties - there's currently
		# no other way to access them. Please fix, blender devs :)
		keep = bpy.data.filepath

		changed = False

		# Copy any references from previous export so next one can create its own reference list.
		references = list(self.references)

		# Clear exporter references list ready for next iteration.
		self.references = []

		for xref in references:

			parent_path = os.path.dirname(xref.pop())
			xref_path = remove_prefix(xref.pop(), "//")

			xref_path = parent_path + '/' + xref_path			
			xref_path_rel = os.path.relpath(xref_path, self.root)

			# Morph Blender group filepath into absolute xsg path
			id, extension = os.path.splitext(xref_path_rel)
			id += '.xsg'
			export_path = export_dir + id

			asset_path = bpy.path.abspath(xref_path, src_dir)
			bpy.ops.wm.open_mainfile(filepath=asset_path)
			changed = True

			self.Convert_Scene(asset_path, export_path, 0)

		# Return current .blend file to the one we started with.
		if changed == True :
			bpy.ops.wm.open_mainfile(filepath=keep)


	def Convert_Scene(self, src_path, export_path, export_list, flags):

		# Current implementation requires us to always export from the current main scene, loading and unloading as required
		# because there's no other way of accessing linked scene user defined properties, which we require access to.
		scene = self.context.scene

		# Grab default ref map, for cases where not specified.

		if hasattr(bpy.context.screen, 'areas'):
			for area in bpy.context.screen.areas: 
				if area.type == 'VIEW_3D':
					space = area.spaces.active
					self.default_reflection_map = space.shading.selected_studio_light.path
		else:
			self.default_reflection_map = None

		# DBG
		#if self.default_reflection_map != None:
		#	print("\n// Viewport reflection map : ")
		#	print(self.default_reflection_map)
		#	print("\n\n")

		self.Log("Convert_Scene : {}".format(src_path))

		self.src_dir = os.path.dirname(src_path)

		# Create output texture directory ...
		directory = os.path.dirname(export_path)
		self.texture_path = os.path.join(directory , "_image")

		#if not os.path.exists(self.texture_path):
		os.makedirs(self.texture_path, exist_ok=True)

		# Record all materials we locate so they can be dumped out ahead of the geometry.			
		self.scene_materials = []
		self.requires_default_material = False

		export_map = {}

		self.file = File(export_path)
		self.file.Open()

		# Map Blender objects to Export_Bases

		for bobj in export_list:

			# Ignore hidden objects
			if bobj.hide_viewport == True:
				continue

			#self.Log(bobj.type)

			if bobj.type == 'MESH':

				export_map[bobj] = Export_Mesh(self, bobj)

				# Record materials referenced by the mesh so they can be converted and written ahead of scene graph traverse/export.

				# Apply modifiers - invoke to_mesh() for evaluated object.

				# TODO: Should have a mode here for if modifiers are disabled.

				depsgraph = self.context.evaluated_depsgraph_get() 
				object_eval = bobj.evaluated_get(depsgraph)
				mesh = object_eval.to_mesh()

				if len(mesh.materials) == 0 : 
					self.requires_default_material = True

				for mtl in mesh.materials:
					self.scene_materials.append(mtl)

				object_eval.to_mesh_clear()

			elif bobj.type == 'EMPTY':

				done = False

				# Check whether this is a linked collection (xref)
				if hasattr(bobj, 'instance_type'):
					if bobj.instance_type == 'COLLECTION':
						export_map[bobj] = Export_Reference_Group(self, bobj)
						
						# Add to list of references to export after this file is done.
						ref = list()
						ref.append(bobj.instance_collection.library.filepath)
						ref.append(src_path)
						self.references.append(ref)
						done = True

				if done != True:
					export_map[bobj] = Export_Null(self, bobj)

			elif bobj.type == 'ARMATURE':
				export_map[bobj] = Export_Skin(self, bobj)
			elif bobj.type  == 'CAMERA':
				export_map[bobj] = Export_Camera(self, bobj)
			elif bobj.type  == 'LIGHT':
				export_map[bobj] = Export_Light(self, bobj)
			else:
				self.Log("Unsupported: ")
				self.Log(bobj.type)

		# Find the objects who do not have a parent or whose parent we are not exporting
		self.root_export_list = [xobj for xobj in export_map.values() if xobj.blender_object.parent not in export_list]
		self.root_export_list = Util.SortByNameField(self.root_export_list)

		self.export_list = Util.SortByNameField(export_map.values())

		# Determine each object's children from the pool of export_objects
		for xobj in export_map.values():
			children = xobj.blender_object.children
			xobj.children = []
			for child in children:
				if child in export_map:
					xobj.children.append(export_map[child])

		self.AnimationWriter = None

		if self.config.export_animation:
			self.Log("Export_Animation[begin]")

			# Collect all animated object data
			animation_generators = self.Animation_Generators_Gather()

			# Split the data up into animation sets based on user options
			if self.config.export_actions_as_sets:
				self.AnimationWriter = SplitSetAnimationWriter(self, animation_generators)
			else:
				self.AnimationWriter = JoinedSetAnimationWriter(self, animation_generators)

			self.Log("Export_Animation[end]")

		self.Log("Write[open] : " + export_path)

		self.Write_Scene(flags)

		self.Log("Write[close]")
		self.file.Close()

		self.Log("")

		export_dir = os.path.dirname(self.config.filepath)
		export_dir += '/' 

		# Export any referenced scenes (created as linked groups in blender/python)
		self.SceneLoad_Export_Referenced_Objects(self.src_dir, export_dir)
		#self.Export_Referenced_Objects(self.src_dir, export_dir)


	def Transform_Convert(self, t):
		# Convert from Blender 'Z' up to Infinity/xsg 'Y' up coordinate system.
		return self.flip_axis_transform_inverse @ t @ self.flip_axis_transform


	def Write_Scene(self, flags):

		self.XSG_Write_Header()

		# Check for supported custom properties.

		# Custom properties - in world ...
		world = bpy.data.worlds["World"]

		if world.get("xsg.scene") != None :
			self.file.Indent()
			self.file.Write(world["xsg.scene"])
			self.file.Write('\n')
			self.file.Unindent()	

		# Custom properties - in scene ...
		if self.context.scene.get("xsg.scene") != None :
			self.file.Indent()
			self.file.Write(self.context.scene["xsg.scene"])
			self.file.Write('\n')
			self.file.Unindent()


		# Write all scene materials
		for mtl in self.scene_materials:
			Export_Material.Write(self, mtl)

		if self.requires_default_material:
			Export_Material.Write(self, None)

		self.file.Write('\n')

		self.file.Indent()

		for obj in self.root_export_list:
			obj.Write(flags)

		self.file.Unindent()

		if self.AnimationWriter != None:
			self.AnimationWriter.AnimationSets_Write()

		self.file.Write('\n</scene>\n</xsg>\n')


	def Log(self, string) :
		#if self.config.verbose :
		print(string)  # Dumps to console for debug. Start blender version from shell to get at this.


	def dump(self,obj):
		for attr in dir(obj):
			if hasattr( obj, attr ):
				self.Log( "obj.%s = %s" % (attr, getattr(obj, attr)))

	def XSG_Write_Header(self) :

		ambient_defn = bpy.data.worlds["World"].node_tree

		if ambient_defn != None :
			ambient = ambient_defn.nodes["Background"].inputs[0].default_value
			self.file.Write('<?xml version="1.0"?>\n<xsg version="0.99">\n<scene ambient="{} {} {}">\n'.format(ambient[0], ambient[1], ambient[2]))
		else:
			# Hardwired if unavailable		
			self.file.Write('<?xml version="1.0"?>\n<xsg version="0.99">\n<scene ambient="0.25 0.25 0.25">\n')


	def Animation_Generators_Gather(self) :
		generators = []

		# If all animation data is to be lumped into one AnimationSet,
		if not self.config.export_actions_as_sets:
			# Build the appropriate generators for each object's type
			for obj in self.export_list:
				if obj.blender_object.type == 'ARMATURE':
					generators.append(Animation_Convert_Armature(self, None, obj))
				else:
					generators.append(Animation_Convert_Default(self, None, obj))
		else:
			# Otherwise, keep track of which objects have no action.  These will be lumped together in a Default_Action AnimationSet.
			actionless_objects = []

			for obj in self.export_list:

				if self.disable_animation:
					continue

				if obj.blender_object.animation_data is None:
					actionless_objects.append(obj)
					continue
				else:
					if obj.blender_object.animation_data.action is None:
						actionless_objects.append(obj)
						continue

				# If an object has an action, build its appropriate generator
				if obj.blender_object.type == 'ARMATURE':
					generators.append(Animation_Convert_Armature(self, Util.SafeName(obj.blender_object.animation_data.action.name), obj))
				else:
					generators.append(Animation_Convert_Default(self, Util.SafeName(obj.blender_object.animation_data.action.name), obj))

			# If we should export unused actions as if the first armature was using them
			if self.config.attach_to_first_armature:
				# Find the first armature
				first_armature = None
				for object in self.export_list:
					if object.blender_object.type == 'ARMATURE':
						first_armature = object
						break

				if first_armature is not None:
					# Determine which actions are not used
					used_actions = [blender_object.animation_data.action
						for blender_object in bpy.data.objects
						if blender_object.animation_data is not None]
					free_actions = [action for action in bpy.data.actions
						if action not in used_actions]

					# If the first armature has no action, remove it from the actionless objects so it doesn't end up in Default_Action
					if first_armature in actionless_objects and len(free_actions):
						actionless_objects.remove(first_armature)

					# Keep track of the first armature's animation data so we can restore it after export
					prev_action = None
					no_data = False
					if first_armature.blender_object.animation_data is not None:
						prev_action = first_armature.blender_object.animation_data.action
					else:
						no_data = True
						first_armature.blender_object.animation_data_create()

					# Build a generator for each unused action
					for action in free_actions:
						first_armature.blender_object.animation_data.action = action
						Generators.append(AnimationGenerator_Armature(self, Util.SafeName(Action.name), first_armature))

					# Restore old animation data
					first_armature.blender_object.animation_data.action = prev_action

					if no_data:
						first_armature.blender_object.animation_data_clear()

			# Build a special generator for all actionless objects
			if len(actionless_objects):
				generators.append(AnimationGenerator_Group(self, "Default_Action", actionless_objects))

		return generators	


def remove_prefix(text, prefix):
	if text.startswith(prefix):
		return text[len(prefix):]
	return text
	

class Export_Reference_Group(Export_Base):
	def __init__(self, exporter, blender_object) :
		Export_Base.__init__(self, exporter, blender_object)

	def __repr__(self):
		return "[Export_Base_Reference: {}]".format(self.name)

	def Write(self, flags):
		t = self.exporter.Transform_Convert(self.blender_object.matrix_local)
		self.Write_Node_Begin(self.name, t)
		self.exporter.file.Write('<object src="')

		# Morph Blender filepath into equivalent xsg path
		here = self.exporter.src_dir + '\\' + remove_prefix(self.blender_object.instance_collection.library.filepath, "//")
		relative_id = os.path.relpath(here, self.exporter.src_dir)

		# Normalize path
		relative_id = relative_id.replace('\\', '/')
		
		id, extension = os.path.splitext(relative_id)
		id += '.xsg'

		self.exporter.file.Write(id, Indent=False)
		self.exporter.file.Write('"', Indent=False)

		# Custom properties ...
		xsg_obj = self.blender_object.get("xsg.object")

		if xsg_obj != None :
			self.exporter.file.Write(">", Indent=False);
			self.exporter.file.Write('\n')
			self.exporter.file.Indent()
			self.exporter.file.Write(xsg_obj)
			self.exporter.file.Write('\n')
			self.exporter.file.Unindent()
			self.exporter.file.Write("</>\n");
		else:
			self.exporter.file.Write('/>\n', Indent=False)

		self.Write_Children(flags)
		self.Write_Node_End()


class Export_Null(Export_Base):
	def __init__(self, exporter, blender_object):
		Export_Base.__init__(self, exporter, blender_object)

	def __repr__(self):
		return "[Export_Null: {}]".format(self.name)

	def Write(self, flags):
		t = self.exporter.Transform_Convert(self.blender_object.matrix_local)

		if (flags & 1) != 0 : # skip position
			t[0][3]=0
			t[1][3]=0
			t[2][3]=0

		self.Write_Node_Begin(self.name, t)
		self.Write_Children(flags)
		self.Write_Node_End()


class Export_Camera(Export_Base):
	def __init__(self, exporter, blender_object):
		Export_Base.__init__(self, exporter, blender_object)
		# Don't export camera animation for now.
		# TODO: Make this an export option. Just disable this if you need camera animation.
		self.disable_animation = True

	def __repr__(self):
		return "[Export_Camera: {}]".format(self.name)

	def Write(self, flags):
		t = self.exporter.Transform_Convert(self.blender_object.matrix_local)
		t = Util.Transform_Adjust_Projector(t)

		if (flags & 1) != 0 : # skip position
			t[0][3]=0
			t[1][3]=0
			t[2][3]=0

		self.Write_Node_Begin(self.name, t)
		self.exporter.file.Write("<camera/>\n")
		self.Write_Children(flags)
		self.Write_Node_End()


class Export_Light(Export_Base):
	def __init__(self, exporter, blender_object):
		Export_Base.__init__(self, exporter, blender_object)

	def __repr__(self):
		return "[Export_Light: {}]".format(self.name)

	def Write(self, flags):
		
		light = self.blender_object.data
		
		t = self.exporter.Transform_Convert(self.blender_object.matrix_local)
		t = Util.Transform_Adjust_Projector(t)
        
		if (flags & 1) != 0 : # skip position
			t[0][3]=0
			t[1][3]=0
			t[2][3]=0

		self.Write_Node_Begin(self.name, t)

		# Defaults
		shadow_param = ''
		start = 20
		end = 100
		inner = 50
		outer = 60
		width = 50
		height = 60

		light_xsg_base = '<light color="{} {} {}" {}'.format(light.color[0], light.color[1], light.color[2], shadow_param)

		if light.type == 'SPOT' or light.type == 'AREA' or light.type == 'POINT'  or light.type == 'SUN' :

			if light.use_shadow :
				shadow_param = 'param="shadow:1" '
			#else:
			#	if light.shadow_method != 'NOSHADOW' :
			#		shadow_param = 'param="shadow:1" '

		if light.type == 'SPOT' or light.type == 'AREA' :
			start = light.shadow_buffer_clip_start
			end   = light.cutoff_distance
			
		elif light.type == 'SUN' :
			start = -1   # autoclip
			end   = -1     # autoclip

		if light.type == 'SPOT' :
			outer = math.degrees(light.spot_size)
			inner = outer - outer * light.spot_blend
			self.exporter.file.Write('{} type="spot" inner="{}" outer="{}" begin="{}" end="{}"/>\n'.format(light_xsg_base, inner, outer, start, end))

		elif light.type == 'AREA' :
			width  = light.size
			height = light.size_y
			# for now
			inner = light.size
			outer = light.size
			if height == 0:
				height = width

			self.exporter.file.Write('{} inner="{}" outer="{}" begin="{}" end="{}" width="{}" height="{}"/>\n'.format(light_xsg_base, inner, outer, start, end, width, height))
		elif light.type == 'POINT' :
			#self.exporter.dump(light)			
			inner = light.shadow_soft_size
			outer = light.shadow_soft_size
			self.exporter.file.Write('{} type="point" inner="{}" outer="{}"/>\n'.format(light_xsg_base, inner, outer))
		elif light.type == 'SUN' :
			inner = light.shadow_soft_size
			outer = light.shadow_soft_size
			self.exporter.file.Write('{} begin="{}" end="{}" inner="{}" outer="{}"/>\n'.format(light_xsg_base, start, end, inner, outer))
			self.exporter.dump(light)
		else :
			print(light.type);  # ignore ambient lights for now - we use scene ambient.
			#self.exporter.file.Write('{}/>\n'.format(light_xsg_base))
		
		self.Write_Children(flags)
		self.Write_Node_End()


# Skinned mesh implementation of Export_Base - called an armature in Blender.
class Export_Skin(Export_Base):
	def __init__(self, exporter, blender_object):
		Export_Base.__init__(self, exporter, blender_object)

	def __repr__(self):
		return "[Export_Skin: {}]".format(self.name)

	def Write(self, flags):
		blender_armature = self.blender_object
		t = self.exporter.Transform_Convert(self.blender_object.matrix_local)
		self.Write_Node_Begin(self.name, t)
		root_bones = [bone for bone in blender_armature.data.bones if bone.parent is None]  # pose.bones then accessed from Bones as required.
		self.Influences_Write(root_bones)
		self.Write_Node_End()
		self.Write_Children(flags)

	def Influences_Write(self, influences):

		# Export a node for each influence (blender pose bone)

		for influence in influences:

			t = Matrix()

			pose_bone = self.blender_object.pose.bones[influence.name]

			if influence.parent:
				t = pose_bone.parent.matrix.inverted()

			t @= pose_bone.matrix
			
			influence_to_parent = t

			influence_id = Util.SafeName(influence.name)
			
			t = self.exporter.Transform_Convert(influence_to_parent)
			self.Write_Node_Begin(influence_id, t)

			self.exporter.file.Indent()

			self.Influence_Write_Children(influence)
			self.exporter.file.Unindent()

			self.Write_Node_End()

	def Influence_Write_Children(self, inf):
		self.Influences_Write(Util.SortByNameField(inf.children))
