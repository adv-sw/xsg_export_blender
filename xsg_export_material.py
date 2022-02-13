
# Note: List of supported cycles material node types in node_wrangler.py

import bpy
import os, sys
import shutil

# debugging
# import pdb

from mathutils import Vector
from .util import Util
from .file import File

class Export_Material:
	
	@staticmethod
	def Write(exp, mtl):

		exp.file.Indent()

		# Write default material if requested to do so :
		if mtl == None :
			exp.file.Write('<material id="default"><part id="diffuse"><input color="0.5 0.5 0.5"/></part></material>\n')
			exp.file.Unindent()
			return
			
		exp.file.Write('<material id="{}'.format(Util.SafeName(mtl.name)))
		exp.file.Write('">\n', Indent=False)
		exp.file.Indent()
		
		normal_map_input = None
		
		if mtl.node_tree == None:
			
			# Diffuse
			clr = mtl.diffuse_color * mtl.diffuse_intensity
			exp.file.Write('<part id="diffuse"><input color="{:f} {:f} {:f}"/></>\n'.format(clr[0], clr[1], clr[2]))

			# Specular
			clr = mtl.specular_color * mtl.specular_intensity
			
			if (clr[0] > 0) or (clr[0] > 0) or (clr[2] > 0) :
				exp.file.Write('<part id="specular"><input color="{:f} {:f} {:f}"/></>\n'.format(clr[0], clr[1], clr[2]))
		else:
		
			# Principled BSDF conversion :
			
			principled_bsdf = mtl.node_tree.nodes.get("Principled BSDF")
			
			if principled_bsdf != None:
			
				diffuse = principled_bsdf.inputs[0]
				skip = False				
				
				if diffuse.is_linked == False :			
					color = diffuse.default_value
					skip = (color[0] == 0) and (color[1] == 0) and (color[2] == 0)
	
				if skip == False:
					Export_Material.Part_Write(exp, mtl, "diffuse", diffuse, -1)
					
				if principled_bsdf.inputs['Specular'].is_linked:
					Export_Material.Part_Write(exp, mtl, "specular", principled_bsdf.inputs['Specular'], -1)
					
					
				# We use self illum as constant channel for now
				constant_input = principled_bsdf.inputs['Emission']
				skip = False				
				
				if constant_input.is_linked == False :			
					color = constant_input.default_value
					skip = (color[0] == 0) and (color[1] == 0) and (color[2] == 0)
		
				if skip == False:
					Export_Material.Part_Write(exp, mtl, "constant", constant_input, -1)
				
				
				
				
				normal_map_input = principled_bsdf.inputs['Normal']
				
				
				
			# Diffuse BSDF : incorporates normal & diffuse
			diffuse_bsdf = mtl.node_tree.nodes.get("Diffuse BSDF")
			
			if diffuse_bsdf != None:
				Export_Material.Part_Write(exp, mtl, "diffuse", diffuse_bsdf.inputs[0], -1)
				normal_map_input = diffuse_bsdf.inputs[2]
			
			# Gloss / specular
			glossy_bsdf = mtl.node_tree.nodes.get("Glossy BSDF")
			
			if glossy_bsdf != None:
				Export_Material.Part_Write(exp, mtl, "specular", glossy_bsdf.inputs[0], glossy_bsdf.inputs[1].default_value * 1000)
			
			# Export Emission
			emission_part = mtl.node_tree.nodes.get("Emission")
			
			if emission_part != None :
				Export_Material.Part_Write(exp, mtl, "constant", emission_part.inputs[0], -1)				
				
		# Export normal if found :
		if normal_map_input != None :

			if normal_map_input.is_linked:
				nmap_input = normal_map_input.links[0].from_node
				
				# Check normal_map_input is a "Normal Map" node.
				# Blender supports a different normal map on specular & diffuse. XSG doesn't. We just check diffuse normal map & use that for both.
				if nmap_input.type == 'NORMAL_MAP' :
				
					if nmap_input.inputs[1].is_linked :
						# Range is 0 .. 10 in blender . 1 seems to mean full normal map without saturation. 
						# xsg also supports -ve value to invert normal map.
						level = nmap_input.inputs[0].default_value 
						Export_Material.Part_Write(exp, mtl, "normal", nmap_input.inputs[1], level)
				
				
				
		# TODO: Merge specular channel export into Part_Write. 
		# Need to add a flag to pick up and export gloss in addition to standard parameters.
		# Blender's range is 1 - 511. xsg is 0-1
		#Specularity = 1000 * (mtl.specular_hardness - 1.0) / 510.0
		#Specular = list(Vector(mtl.specular_color) * mtl.specular_intensity)
		#file.Write('<part id="specular" gloss={:f}><input color="{:f} {:f} {:f}"/></>\n'.format(Specularity, Specular[0], Specular[1], Specular[2]))
		
		exp.file.Unindent()
		
		exp.file.Write("</material>\n");
		exp.file.Unindent()
		
	@staticmethod
	def GetVectorInput(node):
		for inp in node.inputs:
			if inp.is_linked and inp.type == 'VECTOR' :
				l = inp.links[0]
				link_src = l.from_node
				return link_src
		return None
		
	@staticmethod
	def Map_Write(exp, node, color):
		
		Export_Material.Input_Begin(exp, node)   

		if color != None:
			exp.file.Write('color="{:f} {:f} {:f}"'.format(color[0], color[1], color[2]), Indent=False)
		
		texture_path = bpy.path.abspath(node.image.filepath, exp.src_dir)
		
		texture_filename = bpy.path.basename(texture_path)
		
		# Copy source texture file to output directory if we can find it
		if os.path.isfile(texture_path) :
			dest_path = os.path.join(exp.texture_path, texture_filename)
			shutil.copyfile(texture_path, dest_path)
		else:
			texture_filename = None   # Remove unresolved textures for now.
		#	default_source = bpy.utils.user_resource('SCRIPTS', "addons")
		#	default_source += "/io_scene_xsg/undefined.png"
		#
		#	if os.path.isfile(default_source) :
		#		shutil.copyfile(default_source, dest_path)

		vinput = Export_Material.GetVectorInput(node)
		uv_map = None
		
		scale = Vector((1,1,1))
		
		if vinput != None :
			if vinput.type == 'MAPPING':
				if vinput.vector_type == 'POINT' or vinput.vector_type == 'VECTOR' :
					scale = vinput.inputs['Scale'].default_value
				else:
					print("ignoring unsupported mapping vector_type={}".format(vinput.vector_type))
				
				# Grab mapping input ...
				vinput = Export_Material.GetVectorInput(vinput)
			elif vinput.type != 'UVMAP':  # handled below
				print("unsupported vinput_1.type={}".format(vinput.type))
				
		if vinput != None :
			if vinput.type == 'UVMAP':
				uv_map = vinput.uv_map
			else :
				print("unsupported vinput_2.type={}".format(vinput.type))
		
		if texture_filename != None:
			exp.file.Write(' scale="{} {}" src="{}"'.format(scale[0], -scale[1], texture_filename), Indent=False)
		
		if node.extension == 'CLIP':
			exp.file.Write(' addr="rclamp"', Indent=False)  # reverse clamp in XSG (0 thru -1) because must currently flip images upside down to match mapping.
		
		# Gets uv map channel name. XSG currently only supports texture coordinate set id as index reference into mesh tcoord sets.
		# Up to two sets are currently supported by Infinity. Hence anything other than the default is set 1. (default is set 0)

		if uv_map != None and uv_map != "" :
			exp.file.Write(' tcoord="1"', Indent=False)  # Actual ID is : "{}"'.format(uv_map)
			
		exp.file.Write("/>\n", Indent=False)		
	
	def Input_Begin(exp, node):

		exp.file.Write('<input ')

		if hasattr(node, 'label') :
			index = node.label.find('xsg.input:')
			if index == 0:
				exp.file.Write(node.label[10:], Indent=False) # Write the custom node property
				exp.file.Write(' ', Indent=False)

	def RGB_Write(exp, node):
		Export_Material.Input_Begin(exp, node)
		color = node.outputs[0].default_value
		exp.file.Write('color="{:f} {:f} {:f}"/>\n'.format(color[0], color[1], color[2]), Indent=False)
		
	def Input_Write(exp, src, color) :
		if src.type == 'TEX_IMAGE':
			Export_Material.Map_Write(exp, src, color)
		elif src.type == 'MIX_RGB':
			Export_Material.Mixer_Write(exp, src, src.blend_type)
		elif src.type == 'RGB':
			Export_Material.RGB_Write(exp, src)			
		elif src.type == 'INVERT':
			Export_Material.Invert_Write(exp, src, color)
		elif src.type == 'RGBTOBW' :
			if src.inputs[0].is_linked:
				Export_Material.Input_Write(exp, src.inputs[0].links[0].from_node, False)
		else:
			Export_Material.Input_Begin(exp, src)
			exp.file.Write('type="' + src.type + '"/>\n')
			
	# Implemented same way as Mixer_Write, only with type=inv. TODO: Factor
	def Invert_Write(exp, src, color) :	
		
		exp.file.Write('<mix type="inv">\n')
		exp.file.Indent()
		
		for i in src.inputs:
			if i.is_linked:
				if i.type == 'RGBA':
					Export_Material.Input_Write(exp, i.links[0].from_node, True)
				elif i.type == 'VALUE':
					Export_Material.Input_Write(exp, i.links[0].from_node, False)
								
		exp.file.Unindent()				
		exp.file.Write('</mix>\n')
		
	def Mixer_Write(exp, src, blend_type) :
	
		# Inputs: Factor is in 0, RGB inputs are 1 & 2.
	
		# Write simplistic modulate mixer in compact form
		if blend_type == 'MULTIPLY':
			if src.inputs[1].links[0].from_node.type == "RGB":
				Export_Material.Input_Write(exp, src.inputs[2].links[0].from_node, src.inputs[1].links[0].from_node.outputs[0].default_value)
			elif src.inputs[2].links[0].from_node.type == "RGB":
				Export_Material.Input_Write(exp, src.inputs[1].links[0].from_node, src.inputs[2].links[0].from_node.outputs[0].default_value)
		else:
			exp.file.Write('<mix>\n')
			exp.file.Indent()
		
			for i in src.inputs:
				if i.is_linked:
				
					input = i.links[0].from_node

					if i.name != 'Fac':  # ignore factor input for now.
						Export_Material.Input_Write(exp, input, None)
					
			exp.file.Unindent()				
			exp.file.Write('</mix>\n')
		
	@staticmethod
	def Part_Write(exp, mtl, inf_id, node_input, level) :

		exp.file.Write('<part id="')
		exp.file.Write(inf_id, Indent=False)
		exp.file.Write('"', Indent=False)
		
		if level >= 0.0 :
			exp.file.Write(' level="{}"'.format(level), Indent=False)
		
		exp.file.Write('>\n', Indent=False)			
		
		exp.file.Indent()
		
		if node_input.is_linked:
			Export_Material.Input_Write(exp, node_input.links[0].from_node, None)
		else:
			Export_Material.Input_Begin(exp, node_input.node)
			exp.file.Write('color="{:f} {:f} {:f}"'.format(node_input.default_value[0], node_input.default_value[1], node_input.default_value[2]), Indent=False)
			exp.file.Write(' ', Indent=False)
			exp.file.Write('/>\n', Indent=False)
	
		exp.file.Unindent()
		exp.file.Write('</part>\n')		