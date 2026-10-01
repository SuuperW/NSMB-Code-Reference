#pragma once

#include <nsmb/game/stage/entity3danm.hpp>
#include "unagi.hpp"

// vtable at 0217c2fc (ov79)
class MegaUnagi : public Unagi {

public:

	// D0: 0217c0a8
	// D1: 0217c088
	virtual ~MegaUnagi();

	static constexpr ObjectClassID ObjectID = ObjectClassID::MegaUnagi;

	static constexpr u16 UpdatePriority = (u16)ObjectID;
	static constexpr u16 RenderPriority = 88;

#if NTR_EXT_EXISTS(MegaUnagi)
	#include NTR_EXT_INCLUDE(MegaUnagi)
#endif

};
#if !NTR_EXT_EXISTS(MegaUnagi)
NTR_SIZE_GUARD(MegaUnagi, 0xE28);
#endif
