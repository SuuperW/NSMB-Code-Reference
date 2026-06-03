#include "nsmb.hpp"

// ----- Template hacks for libclang -----
// Template instantiations that are not direct subclasses of a non-template will not be properly parsed.
struct template_hack_1 : public Rectangle<fx32> {};
