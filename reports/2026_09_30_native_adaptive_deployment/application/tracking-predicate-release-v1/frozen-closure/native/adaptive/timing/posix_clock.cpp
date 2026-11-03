#include "posix_clock.hpp"
#include <ctime>
#include <cerrno>
#include <limits>
namespace leo::adaptive::timing {
namespace {
int read_clock(clockid_t clock, std::uint64_t* out) {
    timespec t{};
    if(clock_gettime(clock,&t)) return -errno;
    if(t.tv_sec<0 || static_cast<std::uint64_t>(t.tv_sec)>
       (static_cast<std::uint64_t>(INT64_MAX)-999999999)/1000000000)
        return -ERANGE;
    *out=static_cast<std::uint64_t>(t.tv_sec)*1000000000+t.tv_nsec;
    return 0;
}
int mono(void*,std::uint64_t* out) { return read_clock(CLOCK_MONOTONIC,out); }
int utc(void*,std::int64_t* out) {
    std::uint64_t n{}; const int rc=read_clock(CLOCK_REALTIME,&n);
    if(!rc) *out=static_cast<std::int64_t>(n);
    return rc;
}
int counter(void* context,std::uint64_t* out) {
    auto& p=*static_cast<PosixClock*>(context);
    return p.counter_read ? p.counter_read(p.counter_context,out) : -EINVAL;
}
}
ReadPort PosixClock::port() { return {this,mono,utc,counter,exact_counter}; }
}
