
from .util import Util


# Export_Base class wraps a Blender object and writes its data to the file

class Export_Base: # Base class, do not use directly
	def __init__(self, exporter, blender_object):
		self.exporter = exporter  # TODO: OPT - can we access this globally ?
		self.blender_object = blender_object
		self.disable_animation = False
		self.name = Util.SafeName(self.blender_object.name)
		self.children = []

	def __repr__(self):
		return "[Export_Base: {}]".format(self.blender_object.name)

	def Write(self, flags):
		t = self.exporter.Transform_Convert(self.blender_object.matrix_local)

		if (flags & 1) != 0 : # skip position
			t[0][3]=0
			t[1][3]=0
			t[2][3]=0
        
		self.Write_Node_Begin(self.name, t)
		self.Write_Children()
		self.Write_Node_End()

	def Write_Node_Begin(self, id, node_to_parent):
		self.exporter.file.Write('<node id="{}"'.format(id));
		
		Util.Transform_Write(self.exporter.file, node_to_parent)
		
		self.exporter.file.Write('>\n', Indent=False)
		self.exporter.file.Indent()
		
	def Write_Node_End(self):
		self.exporter.file.Unindent()
		self.exporter.file.Write('</node>\n')
		
	def Write_Children(self, flags):
		for child in Util.SortByNameField(self.children):
			child.Write(flags)