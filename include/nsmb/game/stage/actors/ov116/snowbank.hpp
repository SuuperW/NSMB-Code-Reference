#pragma once

#include <nsmb/game/stage/entity3danm.hpp>
#include <nsmb/game/physics/segmentplatform.hpp>

// vtable at 0218EFD4 (ov116)
class SnowBank : public StageEntity {

public:

	using StateFunction = bool(SnowBank::*)();

	// D0: 0218cc6c
	// D1: 0218cb8c
	virtual ~SnowBank();

	// 0218cd54
	virtual s32 onRender() override;

	// 0218d650
	virtual bool onPrepareResources() override;

	// 0218cdf0
	virtual bool updateMain() override;

	static constexpr ObjectClassID ObjectID = ObjectClassID::SnowBank;

	static constexpr u16 UpdatePriority = (u16)ObjectID;
	static constexpr u16 RenderPriority = 247;

	int unknown_3f4[8];
	SegmentPlatform segments[33];
	Vec2 unknown_points_1284[34];
	Vec2 unknown_points_141c[34];
	Vec2 unknown_points_15b4[129];
	int unknown_141c[74];

#if NTR_EXT_EXISTS(SnowBank)
	#include NTR_EXT_INCLUDE(SnowBank)
#endif

};
#if !NTR_EXT_EXISTS(SnowBank)
NTR_SIZE_GUARD(SnowBank, 0x1CE8);
#endif
