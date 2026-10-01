#pragma once

#include <nsmb/game/stage/entity3danm.hpp>

// vtable at 0217c1e0 (ov79)
class Unagi : public StageEntity3DAnm {

public:

	using StateFunction = bool(Unagi::*)();

	// D0: 0217bbdc
	// D1: 0217bcf8
	virtual ~Unagi();

	// 02179ddc
	virtual s32 onCreate() override;

	// 02179a54
	virtual s32 onDestroy() override;

	// 02179b20
	virtual void onCleanupResources() override;

	// 0217a78c
	virtual bool onPrepareResources() override;

	// 02179ca8
	virtual bool updateMain() override;

	// 021799c0
	virtual bool skipRender() override;

	// 0217a844
	virtual bool updateDefeated() override;

	// 0217b74c
	virtual void onBlockHit() override;

	// 0217b750
	virtual void onFireballHit() override;

	// 0217b728
	virtual void onStarmanHit() override;

	// 0217b754
	virtual void onMegaHit() override;

	// 0217b704
	virtual void onBlueShellHit() override;

	// 0217b7e0
	virtual void damagePlayer(ActiveCollider& self, Player& player) override;

	// 02179c78
	virtual void preRender3D() override;

	// 02179b24
	virtual void postRender3D() override;

	static constexpr ObjectClassID ObjectID = ObjectClassID::Unagi;

	static constexpr u16 UpdatePriority = (u16)ObjectID;
	static constexpr u16 RenderPriority = 87;

	int unknown_4bc[603];

#if NTR_EXT_EXISTS(Unagi)
	#include NTR_EXT_INCLUDE(Unagi)
#endif

};
#if !NTR_EXT_EXISTS(Unagi)
NTR_SIZE_GUARD(Unagi, 0xE28);
#endif
