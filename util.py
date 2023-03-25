from math import radians, pi

import bpy
import os, sys
import shutil
from mathutils import *


# Static utilities
class Util:
	@staticmethod
	def SafeName(name):
		return name

	@staticmethod		
	def Transform_Adjust_Projector(t):
		
		t_out = Matrix()
		
		# Infinity lights look along front vector. Here we compensate for blender alternative configuration.
		t_out[0][0] =  t[0][0]
		t_out[1][0] =  t[1][0]
		t_out[2][0] =  t[2][0]

		t_out[0][1] = t[0][2]
		t_out[1][1] = t[1][2]
		t_out[2][1] = t[2][2]

		t_out[0][2] = -t[0][1]
		t_out[1][2] = -t[1][1] 
		t_out[2][2] = -t[2][1]

		t_out[0][3] = t[0][3]
		t_out[1][3] = t[1][3]
		t_out[2][3] = t[2][3]
		
		return t_out

	
	@staticmethod
	def GetTransform_FlipAxis():
		
		t = Matrix()
		# We want output transforms to use a left hand coordinate system format.
		# Blender uses another coord system with +ve y into the screen &  +ve z  pointing up. 
		
		# flip_axis_transform allows us to convert between these formats :-
		#
		# flip_axis_transform  = [1, 0, 0]
		#	                      [0, 0, 1]
		#                        [0, 1, 0]
		#                        [0, 0, 0]

		t[0][0] = 1
		t[1][0] = 0
		t[2][0] = 0
		
		t[0][1] = 0
		t[1][1] = 0
		t[2][1] = 1
		
		t[0][2] = 0
		t[1][2] = 1
		t[2][2] = 0

		t[0][3] = 0
		t[1][3] = 0
		t[2][3] = 0
		
		return t
		

	@staticmethod
	def Transform_Write(file, t):
	
		file.Write(' transform="', Indent=False)
		file.Write("{:f} {:f} {:f}  ".format(t[0][0],  t[1][0],  t[2][0]), Indent=False)
		file.Write("{:f} {:f} {:f}  ".format(t[0][1],  t[1][1],  t[2][1]), Indent=False)
		file.Write("{:f} {:f} {:f}  ".format(t[0][2],  t[1][2],  t[2][2]), Indent=False)
		file.Write("{:f} {:f} {:f}  ".format(t[0][3],  t[1][3],  t[2][3]), Indent=False)
		file.Write('"', Indent=False)

		
	@staticmethod
	def Modifier_Armatures_Collect(blender_object):
	
		skinning_modifier_list = [modifier 
		for modifier in blender_object.modifiers
		if modifier.type == 'ARMATURE' and modifier.show_viewport]
	
		if not skinning_modifier_list:
			return []
	
		return [modifier.object for modifier in skinning_modifier_list]

		
	# Used on lists of Blender objects and lists of export_objects, both of which have a name field
	@staticmethod
	def SortByNameField(List):
		def SortKey(x):
			return x.name
		
		return sorted(List, key=SortKey)
	
	# Make A compatible with B
	@staticmethod
	def CompatibleQuaternion(A, B):
		if (A.normalized().conjugated() @ B.normalized()).angle > pi:
			return -A
		else:
			return A
