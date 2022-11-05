from bpy_extras.io_utils import ImportHelper
from bpy.props import (BoolProperty,
                       FloatProperty,
                       StringProperty,
                       EnumProperty,
                       CollectionProperty
                       )
import numpy as np
import mathutils
import math
import struct
import io
import os
import bmesh
import re
import bpy
bl_info = {
    "name": "Import Pokemon Masters Animation",
    "author": "Romulion for initial code, SleepyZay for Pokemon anim support, Plastered_Crab for bulk importing and QOL improvements",
    "version": (0, 10, 3),
    "blender": (2, 80, 0),
    "location": "File > Import-Export",
    "description": "A tool designed to import LMD animation from the mobile game Pokemon Masters.",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Import-Export"}


if bpy.app.version < (2, 80, 0):
    bl_info['blender'] = (2, 79, 0)


from bpy.types import (
                Operator,
                OperatorFileListElement,
                )




class PokeMastAnimImport(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.pokemonmastersanim"
    bl_label = "Import anim"
    bl_options = {'PRESET', 'UNDO'}

    files: CollectionProperty(
            name="File Path",
            type=OperatorFileListElement,
            )
    directory: StringProperty(
            subtype='DIR_PATH',
            )

    #updated the filter_glob to properly filter all non .lmd files out. 3.0+ Blender requires : instead of = now
    filename_ext = ".wismda"
    filter_glob: StringProperty(
        default="*.lmd",
        maxlen=255,
        options={'HIDDEN'},
    )

    filepath = StringProperty(subtype='FILE_PATH',)
    fps = 60

    def draw(self, context):
        layout = self.layout

    def execute(self, context):
        # skip if no armature binded
        if not bpy.context.active_object or bpy.context.active_object.type != 'ARMATURE':
            return {'CANCELLED'}

        #adds in the ability to select multiple .lmd files at once (pressing the A key to select all works so much faster than doing them all one by one)
        for file_elem in self.files:
            #ignores the uv and cam animations that cause errors and crash the script
            if re.search ('_uv', file_elem.name):
                print("Skipping detected uv file")
            elif re.search ('_cam', file_elem.name):
                print("Skipping detected cam file")
            elif re.search ('.animseq', file_elem.name):
                print("Skipping detected animseq file")
            else:
                filepath = os.path.join(self.directory, file_elem.name)
                CurFile = open(filepath, "rb")

                # chose anim type 20 - trainer, 8 - pokemon
                anim_type = int.from_bytes(CurFile.read(4), byteorder='little')

                if anim_type == 20:
                    CurFile.seek(100)
                else:
                    CurFile.seek(72)
                AnimationLength = struct.unpack('f', CurFile.read(4))[0]
                self.report({'INFO'}, str(AnimationLength))
                AnimationRaw = self.ReadAnimation(CurFile, anim_type)
                self.maxFrames = round(AnimationLength * self.fps)
                self.ApplyAnimation(AnimationRaw, self.fps, file_elem.name)
                CurFile.close()
		
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def ApplyAnimation(self, AnimationRaw, fps, filename):
        armature = bpy.context.active_object
        armature.animation_data_clear()
        scn = bpy.context.scene

        scn.frame_set(0)
        scn.frame_start = 0
        scn.frame_end = self.maxFrames
        bpy.context.scene.render.fps = fps

        mat_identity = mathutils.Matrix.Identity(4)

        for boneName in AnimationRaw.keys():
            # skip non existent bones
            if boneName not in armature.pose.bones:
                continue

            boneRotData = []
            boneTransData = []
            animationData = AnimationRaw[boneName]

            bonePos = armature.pose.bones[boneName]
            bone = armature.data.bones[boneName]
            if animationData['rotation']['type'] == 1:
                bonePos.rotation_mode = "QUATERNION"
            else:
                #bonePos.rotation_mode = "ZXY"
                bonePos.rotation_mode = "QUATERNION"

            # convert to parent - child matrix
            if bone.parent:
                parentChildMatrix = mat_mult(
                    bone.parent.matrix_local.inverted(), bone.matrix_local)
            else:
                parentChildMatrix = bone.matrix_local

            # check if matrix invertable
            if parentChildMatrix != mat_identity:
                parentChildMatrix.invert()
            # get parent 2 bone transform for animation conversion
            #startLoc = parentChildMatrix.translation
            startRot = parentChildMatrix.to_quaternion()
            startEuler = parentChildMatrix.to_euler()

            animationData = self.PrecessAnimation(animationData, boneName)
            animationRotaion = animationData['rotation']
            animationTranslate = animationData['translation']
            animationScale = animationData['scale']

            # if boneName == 'Feeler':
            #   print(startEuler)
            # adding rotation frames
            for i in range(len(animationRotaion['time'])):
                bonePos.rotation_quaternion = mat_mult(
                    startRot, animationRotaion['frames'][i])
                bonePos.keyframe_insert(
                    data_path="rotation_quaternion", frame=animationRotaion['time'][i])

            # adding translation frames
            for n in range(len(animationTranslate['time'])):
                bonePos.location = mat_mult(
                    parentChildMatrix,  animationTranslate['frames'][n])
                bonePos.keyframe_insert(
                    data_path="location", frame=animationTranslate['time'][n])

            for m in range(len(animationScale['time'])):
                bonePos.scale = animationScale['frames'][m]
                bonePos.keyframe_insert(
                    data_path="scale", frame=animationScale['time'][m])

        #extra stuff to name Actions properly based on the file name and character name/alt
        print(filename)
        indexNum = self.find_nth(filename, '_', 1)
        indexName = self.find_nth(filename, '_', 2)
        indexNameEnd = self.find_nth(filename, '_', 3)
        indexUnder = self.find_nth(filename, '_', 4)

        numCode = filename[indexNum + 1 : indexName :]

        charName = filename[indexName + 1 : indexNameEnd :]

        filename = filename[indexUnder + 1 : len(filename)-4 :]
        if len(filename) == 2:
            #adds extra context to filename of mouth animations
            filename = 'mouth_' + filename

        #adds nice naming convention of: [trainerName + trainerAlt] animationTitle
        filename = '[' + charName + '_' + numCode + '] ' + filename
        armature.animation_data.action.name = filename

        #forces all action animations to have fake users so that Beldner doesn't delete the unused ones upon exiting the software
        armature.animation_data.action.use_fake_user = True

    def find_nth(self, haystack, needle, n):
        start = haystack.find(needle)
        while start >= 0 and n > 1:
            start = haystack.find(needle, start+len(needle))
            n -= 1
        return start

    def PrecessAnimation(self, animationData, name):

        # Get frame number from timeline
        animationRotaion = animationData['rotation']
        animationTranslate = animationData['translation']
        animationScale = animationData['scale']
        for i in range(len(animationTranslate['time'])):
            animationTranslate['time'][i] = round(
                animationTranslate['time'][i] * self.maxFrames)

        for i in range(len(animationRotaion['time'])):
            animationRotaion['time'][i] = round(
                animationRotaion['time'][i] * self.maxFrames)

        for i in range(len(animationScale['time'])):
            animationScale['time'][i] = round(
                animationScale['time'][i] * self.maxFrames)

        # fix wrong quaternion interpolation
        i = 0
        prev_frame = {
            "frames":  animationRotaion['frames'][0], "time": animationRotaion['time'][0]}
        for n in range(len(animationRotaion['frames'])):
            frames_passed = animationRotaion['time'][i] - \
                prev_frame['time']
            if frames_passed > 1:

                end_frame = animationRotaion['frames'][i]
                # add between frames
                for m in range(1, frames_passed):
                    animationRotaion["frames"].insert(
                        i,  prev_frame["frames"].slerp(end_frame, m / frames_passed))
                    animationRotaion["time"].insert(
                        i,  prev_frame['time'] + m)
                    i = i + 1

            prev_frame = {
                "frames":  animationRotaion['frames'][i], "time": animationRotaion['time'][i]}
            i = i + 1

        return {'rotation': animationRotaion, 'translation': animationTranslate, 'scale': animationScale}

    def ReadString(self, CurFile, Start):
        CurFile.seek(Start)
        StringLength = int.from_bytes(CurFile.read(4), byteorder='little')
        return CurFile.read(StringLength).decode('utf-8')

    def ReadAnimation(self, CurFile, anim_type):
        self.maxFrames = 1

        if anim_type == 8:
            offset = 92
        else:
            offset = 116

        CurFile.seek(offset)
        bonesCount = int.from_bytes(CurFile.read(4), byteorder='little')

        startPosition = CurFile.tell()
        bonePointers = []
        for i in range(bonesCount):
            bonePointers.append(
                CurFile.tell() + int.from_bytes(CurFile.read(4), byteorder='little'))

        animationData = {}
        for boneAddr in bonePointers:
            CurFile.seek(boneAddr+4)
            BoneNamePointer = read_pointer(CurFile, boneAddr+4)
            BoneName = self.ReadString(CurFile, BoneNamePointer)

            # get rotation type 1 - Quaternion, character; 4 - XYZ, pokemon
            CurFile.seek(boneAddr+12)
            anim_type = int.from_bytes(CurFile.read(4), byteorder='little')
            # skip non bone animation
            CurFile.seek(boneAddr+16)
            if int.from_bytes(CurFile.read(4), byteorder='little') != 7:
                continue

            # Read animation components pointers
            CurFile.seek(boneAddr + 20)
            AnimComponentPointer = RotationPointer = read_pointer(
                CurFile, boneAddr + 20)

            ScalePointer = read_pointer(CurFile, AnimComponentPointer + 8)
            RotationPointer = read_pointer(CurFile, AnimComponentPointer + 12)
            TranslatePointer = read_pointer(CurFile, AnimComponentPointer + 16)

            # Scale data
            ScaleTimeTablePointer = read_pointer(
                CurFile, ScalePointer + 4)
            ScaleTimeTable = read_time_table(
                CurFile, ScaleTimeTablePointer)

            # Frames
            ScaleFramesPointer = read_pointer(
                CurFile, ScalePointer + 8)
            ScaleTable = read_vec3_table(CurFile, ScaleFramesPointer)

            # Translate data
            # Time
            TranslateTimeTablePointer = read_pointer(
                CurFile, TranslatePointer + 4)
            TranslateTimeTable = read_time_table(
                CurFile, TranslateTimeTablePointer)

            # Frames
            TranslateFramesPointer = read_pointer(
                CurFile, TranslatePointer + 8)
            TranslateTable = read_vec3_table(CurFile, TranslateFramesPointer)

            # Rotation data
            # Time
            RotationTimeTablePointer = read_pointer(
                CurFile, RotationPointer + 4)
            RotationTimeTable = read_time_table(
                CurFile, RotationTimeTablePointer)

            # Frames
            RotationFramesPointer = read_pointer(
                CurFile, RotationPointer + 8)
            RotationTable = []
            CurFile.seek(RotationFramesPointer)
            framesCount = int.from_bytes(CurFile.read(4), byteorder='little')

            if anim_type == 1:
                for t in range(int(framesCount/4)):
                    temtQuat = mathutils.Quaternion(
                        struct.unpack('ffff', CurFile.read(4*4)))
                    w = temtQuat.z
                    temtQuat.z = temtQuat.y
                    temtQuat.y = temtQuat.x
                    temtQuat.x = temtQuat.w
                    temtQuat.w = w
                    RotationTable.append(temtQuat)
            else:
                for t in range(int(framesCount/3)):
                    tempEuler = mathutils.Euler(
                        struct.unpack('fff', CurFile.read(4*3)))
                    RotationTable.append(tempEuler.to_quaternion())

            animationData[BoneName] = {
                'rotation': {'time': RotationTimeTable, 'frames': RotationTable, 'type': anim_type},
                'translation': {'time': TranslateTimeTable, 'frames': TranslateTable},
                'scale': {'time': ScaleTimeTable, 'frames': ScaleTable}
            }

        return animationData


def read_vec3_table(stream, offset):
    TransformTable = []
    stream.seek(offset)
    framesCount = int.from_bytes(stream.read(4), byteorder='little')
    for t in range(int(framesCount/3)):
        TransformTable.append(mathutils.Vector(
            struct.unpack('fff', stream.read(4*3))))

    return TransformTable


def read_time_table(stream, offset):
    TimeTable = []
    stream.seek(offset)
    timeCount = int.from_bytes(stream.read(4), byteorder='little')
    for t in range(timeCount):
        TimeTable.append(struct.unpack('f', stream.read(4))[0])
    return TimeTable


def read_pointer(stream, offset):
    stream.seek(offset)
    return stream.tell() + int.from_bytes(stream.read(4), byteorder='little')


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
    self.layout.operator(PokeMastAnimImport.bl_idname,
                         text="Pokemon Masters Animations(.lmd)")


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
