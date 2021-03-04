################################################################################################################################
#
# Copyright (c) 2020, Advance Software Limited. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification are permitted provided that the following conditions are met:
#
#	* Redistributions of source code must retain the above copyright
#	  notice, this list of conditions and the following disclaimer.
#
#	* Redistributions in binary form must reproduce the above copyright
#	  notice, this list of conditions and the following disclaimer in the
#	  documentation and/or other materials provided with the distribution.
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
################################################################################################################################

bl_info = {
	"name": "XSG Exporter",
	"author": "Advance Software Limited",
	"version": (0, 7, 0),
	"blender": (2, 90, 0),
	"location": "File > Export > XSG (.xsg)",
	"description": "<><> XSG 3D web exporter",
	"wiki_url": "http://advance-software.com/xsg",
	"category": "Import-Export"}


import bpy
from bpy.props import BoolProperty
from bpy.props import EnumProperty
from bpy.props import StringProperty


import bmesh
import os
import time
import bpy
import mathutils
import math
import random
import operator
import sys
import pickle
from bpy.props import *
from struct import pack


class XSG_Export(bpy.types.Operator) :
	"""Export to XSG"""
	
	prefs = []

	# Read preferences
	userdir = bpy.utils.resource_path('USER')
	pref_path  = os.path.join(userdir, "adv_blender_xsg_export.cfg")
	
	if os.path.isfile(pref_path) :
		file = open(pref_path)
		selected_only = file.read(1) == '1'
		export_animation = file.read(1) == '1'
		file.close()
	else :
		selected_only = False
		export_animation = False

	bl_idname = "root.xsg"
	bl_label = "<><> Export XSG"
	filepath = StringProperty(subtype='FILE_PATH')

	# Export options
	selected_only = BoolProperty(name="Selected objects only", description="Export only selected objects", default=selected_only)
	export_animation = BoolProperty(name="Export Animation", description="Export animation.", default=export_animation)
	verbose = BoolProperty(name="Verbose",  description="Additional information sent to the console for output",  default=False)
	
	def execute(self, context):
		self.filepath = bpy.path.ensure_ext(self.filepath, ".xsg")

		from . import xsg_export
		xsg_export.XSG_Export(self, context)
		
		# Serialize preferences
		userdir = bpy.utils.resource_path('USER')
		pref_path  = os.path.join(userdir,"adv_blender_xsg_export.cfg")
		
		file = open(pref_path, 'w')
		
		if self.selected_only:
			file.write('1')
		else:
			file.write('0')
		
		if self.export_animation:
			file.write('1')
		else:
			file.write('0')
			
			
		file.close()
		
	
		
	
		return {'FINISHED'}

	def invoke(self, context, event):
		if not self.filepath:
			self.filepath = bpy.path.ensure_ext(bpy.data.filepath, ".xsg")
		context.window_manager.fileselect_add(self)
		return {'RUNNING_MODAL'}


def menu_func_export(self, context):
	self.layout.operator(XSG_Export.bl_idname, text="Infinity (.xsg)")

classes = (
    XSG_Export,
	)


def register():

	from bpy.utils import register_class

	for cls in classes:
		register_class(cls)

	bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():

	bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

	from bpy.utils import unregister_class

	for cls in reversed(classes):
		unregister_class(cls)


if __name__ == "__main__":
	register()
