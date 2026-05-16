#pragma once

#include "basic_types.h"

#include <stdio.h>
#include <__stdarg_va_list.h>

#ifdef __cplusplus
extern "C" {
#endif

// probably easiest to manually add these, needless to say some stuff may not be exactly correct
int OS_VSNPrintf(char* dst, size_t len, const char* fmt, va_list vl);
constexpr fx64 FX64_CONST(int a) { return a; }
fx16 FX_SinIdx(int);
fx16 FX_CosIdx(int);
fx32 FX_Div(fx32 n, fx32 d);
fx64c FX_DivFx64c(fx32 n, fx32 d);
fx32 FX_Inv(fx32);
fx32 FX_Sqrt(fx32);
int FX_Whole(fx32);

void VEC_Add(const VecFx32* a, const VecFx32* b, VecFx32* out);
void VEC_Subtract(const VecFx32* a, const VecFx32* b, VecFx32* out);
fx32 VEC_Mag(const VecFx32*);
fx32 VEC_DotProduct(const VecFx32*, const VecFx32*);
void MTX_Concat43(const MtxFx43* a, const MtxFx43* b, MtxFx43* ab);

u32 MATH_CLAMP(u64, u32, u32);

struct fake_nitro_return_struct { void* ptrUser; };
struct fake_nitro_return_struct* NNS_G3dRSGetRenderObj(NNSG3dRS*);
NNSG3dMatAnmResult* NNS_G3dRSGetMatAnmResult(NNSG3dRS*);
NNSG3dJntAnmResult* NNS_G3dRSGetJntAnmResult(NNSG3dRS*);
NNSG3dVisAnmResult* NNS_G3dRSGetVisAnmResult(NNSG3dRS*);

void NNS_G3dRenderObjSetFlag(NNSG3dRenderObj*, int);
void NNS_G3dRenderObjResetFlag(NNSG3dRenderObj*, int);
void NNS_G3dRenderObjSetUserPtr(NNSG3dRenderObj*, void*);

void NNS_G3dAnmObjSetFrame(NNSG3dAnmObj*, int);
void NNS_G3dAnmObjSetFrame(NNSG3dAnmObj*, int);

u16 GX_RGB(int r, int g, int b);

u16 SND_CalcChannelVolume(int);
void SND_SetupChannelPcm(int chNo, SNDWaveFormat format, const void* dataAddr, SNDChannelLoop loop, int loopStart, int dataLen, int volume, SNDChannelDataShift shift, int timer, int pan);
void SND_StartTimer(u32 chBitMask, u32 capBitMask, u32 alarmBitMask, u32 flags);
void SND_StopTimer(u32 chBitMask, u32 capBitMask, u32 alarmBitMask, u32 flags);
void SND_SetupAlarm(int alarmNo, u32 tick, u32 period, SNDAlarmHandler handler, void* arg);
void SND_SetupCapture(SNDCapture capture, SNDCaptureFormat format, void* buffer_p, u32 length, BOOL loopFlag, SNDCaptureIn in, SNDCaptureOut out);

#ifdef __cplusplus
}
#endif
