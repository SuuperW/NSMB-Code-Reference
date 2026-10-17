#pragma once

#include <nsmb/game/stage/entity.hpp>
#include <nsmb/game/physics/collider.hpp>

// vtable at 021245bc (ov10)
class BrokenBrick : public StageEntity {
public:

	using StateFunction = bool(BrokenBrick::*)(int);

	// D1: 020d5240
	// D0: 020d52c8
	virtual ~BrokenBrick() override;

	// 020d5400
	s32 onCreate() override;

	// 020d5358
	s32 onDestroy() override;

	// 020d5398
	s32 onUpdate() override;

	// 020d5390
	s32 onRender() override;

	// 020d538c
	void onCleanupResources() override;

	// 020d56dc
	void onBlockHit() override;

	// 020d5750
	bool switchState(StateFunction function, int stateSlot);

	// 020d561c
	bool defaultState(int unknown);

	static constexpr ObjectClassID ObjectID = ObjectClassID::BrokenBrick;

	static constexpr u16 UpdatePriority = (u16)ObjectID;
	static constexpr u16 RenderPriority = 277;

	// 021245a8
	static const ActorProfile profile;

	Vec2 unknown_3f4;
	int unknown_400;
	u8 unknown_404;
	u8 unknown_405;
	u8 unknown_406;
	u8 unknown_407;
	u8 unknown_408;
	u8 unknown_409;
	u8 unknown_40a;
	u8 unknown_40b[2];
	u8 unknown_40d;
	u8 unknown_40e;
	u8 unknown_40f;
	u8 unknown_410;
	u8 unknown_411;
	u8 unknown_412;
	u8 unknown_413;
	int unknown_414;
	u8 unknown_418;
	Collider collider;
	s32 unknown_488;
	s32 unknown_48c;
	s32 unknown_490;
	s32 unknown_494;
	u8 unknown_498[8];
	s32 unknown_4a0;
	Vec3 unknown_4a4;
	StateFunction updateFunctions[5];
	s16 lifeTimer;
	s16 unknown_4de;
	s16 unknown_4e0;
	u16 stateID;
	s16 unknown_4e4;
	u8 unknown_4e6[5];
	u8 unknown_4eb;

#if NTR_EXT_EXISTS(BrokenBrick)
	#include NTR_EXT_INCLUDE(BrokenBrick)
#endif

};
#if !NTR_EXT_EXISTS(BrokenBrick)
NTR_SIZE_GUARD(BrokenBrick, 0x4EC);
#endif
