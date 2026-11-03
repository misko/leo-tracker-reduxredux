#pragma once
#include "location.h"

namespace leo::location::research {
// Private opt-in session: the owner must keep the snapshot arrays alive and
// unchanged until unbind/rebind or context destruction. Ordinary API calls do
// not opt in. Metadata changes fall back to checked scoring. Rebinding always
// invalidates state caches, even if an allocation address/generation is reused.
bool bind_immutable_orbit(leo_score_context*,const leo_orbit_snapshot*);
bool immutable_orbit_matches(const leo_score_context*,const leo_orbit_snapshot*);
}
