#pragma once
#include "timebase.hpp"
namespace leo::adaptive::timing {
// Lifetime is owned by the acquisition thread. Counter callback must return a
// current coherent hardware snapshot, not the most recently delivered block.
struct PosixClock {
    void* counter_context{};
    int (*counter_read)(void*, std::uint64_t*){};
    bool exact_counter{};
    ReadPort port();
};
}
