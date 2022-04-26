bl_info = {
	"name": "Import Pokemon Masters Animation",
	"author": "Romulion",
	"version": (0, 10, 2),
	"blender": (2, 80, 0),
	"location": "File > Import-Export",
	"description": "A tool designed to import LMD animation from the mobile game Pokemon Masters",
	"warning": "",
	"wiki_url": "",
	"tracker_url": "",
	"category": "Import-Export"}

import bpy
import bmesh
import os
import io
import struct
import math
import mathutils
import numpy as np
from bpy.props import (BoolProperty,
					   FloatProperty,
					   StringProperty,
					   EnumProperty,
					   CollectionProperty
					   )
from bpy_extras.io_utils import ImportHelper

if bpy.app.version < (2, 80, 0):
    bl_info['blender'] = (2, 79, 0)

class PokeMastAnimImport(bpy.types.Operator, ImportHelper):
	bl_idname = "import_scene.pokemonmastersanim"
	bl_label = "Import anim"
	bl_options = {'PRESET', 'UNDO'}
	
	filename_ext = ".wismda"
	filter_glob = StringProperty(
			default="*.lmd",
			options={'HIDDEN'},
			)
 
	filepath = StringProperty(subtype='FILE_PATH',)
	files = CollectionProperty(type=bpy.types.PropertyGroup)
	fps = 60
	def draw(self, context):
		layout = self.layout

	def execute(self, context):
		#skip if no armature binded
		if not bpy.context.active_object or bpy.context.active_object.type != 'ARMATURE':
			return {'CANCELLED'}
		
		CurFile = open(self.filepath,"rb")
		
		CurFile.seek(100)
		AnimationLength = struct.unpack('f', CurFile.read(4))[0]
		
		AnimationRaw = self.ReadAnimation(CurFile,116)
		self.maxFrames = round(AnimationLength * self.fps)
		self.ApplyAnimation(AnimationRaw, self.fps)
		CurFile.close()
		return {'FINISHED'}
		
	def invoke(self, context, event):
		context.window_manager.fileselect_add(self)
		return {'RUNNING_MODAL'}

	def ApplyAnimation(self, AnimationRaw, fps):
		armature = bpy.context.active_object
		armature.animation_data_clear()
		scn = bpy.context.scene
		scn.frame_set(0)
		scn.frame_start = 0
		scn.frame_end = self.maxFrames
		bpy.context.scene.render.fps = fps

		mat_identity = mathutils.Matrix.Identity(4)

		for boneName in AnimationRaw.keys():
			#skip non existent bones
			if boneName not in armature.pose.bones:
				continue

			boneRotData = []
			boneTransData = []
			animationData = AnimationRaw[boneName]

			bonePos = armature.pose.bones[boneName]
			bone = armature.data.bones[boneName]
			bonePos.rotation_mode = "QUATERNION"

			#convert to parent - child matrix
			if bone.parent:
				parentChildMatrix = mat_mult(bone.parent.matrix_local.inverted(), bone.matrix_local)
			else:
				parentChildMatrix = bone.matrix_local

			#check if matrix invertable
			if parentChildMatrix != mat_identity:
				parentChildMatrix.invert()
			#get parent 2 bone transform for animation conversion
			#startLoc = parentChildMatrix.translation
			startRot = parentChildMatrix.to_quaternion()

			animationData = self.PrecessAnimation(animationData, boneName)
			animationRotaion = animationData['rotation']
			animationTranslate = animationData['transform']

			#adding rotation frames
			for i in range(len(animationRotaion['time'])):
				bonePos.rotation_quaternion = mat_mult(startRot, animationRotaion['frames'][i])
				bonePos.keyframe_insert(data_path = "rotation_quaternion", frame = animationRotaion['time'][i])

			#adding translation frames
			for n in range(len(animationTranslate['time'])):
				bonePos.location = mat_mult(parentChildMatrix,  animationTranslate['frames'][n])
				bonePos.keyframe_insert(data_path = "location", frame = animationTranslate['time'][n])

	def PrecessAnimation(self, animationData, name):

		animationRotaion = animationData['rotation']
		animationTranslate = animationData['transform']
		for i in range(len(animationTranslate['time'])):
			animationTranslate['time'][i] = round(animationTranslate['time'][i] * self.maxFrames)

		for i in range(len(animationRotaion['time'])):
			animationRotaion['time'][i] = round(animationRotaion['time'][i] * self.maxFrames)
		
		#fix wrong quaternion interpolation
		i = 0
		prev_frame = { "frames":  animationRotaion['frames'][0], "time": animationRotaion['time'][0]}
		for n in range(len(animationRotaion['frames'])):
			frames_passed = animationRotaion['time'][i] - prev_frame['time']
			if frames_passed > 1:

				end_frame = animationRotaion['frames'][i]
				#add between frames
				for m in range(1, frames_passed):
					animationRotaion["frames"].insert(i,  prev_frame["frames"].slerp(end_frame, m / frames_passed))
					animationRotaion["time"].insert(i,  prev_frame['time'] + m)
					i = i + 1

			prev_frame = { "frames":  animationRotaion['frames'][i], "time": animationRotaion['time'][i]}
			i = i + 1
		
		return {'rotation': animationRotaion, 'transform': animationTranslate}

	def ReadString(self, CurFile,Start):
		CurFile.seek(Start)
		StringLength = int.from_bytes(CurFile.read(4),byteorder='little')
		return CurFile.read(StringLength).decode('utf-8')
	
	def ReadAnimation(self, CurFile, StartAddr):
		self.maxFrames = 1
		CurFile.seek(116)
		bonesCount = int.from_bytes(CurFile.read(4),byteorder='little')
		startPosition = CurFile.tell()
		bonePointers = []
		for i in range(bonesCount):
			bonePointers.append(CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little'))
		
		
		animationData = {}
		for boneAddr in bonePointers:
			CurFile.seek(boneAddr+4)
			BoneNamePointer = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
			BoneName = self.ReadString(CurFile,BoneNamePointer)
			CurFile.seek(boneAddr + 20)
			AnimComponentPointer = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
			
			CurFile.seek(AnimComponentPointer + 12)
			RotationFramesPointer = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
			
			CurFile.seek(AnimComponentPointer + 16)
			TransformFramesPointer = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
			
			#Transforms
			CurFile.seek(TransformFramesPointer + 4)
			TransformTimeTable = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
			#time
			TimeTable = []
			CurFile.seek(TransformTimeTable)
			timeCount = int.from_bytes(CurFile.read(4),byteorder='little')
			for t in range(timeCount):
				TimeTable.append(struct.unpack('f', CurFile.read(4))[0])

			#transform frames
			TransformTable = []
			CurFile.seek(TransformFramesPointer + 12)
			framesCount = int.from_bytes(CurFile.read(4),byteorder='little')
			for t in range(int(framesCount/3)):
				TransformTable.append(mathutils.Vector(struct.unpack('fff', CurFile.read(4*3))))
				
			#Rotation
			CurFile.seek(RotationFramesPointer + 4)
			RotationTimeTable = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
			
			#time
			TimeTable1 = []
			CurFile.seek(RotationTimeTable)
			timeCount = int.from_bytes(CurFile.read(4),byteorder='little')
			for t in range(timeCount):
				TimeTable1.append(struct.unpack('f', CurFile.read(4))[0])
			#rotation frames
			RotationTable = []
			CurFile.seek(RotationFramesPointer + 12)
			framesCount = int.from_bytes(CurFile.read(4),byteorder='little')
			for t in range(int(framesCount/4)):
				temtQuat = mathutils.Quaternion(struct.unpack('ffff', CurFile.read(4*4)))
				w = temtQuat.z
				temtQuat.z = temtQuat.y
				temtQuat.y = temtQuat.x
				temtQuat.x = temtQuat.w
				temtQuat.w = w
				RotationTable.append(temtQuat)
				
			animationData[BoneName] = { 
				'rotation' : { 'time' : TimeTable1, 'frames' : RotationTable},
				'transform' : { 'time' : TimeTable, 'frames' : TransformTable}
			}
			self.maxFrames = max(self.maxFrames, timeCount)
			
		return 	animationData


def mat_mult(mat1, mat2):
	if bpy.app.version >= (2, 80, 0):
		return mat1 @ mat2
	return mat1 * mat2

def select_all(select):
	if select:
		actionString = 'SELECT'
	else:
		actionString = 'DESELECT'

	if bpy.ops.object.select_all.poll():
		bpy.ops.object.select_all(action=actionString)

	if bpy.ops.mesh.select_all.poll():
		bpy.ops.mesh.select_all(action=actionString)

	if bpy.ops.pose.select_all.poll():
		bpy.ops.pose.select_all(action=actionString)

def utils_set_mode(mode):
	if bpy.ops.object.mode_set.poll():
		bpy.ops.object.mode_set(mode=mode, toggle=False)

def menu_func_import(self, context):
	self.layout.operator(PokeMastAnimImport.bl_idname, text="Pokemon Masters Animations(.lmd)")		
		
def register():
	bpy.utils.register_class(PokeMastAnimImport)
	if bpy.app.version >= (2, 80, 0):
		bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
	else:
		bpy.types.INFO_MT_file_import.append(menu_func_import)

def unregister():
	bpy.utils.unregister_class(PokeMastAnimImport)
	if bpy.app.version >= (2, 80, 0):
		bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
	else:
		bpy.types.INFO_MT_file_import.remove(menu_func_import)
	
if __name__ == "__main__":
	register()
