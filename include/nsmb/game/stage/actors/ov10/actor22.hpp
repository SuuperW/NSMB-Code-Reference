#pragma once

#include <nsmb/game/stage/entity.hpp>

// vtable at 02126BEC (ov10)
class Actor22 : public StageEntity
{
public:

	// D0: 020E93C4
	// D1: 020E9368
	virtual ~Actor22();

	static constexpr ObjectClassID ObjectID = ObjectClassID::Actor22;

	static constexpr u16 UpdatePriority = (u16)ObjectID;
	static constexpr u16 RenderPriority = 29;

	// 02126BE0
	static const ActorProfile profile;


#if NTR_EXT_EXISTS(Actor22)
	#include NTR_EXT_INCLUDE(Actor22)
#endif

};
#if !NTR_EXT_EXISTS(Actor22)
NTR_SIZE_GUARD(Actor22, sizeof(StageEntity));
#endif
