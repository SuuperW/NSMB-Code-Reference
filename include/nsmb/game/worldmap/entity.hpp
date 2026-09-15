#pragma once

#include <nsmb/core/graphics/3d/modelanm.hpp>
#include <nsmb/core/graphics/3d/animationctrl.hpp>

// overlay 8
// vtable at 020e9958
class WorldmapEntityModel
{
public:

	enum class Type : u32 {
		HammerBro = 0,
		FlyingBlock
	};


	ModelAnm entityModel;				//Model of the given entity
	AnimationCtrl patternAnimation;		//Pattern animation for FlyingBlock
	Model linkModel;					//Model for Hammer/Map Shadow
	AnimationCtrl shadowAnimation;		//Shadow animation for FlyingBlock
	Type type;							//Type of the entity


	//020ee7e0
	static u32 shadowAnimations[2];

	//020ee7e8
	static u32 entityAnimations[2][2];//Type & ID

	//020ee7dc
	static u16 texPaletteBase;

	//020e2e54
	static u16 texPaletteOffset[2];

	//020e9940
	static u32 resourceFileIDs[2][2];//Type & Model/Animation


	//020dc1bc
	WorldmapEntityModel();

	//D0:020dc13c
	//D1:020dc180
	virtual ~WorldmapEntityModel();

	//020dbfe0
	bool create(Type type);

	//020dbdf8
	void render(MtxFx43* modelMatrix, Vec3* scale, Vec3* relPos);//relPos only used by Flying Block (and even there only Y)

	//020dbdd0
	void update();

	//020dbd60
	void setAnimation(u32 animID);

	//020dbc88
	static bool loadFiles();

};
NTR_SIZE_GUARD(WorldmapEntityModel, 0x198);
