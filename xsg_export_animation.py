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
# This file : Animation data manipulation & export.
#
# ------------------------------------------------------------------------------------------------------------------------------

import bpy
from mathutils import Vector, Matrix
from .util import Util

class Keyframe:
	def __init__(self, time, value):
		self.time = time
		self.value = value		
		
class Animation:
	def __init__(self, id):
		self.name = id
		
		self.keyframes_rotation = []
		self.keyframes_scale = []
		self.keyframes_position = []
		
	def GetKeyframeCount(self) :
		return len(self.keyframes_rotation)
		
	def Keyframes_Optimize(self, keyframes, threshold, slerp=False) :

		done = False

		while not done:
		
			done = True

			count = len(keyframes)

			if count > 2:
				for index in range(0, count-2) :
				
					time_0 = keyframes[index].time
					time_1 = keyframes[index+1].time
					time_2 = keyframes[index+2].time

					alpha = (time_1-time_0)/(time_2-time_0)

					key_0 = keyframes[index].value
					key_1 = keyframes[index+1].value
					key_2 = keyframes[index+2].value

					if slerp:
						interp = key_0.slerp(key_2, alpha)
						diff = interp - key_1
						len_squared = (diff.x * diff.x) + (diff.y * diff.y) + (diff.z * diff.z) + (diff.w * diff.w)
						zap = len_squared <= threshold   # could square root this but as it's just a threshold, it'll do & faster.
					else:
						interp = key_0.lerp(key_2, alpha)						
						diff = interp - key_1
						zap = diff.length <= threshold

					if zap:
						del keyframes[index+1]
						done = False
						break

			elif count > 1 :
				diff = keyframes[index+1].value - keyframes[index].value

				if slerp:
					len_squared = (diff.x * diff.x) + (diff.y * diff.y) + (diff.z * diff.z) + (diff.w * diff.w)
					zap = len_squared <= threshold   # could square root this but as it's just a threshold, it'll do & faster.
				else:
					zap = diff.length <= threshold
						
				if zap:
					del keyframes[index+1]
		
		
	def Optimize(self):
	
		# TODO: Add these as configuration parameters if required.
		scale_threshold = 0.01
		translation_threshold = 0.01
		rotation_threshold = 0.0001
		
		self.Keyframes_Optimize(self.keyframes_position, translation_threshold)
		self.Keyframes_Optimize(self.keyframes_scale, scale_threshold)
		self.Keyframes_Optimize(self.keyframes_rotation, rotation_threshold, slerp=True)
		

# Creates a list of animation objects based on the animation needs of the Export_Base passed to it.
class AnimationGenerator: # Base class, do not use directly.
	def __init__(self, exporter, id, export_object):
		self.exporter = exporter
		self.name = id
		self.export_object = export_object
		self.animations = []


# Creates one animation object that contains the rotation, scale, and position keyframes for the export_object
class Animation_Convert_Default(AnimationGenerator):

	def __init__(self, exporter, id, export_object):
		AnimationGenerator.__init__(self, exporter, id, export_object)
		self.Keyframes_Generate()
		
	def Keyframes_Generate(self):
		scene = bpy.context.scene
		
		blender_armatures = Util.Modifier_Armatures_Collect(self.export_object.blender_object)
		
		if len(blender_armatures) > 0:
			return
		
		if self.export_object.disable_animation:
			return

		bobj = self.export_object.blender_object
		
		# Projectors (camera, lights) point a different direction in their local coordinate system than their xsg equivalents, so we must compensate accordingly.
		is_projector = True if bobj.type  == 'CAMERA' or bobj.type  == 'LAMP' else False
		
		anim = Animation(self.export_object.name)
		
		scene = bpy.context.scene
		frame_period = scene.render.fps_base / scene.render.fps
		
		for frame in range(scene.frame_start, scene.frame_end):
			
			scene.frame_set(frame)
			
			time = (frame-scene.frame_start) * frame_period
			
			transform = self.exporter.Transform_Convert(bobj.matrix_local)
			
			if is_projector:
				transform = Util.Transform_Adjust_Projector(transform)
				
			rotation = transform.to_quaternion().normalized()
			
			anim.keyframes_rotation.append(Keyframe(time, rotation))

			scale = transform.to_scale()
			anim.keyframes_scale.append(Keyframe(time, scale))

			position = transform.to_translation()
			anim.keyframes_position.append(Keyframe(time, position))
		
		anim.Optimize()
		
		self.animations.append(anim)
		scene.frame_set(scene.frame_current)

		
# Creates an animation object for each of the export_objects

class AnimationGenerator_Group(AnimationGenerator):
	def __init__(self, exporter, id, export_objects):
		AnimationGenerator.__init__(self, exporter, id, None)
		self.export_objects = export_objects
		
		self.Keyframes_Generate()
	
	def Keyframes_Generate(self):
		for obj in self.export_objects:
			if obj.blender_object.type == 'ARMATURE':
				temporary_generator = Animation_Convert_Armature(self.exporter, None, Object)
				self.animations += temporary_generator.animations
			else:
				temporary_generator = Animation_Convert_Default(self.exporter,	None, Object)
				self.animations += temporary_generator.animations


# Creates an animation object for the armature for each bone (influence) in the armature.
class Animation_Convert_Armature(Animation_Convert_Default):
	def __init__(self, exporter, id, export_object):
		Animation_Convert_Default.__init__(self, exporter, id, export_object)
		self.Animation_Convert_Skin_Influences(exporter)
		
	def Animation_Convert_Skin_Influences(self, exporter):
		from itertools import zip_longest as zip
		
		scene = bpy.context.scene
		
		bobj = self.export_object.blender_object
		
		#anim = Animation(self.export_object.name)
		
		exporter.Log('convert_anim: ' + self.export_object.name)
		
		# Create animation objects for each influence (pose bone in Blender terminology) ...
		
		influence_animations = [Animation(Util.SafeName(skin_influence.name)) for skin_influence in bobj.pose.bones]
		
		scene = bpy.context.scene
		frame_period = scene.render.fps_base / scene.render.fps

		for frame in range(scene.frame_start, scene.frame_end):
			
			exporter.Log('frame: ' + str(frame))
			
			scene.frame_set(frame)
			
			for pose_bone, anim in zip(bobj.pose.bones, influence_animations):
							
				transform = Matrix()
				
				if pose_bone.parent:
					transform = pose_bone.parent.matrix.inverted()
				 
				# Remember Blenderp performs multiplies right to left & on matrices they're not commutitive (doh).
				transform @= pose_bone.matrix
				influence_to_parent = self.exporter.Transform_Convert(transform)
			
				time = (frame-scene.frame_start) * frame_period

				scale = influence_to_parent.to_scale()
				anim.keyframes_scale.append(Keyframe(time, scale))

				position = influence_to_parent.to_translation()
				anim.keyframes_position.append(Keyframe(time, position))
				
				rotation = influence_to_parent.to_quaternion().normalized()
				prev_rotation = anim.keyframes_rotation[-1].value if len(anim.keyframes_rotation) else rotation
				anim.keyframes_rotation.append(Keyframe(time, Util.CompatibleQuaternion(rotation, prev_rotation)))
				
				#exporter.Log('pose_bone: ' + pose_bone.name)
	
		for anim in influence_animations:
			anim.Optimize()
			self.animations.append(anim)
		
		scene.frame_set(scene.frame_current)


# Container for all animation_generators that belong in a single AnimationSet
class AnimationSet:
	def __init__(self, id, animation_generators):
		self.name = id
		self.animation_generators = animation_generators


# Writes all animation data to file.  

class AnimationWriter:
	def __init__(self, exporter, animation_generators):
		self.exporter = exporter
		self.animation_generators = animation_generators
		self.animation_sets = []
		
	# Write all animation sets. 
	def AnimationSets_Write(self):
			
		self.exporter.file.Indent()
		
		scene = bpy.context.scene
		frame_period = scene.render.fps_base / scene.render.fps
		anim_period = (scene.frame_end - scene.frame_start) * frame_period
			
		for set in self.animation_sets:
			self.exporter.Log("Writing animation set {}".format(set.name))
			
			self.exporter.file.Write('\n')
			self.exporter.file.Write('<animation period="{}" seq="l">\n'.format(anim_period))
			#self.exporter.file.Write('id="{}">\n'.format(set.name))
			self.exporter.file.Indent()
			
			# Write animation for each generator ...
			
			for generator in set.animation_generators:
			
				#self.exporter.file.Write('gen\n')
				
				for current_animation in generator.animations:
					
					#self.exporter.file.Write('anim\n')
				
					self.exporter.Log("Writing animation of {}".format(current_animation.name))
					
					# Skip animation channels containing no animation data (i.e. static content)
					if (len(current_animation.keyframes_rotation) < 2) and (len(current_animation.keyframes_scale) < 2) and (len(current_animation.keyframes_position) < 2) :
						continue
					
					self.exporter.file.Indent()
					self.exporter.file.Write('<channel id="{}" target="node">\n'.format(current_animation.name))
					self.exporter.file.Indent()
					
					if len(current_animation.keyframes_rotation) > 1 : 
					
						self.exporter.file.Write('<keyframes dest="rotation">\n');
						self.exporter.file.Indent()

						self.exporter.file.Write('<time>')
						for key in current_animation.keyframes_rotation :
							self.exporter.file.Write("{:9f} ".format(key.time), Indent=False)

						self.exporter.file.Write('</time>\n')					
					
						self.exporter.file.Write('<value>')
					
						for key in current_animation.keyframes_rotation :
							self.exporter.file.Write("{:9f} {:9f} {:9f} {:9f} ".format(key.value.x, key.value.y, key.value.z, key.value.w), Indent=False)
						
						self.exporter.file.Write('</value>\n')					
						self.exporter.file.Unindent()
						self.exporter.file.Write('</keyframes>\n')					
					
					# Write scale keys
					
					if len(current_animation.keyframes_scale) > 1 : 
					
						self.exporter.file.Write('<keyframes dest="scale">\n');
						self.exporter.file.Indent()
						
						self.exporter.file.Write('<time>')
						for key in current_animation.keyframes_scale :
							self.exporter.file.Write("{:9f} ".format(key.time), Indent=False)

						self.exporter.file.Write('</time>\n')					

						self.exporter.file.Write('<value>')
						
						for key in current_animation.keyframes_scale :
							self.exporter.file.Write("{:9f} {:9f} {:9f}  ".format(key.value[0], key.value[1], key.value[2]), Indent=False)
						
						self.exporter.file.Write('</value>\n')
						self.exporter.file.Unindent()
						self.exporter.file.Write('</keyframes>\n')
										
										
				   # Write position keys ...
					
					if len(current_animation.keyframes_position) > 1 : 
					
						self.exporter.file.Write('<keyframes dest="position">\n');
						self.exporter.file.Indent()
						
						self.exporter.file.Write('<time>')
						
						for key in current_animation.keyframes_position:
							self.exporter.file.Write("{:9f} ".format(key.time), Indent=False)
						
						self.exporter.file.Write('</time>\n')
						
						self.exporter.file.Write('<value>')
						
						for key in current_animation.keyframes_position:
							self.exporter.file.Write('{:9f} {:9f} {:9f}  '.format(key.value[0], key.value[1], key.value[2]), Indent=False)
							
						self.exporter.file.Write('</value>\n')
						self.exporter.file.Unindent()
						self.exporter.file.Write('</keyframes>\n')

					self.exporter.Log("ok")
					
					self.exporter.file.Unindent()
					self.exporter.file.Write("</channel>\n")
					self.exporter.file.Unindent()
					
			self.exporter.file.Unindent()
			self.exporter.file.Write("</animation>\n")
			
			self.exporter.Log("Finished writing animation set {}".format(set.name))
			
			self.exporter.file.Unindent()
	

# Implementation of AnimationWriter that places all generators into a single AnimationSet.
class JoinedSetAnimationWriter(AnimationWriter):
	def __init__(self, exporter, animation_generators):
		AnimationWriter.__init__(self, exporter, animation_generators)
		
		self.animation_sets = [AnimationSet("Global", self.animation_generators)]
		

# Implementation of AnimationWriter that places each generator into its own AnimationSet
class SplitSetAnimationWriter(AnimationWriter):
	def __init__(self, exporter, animation_generators):
		AnimationWriter.__init__(self, exporter, animation_generators)
		
		self.animation_sets = [AnimationSet(Generator.name, [Generator])
			for Generator in animation_generators]