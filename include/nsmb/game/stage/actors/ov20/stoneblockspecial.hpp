#pragma once

#include <nsmb/game/stage/actors/ov10/stoneblock.hpp>
#include <nsmb/game/physics/rotatingplatform.hpp>

// vtable at 0x021330a4 (ov20)
class StoneBlockSpecial : public StoneBlock {

	// D0: 0212fa04
	// D1: 0212f900
	virtual ~StoneBlockSpecial();

	// 0212fec8
	virtual s32 onCreate() override;

	// 0212fc1c
	virtual s32 onDestroy() override;

	// 0212fc4c
	virtual s32 onRender() override;

	// 02131478
	virtual bool onPrepareResources() override;

	// 0212fd38
	virtual bool updateMain() override;

	// 0212fb58
	virtual bool skipRender() override;

	Collider collider;
	int unknown_528;
	int unknown_52c;
	int unknown_530;
	int unknown_534;
	ActiveCollider platformACs[3];
	RotatingPlatform rotatingPlatforms[2];
	Vec2 unknown_828;
	int unknown_834[6];
	Vec2 unknown_84c[3];
	Vec2 unknown_870[2];
	int unknown_888[13];

	static constexpr ObjectClassID ObjectID = ObjectClassID::StoneBlockSpecial;

	static constexpr u16 UpdatePriority = (u16)ObjectID;
	static constexpr u16 RenderPriority = 207;

#if NTR_EXT_EXISTS(StoneBlockSpecial)
	#include NTR_EXT_INCLUDE(StoneBlockSpecial)
#endif

};
#if !NTR_EXT_EXISTS(StoneBlockSpecial)
NTR_SIZE_GUARD(StoneBlockSpecial, 0x8BC);
#endif
