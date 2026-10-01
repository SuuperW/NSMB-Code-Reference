#pragma once

#include <nsmb/game/stage/entity3d.hpp>

// vtable at 0218a814 (ov110)
class ObstacleBubble : public StageEntity3D {

public:

	using StateFunction = bool(ObstacleBubble::*)();

	// D0: 02189a80
	// D1: 021899e0
	virtual ~ObstacleBubble();

	// 02189c58
	virtual s32 onCreate() override;

	// 02189b28
	virtual s32 onRender() override;

	// 02189da8
	virtual bool onPrepareResources() override;

	// 02189c38
	virtual bool updateMain() override;

	// 0218a3a4
	virtual void onBlockHit() override;

	// 0218a3a0
	virtual void onFireballHit() override;

	// 0218a39c
	virtual void onStarmanHit() override;

	// 0218a3ac
	virtual void onMegaHit() override;

	// 0218a3a8
	virtual void onStomped() override;

	// 0218a3fc
	virtual void damagePlayer(ActiveCollider& self, Player& player) override;

	static constexpr ObjectClassID ObjectID = ObjectClassID::ObstacleBubble;

	static constexpr u16 UpdatePriority = (u16)ObjectID;
	static constexpr u16 RenderPriority = 143;

	int unknown_4a0[14];

#if NTR_EXT_EXISTS(ObstacleBubble)
	#include NTR_EXT_INCLUDE(ObstacleBubble)
#endif

};
#if !NTR_EXT_EXISTS(ObstacleBubble)
NTR_SIZE_GUARD(ObstacleBubble, 0x4D8);
#endif
