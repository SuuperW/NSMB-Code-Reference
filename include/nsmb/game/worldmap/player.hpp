#pragma once

#include <nsmb/game/player.hpp>

// overlay 8
//vtable 020e9b70
class WorldmapPlayerModel
{
public:

	struct ModelConfig {
		s8 sizeIndex;
		s8 texPalette;
	};

	struct WMAnimation {
		u32 animFileID;
		u32 animIndex;			//NSBCA animation index
		fx32 speed;
		FrameCtrl::Type type;
		u32 unknown;
		u32 headAnimID;
	};

	enum class WMPowerupState : s8 {
		Small = 0,
		Super,
		Fire,
		Unused0,	//Identical to Small
		Shell,
		Unused1		//Identical to Super
	};

	enum class AnimationType : u32 {
		Idle = 0,
		Walk,
		Run,
		Pipe,
		CourseEnter,
		CoinCompleted
	};

	PlayerModel model;				//Player model
	ModelConfig* config;			//Configuration for the model depending on powerup state
	AnimationType animID;			//Current main animation ID
	u32 headAnimID;					//Current head animation ID
	u8 playerID;					//Player ID
	s8 sizeState;					//Size: 0=standard,1=small
	WMPowerupState powerupState;	//Current powerup state


	//020e4010
	static WMAnimation animations[6];

	//020e3ffc
	static u32 idleAnimationIDs[2];		//Not applicable to size state 1

	//020e3ff4
	static u32 walkAnimationIDs[2];

	//020e3fec
	static u32 runAnimationIDs[2];

	//020e4004
	static ModelConfig modelConfigs[6];


	//020ddd50
	WorldmapPlayerModel();

	//D0:020ddd00
	//D1:020ddd2c
	virtual ~WorldmapPlayerModel();

	//020ddc28
	bool create(u8 playerID, s8 playerPowerup, u32 animID);

	//020ddbb4
	void render(MtxFx43* modelMatrix, Vec3* scale);

	//020ddb90
	void update(bool skip);

	//020dda80
	void setAnimation(AnimationType animID, bool continueAnimation);

	//020dd9f8
	void setHeadAnimation(u32 headAnimID);

	//020dd21c
	static bool loadFiles();

};
NTR_SIZE_GUARD(WorldmapPlayerModel, 0x3D8);
