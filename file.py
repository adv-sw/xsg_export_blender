
# Interface to the output file. Text mode (the only mode supported at this time) features optional hierarchy indenting for improved readibility.
class File:
	def __init__(self, filepath):
		self.filepath = filepath
		self.file = None
		self.intentation_level = 0

	def Open(self):
		if not self.file:
			self.file = open(self.filepath, 'w')

	def Close(self):
		self.file.close()
		self.file = None

	def Write(self, String, Indent=True):
		if Indent:
			self.file.write(("{}" + String).format("\t" * self.intentation_level))
		else:
			self.file.write(String)

	def Indent(self, Levels=1):
		self.intentation_level += Levels

	def Unindent(self, Levels=1):
		self.intentation_level -= Levels
		if self.intentation_level < 0:
			self.intentation_level = 0

