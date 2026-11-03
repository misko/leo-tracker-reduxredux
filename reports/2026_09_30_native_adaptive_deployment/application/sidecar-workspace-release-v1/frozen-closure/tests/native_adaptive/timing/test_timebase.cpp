#include "timebase.hpp"
#include "posix_clock.hpp"
#include <cassert>
#include <cmath>
#include <limits>
#include <stdexcept>
using namespace leo::adaptive::timing;
namespace {
constexpr std::uint64_t base = (UINT64_C(1) << 54) + 37;
constexpr std::int64_t utc = INT64_C(1790740000000000000);
Config config() { return {2500000, 1000000, 10000000000ULL, 10, 100, 2}; }
Bracket bracket(std::uint64_t sample, std::int64_t elapsed) {
    return {UINT64_C(100000000000) + static_cast<std::uint64_t>(elapsed),
        UINT64_C(100000000200) + static_cast<std::uint64_t>(elapsed),
        sample, utc + elapsed, utc + elapsed + 200, true};
}
void precision_history_and_expiry() {
    Timebase t(config()); Anchor a; double uncertainty = -1;
    assert(t.begin(1) == Status::ok);
    assert(t.observe(bracket(base, 0)) == Status::ok);
    assert(t.anchor_for(1, base + 1, a, uncertainty) == Status::ok);
    assert(a.counter == base && a.utc_ns == utc + 100);
    assert(std::fabs(uncertainty - 400.008) < 1e-6);
    assert(t.anchor_for(1, base - 1, a, uncertainty) == Status::unavailable);
    assert(t.anchor_for(1, base + 25000001, a, uncertainty) == Status::expired);
    assert(t.observe(bracket(base + 2500000, 1000000000)) == Status::ok);
    assert(t.anchor_for(1, base + 100, a, uncertainty) == Status::ok && a.counter == base);
    assert(t.observe(bracket(base + 5000000, 2000000000)) == Status::ok);
    assert(t.retained() == 2);
    assert(t.anchor_for(1, base + 100, a, uncertainty) == Status::unavailable);
    assert(t.begin(1) == Status::invalid_generation);
    assert(t.begin(2) == Status::ok && !t.qualified());
    assert(t.anchor_for(1, base, a, uncertainty) == Status::invalid_generation);
}
void discontinuity_requires_new_generation() {
    Timebase t(config()); assert(t.begin(4) == Status::ok);
    assert(t.observe(bracket(base, 0)) == Status::ok);
    auto b = bracket(base + 2500000, 1000000000);
    b.utc_before_ns += 1000000; b.utc_after_ns += 1000000;
    assert(t.observe(b) == Status::clock_discontinuity && !t.qualified());
    assert(t.observe(bracket(base, 0)) == Status::unavailable);
    assert(t.begin(5) == Status::ok);
    assert(t.observe(bracket(base, 0)) == Status::ok);
    assert(t.observe(bracket(base - 1, 1000)) == Status::counter_regression);
    assert(t.begin(6) == Status::ok);
    b = bracket(base, 0); b.utc_after_ns += 100000000;
    assert(t.observe(b) == Status::clock_discontinuity);
    assert(t.begin(7) == Status::ok);
    b = bracket(base, 0); b.exact_counter = false;
    assert(t.observe(b) == Status::unqualified_counter);
    b = bracket(base, 0); b.monotonic_after_ns += 2000000;
    assert(t.observe(b) == Status::invalid_bracket && !t.qualified());
    assert(t.begin(8)==Status::ok);
    assert(t.observe(bracket(base,0))==Status::ok);
    b=bracket(base+2500000,1000000000);b.monotonic_after_ns+=2000000;
    assert(t.observe(b)==Status::invalid_bracket && !t.qualified());
    Anchor a;double width;
    assert(t.anchor_for(8,base,a,width)==Status::unavailable);
}
void asymmetric_clock_reads() {
    Timebase t(config()); assert(t.begin(1)==Status::ok);
    auto a=bracket(base,0);
    a.monotonic_before_ns-=900000;
    assert(t.observe(a)==Status::ok);
    auto b=bracket(base+2500000,1000000000);
    b.monotonic_after_ns+=900000;
    assert(t.observe(b)==Status::ok);
    Anchor anchor; double width;
    assert(t.anchor_for(1,b.counter,anchor,width)==Status::ok);
    assert(width==900400);
}
struct Fake { int call{}; int fail_at{}; };
int mono(void* p, std::uint64_t* out) { auto& f=*static_cast<Fake*>(p); ++f.call; *out=1000+f.call*100; return f.call==f.fail_at; }
int real(void* p, std::int64_t* out) { auto& f=*static_cast<Fake*>(p); ++f.call; *out=utc+f.call*100; return f.call==f.fail_at; }
int counter(void* p, std::uint64_t* out) { auto& f=*static_cast<Fake*>(p); assert(++f.call==3); *out=base; return f.call==f.fail_at; }
void read_order_and_transaction() {
    Fake f; ReadPort p{&f,mono,real,counter,true}; Bracket b;
    assert(read_bracket(p,b)==Status::ok && f.call==5 && b.counter==base);
    assert(b.utc_before_ns==utc+200 && b.utc_after_ns==utc+400);
    for(int fail=1; fail<=5; ++fail) { f={0,fail}; b.counter=123; assert(read_bracket(p,b)==Status::read_error && b.counter==123); }
    p.exact_counter=false; f={}; assert(read_bracket(p,b)==Status::unqualified_counter && f.call==0);
}
}
int main() {
    precision_history_and_expiry(); discontinuity_requires_new_generation();
    asymmetric_clock_reads(); read_order_and_transaction();
    PosixClock real_clock{nullptr,[](void*,std::uint64_t* n){*n=17;return 0;},true};
    Bracket b;assert(read_bracket(real_clock.port(),b)==Status::ok);
    assert(b.counter==17 && b.utc_before_ns>0 && b.utc_after_ns>=b.utc_before_ns);
    assert(b.monotonic_after_ns>=b.monotonic_before_ns);
}
