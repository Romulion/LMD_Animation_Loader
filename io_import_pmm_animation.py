bl_info = {
	"name": "Import Pokemon Masters Animation",
	"author": "Romulion",
	"version": (0, 9, 0),
	"blender": (2, 79, 0),
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
		#Animation = self.ConvertAnimation(AnimationRaw)
		self.maxFrames = round(AnimationLength * self.fps)
		Animation = self.ConvertAnimationStableFPS(AnimationRaw)
		self.ApplyAnimation(Animation, self.fps)
		CurFile.close()
		return {'FINISHED'}
		
	def invoke(self, context, event):
		context.window_manager.fileselect_add(self)
		return {'RUNNING_MODAL'}
		
	
	def ApplyAnimation(self, Animation, fps):
		armature = bpy.context.active_object
		armature.animation_data_clear()
		scn = bpy.context.scene
		scn.frame_set(0)
		scn.frame_start = 0
		scn.frame_end = self.maxFrames
		bpy.context.scene.render.fps = fps
		for boneName in Animation.keys():
			bonePos = armature.pose.bones[boneName]
			bone = armature.data.bones[boneName]
			bonePos.rotation_mode = "QUATERNION"
			#convert to parent - child matrix
			if bone.parent:
				parentChildMatrix = mat_mult(bone.parent.matrix_local.inverted(), bone.matrix_local)
			else:
				parentChildMatrix = bone.matrix_local
			#get parent 2 bone transform for animation conversion
			startLoc = parentChildMatrix.translation
			startRot = parentChildMatrix.to_quaternion().inverted()
			boneAnim = Animation[boneName]
			
			for i in range(len(boneAnim['transform'])):
				bonePos.location = boneAnim['transform'][i][1] - startLoc
				bonePos.rotation_quaternion = mat_mult(startRot, boneAnim['rotation'][i][1])
				bonePos.keyframe_insert(data_path = "location", frame = boneAnim['transform'][i][0], index= -1)
				bonePos.keyframe_insert(data_path = "rotation_quaternion", frame = boneAnim['rotation'][i][0])
	
	def ConvertAnimation(self, AnimationRaw):
		frameLength = 1 / self.maxFrames
		ConvertedAnimation = {}
		for bone in AnimationRaw.keys():
			boneRotData = []
			boneTransData = []
			animationData = AnimationRaw[bone]
			frameRTimeTable = animationData['rotation']['time']
			frameRotTable = animationData['rotation']['frames']
			frameTTimeTable = animationData['transform']['time']
			frameTransTable = animationData['transform']['frames']
			for i in range(self.maxFrames):
				boneRotData.append(self.Interpolate(frameRTimeTable,frameRotTable,i * frameLength, False,bone))
				boneTransData.append(self.Interpolate(frameTTimeTable,frameTransTable,i * frameLength,True,bone))
			ConvertedAnimation[bone] = {'rotation': boneRotData, 'transform': boneTransData}
				
		return ConvertedAnimation
		
	def ConvertAnimationStableFPS(self, AnimationRaw):
		framesCount = self.maxFrames
		frameLength = 1 / framesCount
		ConvertedAnimation = {}
		for bone in AnimationRaw.keys():
			boneRotData = []
			boneTransData = []
			animationData = AnimationRaw[bone]
			frameRTimeTable = animationData['rotation']['time']
			frameRotTable = animationData['rotation']['frames']
			frameTTimeTable = animationData['transform']['time']
			frameTransTable = animationData['transform']['frames']
			#first frame
			boneRotData.append((0,frameRotTable[0]))
			boneTransData.append((0,frameTransTable[0]))
			
			for i in range(1,framesCount - 1):
				currFrame = i
				boneRotData.append((i,self.Interpolate(frameRTimeTable,frameRotTable,i * frameLength, False)))
				boneTransData.append((i,self.Interpolate(frameTTimeTable,frameTransTable,i * frameLength,True)))
			
			'''			
			#reducing frames data
			lastWritten = [0,0]
			lastIndex = [0,0]
			for i in range(1,framesCount - 1):
				approxFrame = (len(frameRotTable) -1 ) * i * frameLength
				start = math.floor(approxFrame)
				#dont write key data if keys inside same interval 
				if lastIndex[0] != start:
					if lastWritten[0] != i-1:
						boneRotData.append((i-1,self.Interpolate(frameRTimeTable,frameRotTable,(i-1) * frameLength, False,bone)))
						boneTransData.append((i-1,self.Interpolate(frameTTimeTable,frameTransTable,(i-1) * frameLength,True,bone)))
						boneRotData.append((i,self.Interpolate(frameRTimeTable,frameRotTable,i * frameLength, False,bone)))
						boneTransData.append((i,self.Interpolate(frameTTimeTable,frameTransTable,i * frameLength,True,bone)))
						lastWritten = [i,i]
					lastIndex = [i,i]
			'''
			#last frame
			boneRotData.append((framesCount-1,frameRotTable[-1]))
			boneTransData.append((framesCount-1,frameTransTable[-1]))
			ConvertedAnimation[bone] = {'rotation': boneRotData, 'transform': boneTransData}
				
		return ConvertedAnimation	

	def Interpolate(self,TimeTable,frameTable,search,trans):
		#find nearest frame
		'''
		end = -1
		exact = False
		for i in range(1,len(TimeTable)):
			if TimeTable[i] == search:
				end = i
				exact = True
				break
			if TimeTable[i] > search and  TimeTable[i-1] < search:
				end = i
				break
		
		if search == 0:
			end = 0

		if end == -1:
			print("cant approximate" + str(search))
			return
			
		if exact or search == 0:
			return frameTable[end]
		'''
		#weight =  (search - TimeTable[end-1]) / (TimeTable[end] - TimeTable[end-1])
		approxFrame = (len(frameTable) -1 ) * search
		start = math.floor(approxFrame)
		weight = approxFrame - start
		if trans:
			return frameTable[start] + (frameTable[start + 1] - frameTable[start]) * weight
		else:
			return frameTable[start].slerp(frameTable[start + 1],weight)

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
			CurFile.seek(TransformFramesPointer + 4)
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
