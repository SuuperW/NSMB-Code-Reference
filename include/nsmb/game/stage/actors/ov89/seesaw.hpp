#pragma once

#include <nsmb/game/stage/entity3danm.hpp>

// vtable at 0217fbb4 (ov89)
class SeeSaw : public StageEntity {

public:

	using StateFunction = bool(SeeSaw::*)();

	// D0: 0217e17c
	// D1: 0217e0f0
	virtual ~SeeSaw();

	// 0217e2bc
	virtual s32 onCreate() override;

	// 0217e210
	virtual s32 onDestroy() override;

	// 0217e234
	virtual s32 onRender() override;

	// 0217e7f0
	virtual bool onPrepareResources() override;

	// 0217e274
	virtual bool updateMain() override;

	static constexpr ObjectClassID ObjectID = ObjectClassID::SeeSaw;

	static constexpr u16 UpdatePriority = (u16)ObjectID;
	static constexpr u16 RenderPriority = 210;

	int unknown_3f4[70];

#if NTR_EXT_EXISTS(SeeSaw)
	#include NTR_EXT_INCLUDE(SeeSaw)
#endif

};
#if !NTR_EXT_EXISTS(SeeSaw)
NTR_SIZE_GUARD(SeeSaw, 0x50C);
#endif
