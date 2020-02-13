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

class PokeMastAnimImport():

	def execute(self):
		#skip if no armature binded
		if not bpy.context.active_object or bpy.context.active_object.type != 'ARMATURE':
			print("Armature not selected")
			return
			
		CurFile = open(self.filepath2,"rb")
		
		AnimationRaw = self.ReadAnimation(CurFile,116)
		Animation = self.ConvertAnimation(AnimationRaw)
		CurFile.seek(100)
		AnimationLength = struct.unpack('f', CurFile.read(4))[0]
		ApplyAnimation(Animation, AnimationLength)
		CurFile.close()
		
	def ApplyAnimation(self, Animation, AnimationLength):
		armature = bpy.context.active_object
		armature.animation_data_clear()
		scn = bpy.context.scene
		scn.frame_set(0)
		bpy.context.scene.render.fps = self.maxFrames / AnimationLength
		
		for boneName in Animation.keys():
			bone = armature.bones[boneName]
			boneAnim = Animation[boneName]
			bone.rotation_mode = "QUATERNION"
			for i in range(self.maxFrames):
				bone.location = boneAnim['transform'][i]
				bone.rotation_quaternion = boneAnim['rotation'][i]
				bone.keyframe_insert(data_path = "location", frame = i, index= -1)
				bone.keyframe_insert("rotation_quaternion", frame = i)
	
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
				boneRotData.append(self.Interpolete(frameRTimeTable,frameRotTable,i * frameLength, False))
				boneTransData.append(self.Interpolete(frameTTimeTable,frameTransTable,i * frameLength,True))
			ConvertedAnimation[bone] = {'rotation': boneRotData, 'transform': boneTransData}
		return ConvertedAnimation	

	def Interpolete(self,TimeTable,frameTable,search,trans):
		#find nearest frame
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
			#print(TimeTable)
			print("cant approximate" + str(search))
			return
			
		if exact or search == 0:
			return frameTable[end]

		weight =  (search - TimeTable[end-1]) / (TimeTable[end] - TimeTable[end-1])
		if trans:
			return frameTable[end-1] + (frameTable[end] - frameTable[end-1]) * weight
		else:
			return self.Slerp(frameTable[end-1],frameTable[end],weight)

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
				TransformTable.append(np.array(struct.unpack('fff', CurFile.read(4*3))))
				
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
				RotationTable.append(struct.unpack('ffff', CurFile.read(4*4)))
				
			animationData[BoneName] = { 
				'rotation' : { 'time' : TimeTable1, 'frames' : RotationTable},
				'transform' : { 'time' : TimeTable, 'frames' : TransformTable}
			}
			self.maxFrames = max(self.maxFrames, timeCount)
			
		return 	animationData

	def Slerp(self, qa,qb,degree):
		qm = [0,0,0,0]
		# Calculate angle between quaternions.
		cosHalfTheta = qa[3] * qb[3] + qa[0] * qb[0] + qa[1] * qb[1] + qa[2] * qb[2]
		# if qa=qb or qa=-qb then theta = 0 and we can return qa
		if abs(cosHalfTheta) >= 1.0:
			qm[3] = qa[3];qm[1] = qa[1];qm[2] = qa[2];qm[2] = qa[2]
			return qm

		halfTheta = math.acos(cosHalfTheta)
		sinHalfTheta = math.sqrt(1.0 - cosHalfTheta*cosHalfTheta)
		if abs(sinHalfTheta) < 0.001:
			qm[3] = (qa[3] * 0.5 + qb[3] * 0.5)
			qm[0] = (qa[0] * 0.5 + qb[0] * 0.5)
			qm[1] = (qa[1] * 0.5 + qb[1] * 0.5)
			qm[2] = (qa[2] * 0.5 + qb[2] * 0.5)
			return qm
		
		ratioA = math.sin((1 - degree) * halfTheta) / sinHalfTheta
		ratioB = math.sin(degree * halfTheta) / sinHalfTheta
		
		qm[3] = (qa[3] * ratioA + qb[3] * ratioB)
		qm[0] = (qa[0] * ratioA + qb[0] * ratioB)
		qm[1] = (qa[1] * ratioA + qb[1] * ratioB)
		qm[2] = (qa[2] * ratioA + qb[2] * ratioB)
		return qm

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
    self.layout.operator(PokeMastImport.bl_idname, text="Pokemon Masters (.lmd)")		
		
def register():
    bpy.utils.register_class(PokeMastImport)
    bpy.types.INFO_MT_file_import.append(menu_func_import)

def unregister():
    bpy.utils.unregister_class(PokeMastImport)
    bpy.types.INFO_MT_file_import.remove(menu_func_import)
	
if __name__ == "__main__":
    register()