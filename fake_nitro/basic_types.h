#pragma once

#ifdef __cplusplus
extern "C" {
#endif

// types we can infer based on the name and usage
typedef signed char s8;
typedef unsigned char u8;
typedef short s16;
typedef unsigned short u16;
typedef int s32;
typedef unsigned int u32;
typedef long long s64;
typedef unsigned long long u64;
typedef int BOOL;

typedef s16 fx16;
typedef s32 fx32;
typedef s64 fx64;
typedef s64 fx64c;
#define FX32_SHIFT 12

typedef struct VecFx32 {
	fx32 x, y, z;
} VecFx32;
typedef struct VecFx16 {
	fx16 x, y, z;
} VecFx16;

typedef struct MtxFx33 {
	VecFx32 a, b, c;
} MtxFx33;

typedef struct MtxFx43 {
	fx32 m[4][3];
} MtxFx43;

typedef struct MtxFx44 {
	fx32 m[4][4];
} MtxFx44;

typedef void* NNSFndHeapHandle;

// "use of undeclared identifier"
typedef int NNSG3dJntAnmResultFlag;

// This was determined to be wrong size, and determined to be integer type.
typedef s64 OSTick;

// These are used for fixed-size arrays that are initialized in NSMB-CR
#define SND_PITCH_TABLE_SIZE 768
#define SND_DECIBEL_TABLE_SIZE 128

// Types that need non-int attributes.
typedef struct NNSG3dRenderObj {
	union {
		int _fake_[21];
		void* ptrUser;
	};
} NNSG3dRenderObj;

typedef struct NNSG3dResMdl {
	union {
		int _fake_[2];
		struct {
			u32 numMat;
			u32 numNode;
		} info;
	};
} NNSG3dResMdl;

typedef struct NNSG3dAnmObj {
	union {
		int _fake_[1];
		struct {
			u32 numMapData;
			u32 mapData[];
		};
	};
} NNSG3dAnmObj;

typedef struct NNSG3dRS {
	union {
		int _fake_[1];
		u8 c[4];
	};
} NNSG3dRS;

// Auto-gen can't figure out this one.
typedef int SNDCommandID;

#ifdef __cplusplus
}
#endif
