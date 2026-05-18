#pragma once

#include <nsmb_nitro.hpp>


class Base;
class Object;
class Scene;
class Actor;


enum class BaseReturnState : u32 {
	PreFailed = 0,
	Failed,
	Success,
	Minus1	//WHEN??? -> StageScene::onCreate
};

enum class ObjectState : u8 {
	NotCreated = 0,
	Active,
	Dead
};

enum class ObjectType : u8 {
	Other = 0,//Effects???
	Scene,
	Actor
};

enum class ProfileStep : u8 {
	None = 0,
	LoadOverlay,
	SetParams,
	Construct,
	Create
};

enum class ObjectClassID : u16 {
	BootScene = 0,
	VSConnectScene = 6,
	WorldmapScene = 9,
	CorruptedSaveScene = 11,
	EndingScene = 12,
	StageFX = 18,
	Player = 21,
	Actor22 = 22,
	PipePiranhaUp = 23,
	PipePiranhaDown = 24,
	PipePiranhaRight = 25,
	PipePiranhaLeft = 26,
	BulletBill = 27,
	Item = 31,
	BobOmb = 35,
	Thwomp = 37,
	GiantThwomp = 38,
	Lakitu = 39,
	Boo = 41,
	BalloonBoo = 42,
	ChainChompLog = 44,
	ChainChomp = 45,
	Zoom = 49,
	DryBones = 55,
	BigDryBones = 56,
	LakituSpawner = 59,
	PipeEnemySpawner = 64,
	FireBar = 65,
	Coin = 66,
	DonutLift = 71,
	Whomp = 73,
	Goomba = 83,
	Paragoomba = 84,
	MiniGoomba = 85,
	WarpEntrance = 87,
	Snailicorn = 91,
	CoinSpawner = 92,
	KoopaTroopa = 94,
	KoopaParatroopa = 95,
	FenceKoopa = 96,
	Pokey = 98,
	SpikedBall = 103,
	SpikedBallTrigger = 104,
	Amp = 110,
	BossController = 114,
	Peach = 115,
	Broozer = 120,
	VolcanoEruption = 121,
	Splunkin = 127,
	Toadsworth = 134,
	SpikeBass = 150,
	RedCoinRing = 151,
	PhantomHand = 152,
	SnowSpike = 155,
	Snowball = 156,
	SpikeBassSpawner = 157,
	VerticalCheckpoint = 158,
	Checkpoint = 159,
	TiltMetalDish = 169,
	WobbleRock = 170,
	BigSpikedBall = 185,
	Manhole = 187,
	TileGod = 206,
	SkewerDown = 216,
	SkewerUp = 217,
	SkewerLeft = 218,
	SkewerRight = 219,
	DistancedSkewerDown = 220,
	DistancedSkewerUp = 221,
	DistancedSkewerLeft = 222,
	DistancedSkewerRight = 223,
	SwellingGround = 231,
	Trampoline = 237,
	BanzaiBill = 238,
	MegaGoomba = 239,
	BulletBillBlaster = 248,
	BanzaiBillBlaster = 249,
	SpinBlock = 254,
	SpinBlock255 = 255,
	SpinBlock256 = 256,
	EndingController = 314,
	StageCamera = 316,
	WorldCamera = 318,
	WorldmapActor = 319,
	WorldMapCamera = 322,
	TitleScreenCamera = 323,
	EndingCamera = 324,
};

typedef s32(Base::* BaseProcessFunction)();
typedef bool(Base::* BasePreFunction)();
typedef s32(Base::* BaseOnFunction)();
typedef void(Base::* BasePostFunction)(BaseReturnState);

typedef u32(*OverlayLoadFunction)(u16);
typedef void (*OverlayUnloadFunction)(u16);
