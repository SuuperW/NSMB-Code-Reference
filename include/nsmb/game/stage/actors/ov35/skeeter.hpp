#pragma once

#include <nsmb/game/stage/entity3danm.hpp>

// vtable at 02143afc (ov35)
class Skeeter : public StageEntity {

public:

	using StateFunction = bool(Skeeter::*)();

	// C3: 02143094
	Skeeter();

	// D0: 02141ef0, D1: 02141e80
	virtual ~Skeeter();

	// 02142e30
	s32 onCreate() override;

	// 02142dd0
	s32 onDestroy() override;

	// 02142c74
	s32 onRender() override;

	// 02142db4
	void onCleanupResources() override;

	// 02142dd8
	bool onPrepareResources() override;

	// 02142c08
	bool updateMain() override;

	// 02141f6c
	bool skipRender() override;

	// 02141f68
	void onBlockHit() override;

	// 02142288
	void onEntityHit() override;

	// 02142304
	void onFireballHit() override;

	// 021421a4
	void onStarmanHit() override;

	// 021420cc
	void onMegaHit() override;

	// 02142188
	void onMegaKicked() override;

	// 021423ac
	void onStomped() override;

	// 02141fe8
	void onBlueShellHit() override;

	// 02142420
	void damagePlayer(ActiveCollider& self, Player& player) override;

	// 02142ff8
	bool switchState(StateFunction function);

	// 021424fc
	Player* getClosestPlayer(fx32* out_relativeX, fx32* out_relativeY);

	// 02142944
	bool doSkeetState();

	// 02142568
	bool dropBombState();

	static const StateFunction sDoSkeet;

	static const StateFunction sDropBomb;

	// 02143a08
	static fx32 offscreenLungeSpeeds[2]; // positive and negative

	// 02143a00
	static fx32 onscreenLungeSpeeds[2]; // positive and negative

	u32 unk3f4;
	u32 unk3f8;
	u32 unk3fc;
	u32 unk400;
	u32 unk404;
	u32 unk408;
	u32 unk40c;
	u32 unk410;
	u32 unk414;
	u32 unk418;
	u32 unk41c;
	u32 unk420;
	u32 unk424;
	u32 unk428;
	u32 unk42c;
	u32 unk430;
	u32 unk434;
	u32 unk438;
	u32 unk43c;
	u32 unk440;
	u32 unk444;
	u32 unk448;
	u32 unk44c;
	u32 unk450;
	u32 unk454;
	u32 unk458;
	u32 unk45c;
	u32 unk460;
	u32 unk464;
	u32 unk468;
	u32 unk46c;
	u32 unk470;
	u32 unk474;
	u32 unk478;
	u32 unk47c;
	u32 unk480;
	u32 unk484;
	u32 unk488;
	u32 unk48c;
	u32 unk490;
	u32 unk494;
	u32 unk498;
	StateFunction stateFunction;
	u32 unk4a4;
	u32 unk4a8;
	u32 unk4ac;
	u32 unk4b0;
	u32 unk4b4;
	u32 unk4b8;

#if NTR_EXT_EXISTS(Skeeter)
	#include NTR_EXT_INCLUDE(Skeeter)
#endif

};
#if !NTR_EXT_EXISTS(Skeeter)
NTR_SIZE_GUARD(Skeeter, 0x4bc);
#endif
