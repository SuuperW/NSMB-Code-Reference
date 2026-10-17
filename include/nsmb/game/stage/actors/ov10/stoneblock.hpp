#pragma once

#include <nsmb/game/stage/entity.hpp>
#include <nsmb/game/physics/collider.hpp>
#include <nsmb/core/graphics/3d/texture.hpp>

// stone blocks look very weird to me
// One of them has 3 vtables.
// Two of them seem identical. (Could it be that they are different purely to have different priorities?)
// One is much larger than the rest. And is in overlay 20.

// vtable at 0x2125b80 (ov10)
class StoneBlock : public StageEntity {
public:

	// D0: 020dc660
	// D1: 020dc6e0
	virtual ~StoneBlock();

	// 020dc774
	virtual s32 onCreate() override;

	// 020dc7b4
	virtual bool onPrepareResources() override;

	Texture textures[5];
	// The size of this base is uncertain.
	int unknown_41c[40];

};
NTR_SIZE_GUARD(StoneBlock, 0x4BC);

// vtable at 0x2125c9c (ov10)
class StoneBlockUpDownBase : public StoneBlock {

	// D0: 020dc7dc
	// D1: 020dc878
	virtual ~StoneBlockUpDownBase();

	// 020dc99c
	virtual s32 onCreate() override;

	// 020dc90c
	virtual s32 onDestroy() override;

	// 020dc930
	virtual s32 onRender() override;

	// 020dc970
	virtual bool updateMain() override;

	Collider collider;
	int unknown_528[11];
};
NTR_SIZE_GUARD(StoneBlockUpDownBase, 0x554);
// vtable at 0x2125dec (ov10)
class StoneBlockUpDown : public StoneBlockUpDownBase {

	// D0: 020dccf8
	// D1: 020dcc58
	virtual ~StoneBlockUpDown();

	// 020dcdc0
	virtual s32 onCreate() override;

	// 020dcda0
	virtual bool updateMain() override;


	static constexpr ObjectClassID ObjectID = ObjectClassID::StoneBlockUpDown;

	static constexpr u16 UpdatePriority = (u16)ObjectID;
	static constexpr u16 RenderPriority = 204;

};
NTR_SIZE_GUARD(StoneBlockUpDown, sizeof(StoneBlockUpDownBase));

// vtable at 0x2125f48 (ov10)
class StoneBlockLeftRight : public StoneBlock {

	// D0: 020dd328
	// D1: 020dd294
protected:
	virtual ~StoneBlockLeftRight();

public:
	// 020dd5e8
	virtual s32 onCreate() override;

	// 020dd474
	virtual s32 onDestroy() override;

	// 020dd498
	virtual s32 onRender() override;

	// 020dd4d8
	virtual bool updateMain() override;

	// 020dd3c4
	virtual bool skipRender() override;

	int unknown_4bc[4];
	Collider collider;
	int unknown_538[4];
	fx32 width;
	fx32 positionOffset;
	fx32 endpoints[2]; // start, end
	int unknown_558[2];
	fx16 maximumSpeed;
	short unknown_562;
	int unknown_564;

};
NTR_SIZE_GUARD(StoneBlockLeftRight, 0x568);

class StoneBlockLeftRight1 : public StoneBlockLeftRight {

	static constexpr ObjectClassID ObjectID = ObjectClassID::StoneBlockLeftRight1;

	static constexpr u16 UpdatePriority = (u16)ObjectID;
	static constexpr u16 RenderPriority = 205;

};
NTR_SIZE_GUARD(StoneBlockLeftRight1, sizeof(StoneBlockLeftRight));

class StoneBlockLeftRight2 : public StoneBlockLeftRight {

	static constexpr ObjectClassID ObjectID = ObjectClassID::StoneBlockLeftRight2;

	static constexpr u16 UpdatePriority = (u16)ObjectID;
	static constexpr u16 RenderPriority = 206;

};
NTR_SIZE_GUARD(StoneBlockLeftRight2, sizeof(StoneBlockLeftRight));
