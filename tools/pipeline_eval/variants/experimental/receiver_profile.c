#include "receiver_profile.h"
#include <string.h>

_Thread_local ProfileStat receiver_stats[PROFILE_COUNT];

void experimental_receiver_profile_reset(void) {
    memset(receiver_stats, 0, sizeof receiver_stats);
}

unsigned experimental_receiver_profile_read(ProfileStat *out, unsigned capacity) {
    if (capacity >= PROFILE_COUNT)
        memcpy(out, receiver_stats, sizeof receiver_stats);
    return PROFILE_COUNT;
}
