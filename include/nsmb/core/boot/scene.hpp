#pragma once

#include <nsmb/core/entity/scene.hpp>

//ov1
// vtable at 0x020cd0f0
class BootScene : public Scene
{
public:

	//C3:020cce88
	BootScene();

	//D0:020cc300
	//D1:020cc2e0
	virtual ~BootScene();

	//020ccb30
	virtual s32 onCreate() override;

	//020ccb28
	virtual s32 onDestroy() override;

	//020ccb24
	virtual void onCleanupResources() override;

	//020ccb1c
	virtual s32 onRender() override;

	//020cc580
	virtual s32 onUpdate() override;

	//020cc4b4
	//void ? ? ? ();

	//020cc328
	//void ? ? ? ();

	/*
	Case 0 == 7
	Case 1 -> 2/6
	Case 2 -> 3
	Case 3 -> 4/6
	Case 4 -> 5
	Case 5 -> 7
	Case 6 -> 0
	Case 7 -> F
	Case 8 -> 9/F
	Case 9 -> S
	*/

	static constexpr ObjectClassID ObjectID = ObjectClassID::BootScene;

	static constexpr u16 UpdatePriority = (u16)ObjectID;
	static constexpr u16 RenderPriority = 7;

	//020cd144
	static u8 nintendoLogoNCG[0x5F0];

	//020cd734
	static u8 nintendoLogoNCL[0x200];

	//020cd934
	static u8 nintendoLogoNSC[0x1F0];

	//020cdb24
	static u8 copyrightTextNCG[0xD28];

	//020ce84c
	static u8 copyrightTextNCL[0x20];

	//020ce86c
	static u8 copyrightTextNSC[0x2B8];

	//Save related
	u32 unk64;
	u32 unk68;
	u32 unk6c;
	u32 unk70;

	u32 unk74;//???

	u16 unk78;//Timer: 0x78 or 0 if this is not the starting scene
	u8 unk7a;//State 0-9
	u8 unk7b;
	u8 unk7c;
	u8 unk7d;
	u8 unk7e;

};
NTR_SIZE_GUARD(BootScene, 0x80);
