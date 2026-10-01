#pragma once

#include <nsmb/game/stage/entity3danm.hpp>

// vtable at 0216E180 (ov11)
class HammerBro : public StageEntity3DAnm {

public:

	using StateFunction = bool(HammerBro::*)();

	// D0: 0215d2ac
	// D1: 0215d25c
	virtual ~HammerBro();

	// 0215d500
	virtual s32 onCreate() override;

	// 0215d6c4
	virtual bool onPrepareResources() override;

	// 0215d490
	virtual bool updateMain() override;

	// 0215df58
	virtual void onBlockHit() override;

	// 0215df88
	virtual void onEntityHit() override;

	// 0215dfd0
	virtual void onFireballHit() override;

	// 0215dfa0
	virtual void onStarmanHit() override;

	// 0215dfb8
	virtual void onSlidingHit() override;

	// 0215e0bc
	virtual void onMegaHit() override;

	// 0215e0d4
	virtual void onStomped() override;

	// 0215e0a4
	virtual void onGroundPound() override;

	// 0215df70
	virtual void onBlueShellHit() override;

	// 0215df10
	virtual void onMegaGroundPound() override;

	// 0215e1ec
	virtual void entityCollision(ActiveCollider& self, StageActor& actor) override;

	// 0215e0ec
	virtual void damagePlayer(ActiveCollider& self, Player& player) override;

	// 0215d44c
	virtual void preRender3D() override;

	// 0215d304
	virtual void postRender3D() override;

	static constexpr ObjectClassID ObjectID = ObjectClassID::HammerBro;

	static constexpr u16 UpdatePriority = (u16)ObjectID;
	static constexpr u16 RenderPriority = 81;

	int unknown_4bc[41];
	Vec3 unknown_560;
	int unknown_570[5];
	fx32 unknown_584;
	fx32 unknown_588;
	int unknown_58c;
	s16 unknown_590;
	s16 unknown_592;
	int unknown_594;
	s16 unknown_598;
	int unknown_59c[4];
	s16 unknown_5ac;
	s16 unknown_5ae;
	int unknown_5b0;
	s16 canGiveMega;
	s16 unknown_5b6;
	s16 unknown_5b8;
	s16 unknown_5ba;
	s8 unknown_5bc;
	s8 unknown_5bd;

#if NTR_EXT_EXISTS(HammerBro)
	#include NTR_EXT_INCLUDE(HammerBro)
#endif

};
#if !NTR_EXT_EXISTS(HammerBro)
NTR_SIZE_GUARD(HammerBro, 0x5C0);
#endif
