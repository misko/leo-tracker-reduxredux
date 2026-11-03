#include "tracking.hpp"
#include <atomic>
#include <cassert>
#include <cstdlib>
#include <iomanip>
#include <new>
#include <sstream>
#include <stdexcept>
#include <thread>

namespace { thread_local bool fail_next_allocation=false; }
void* operator new(std::size_t size) {
    if (fail_next_allocation) { fail_next_allocation=false; throw std::bad_alloc(); }
    if (void* result=std::malloc(size?size:1)) return result;
    throw std::bad_alloc();
}
void operator delete(void* ptr) noexcept { std::free(ptr); }
void operator delete(void* ptr,std::size_t) noexcept { std::free(ptr); }

using namespace leo::adaptive::tracking;
namespace {
std::string id(unsigned n) {
    std::ostringstream out;
    out << "sha256:" << std::hex << std::setfill('0') << std::setw(64) << n;
    return out.str();
}
std::vector<Candidate> fixture(unsigned count) {
    std::vector<Candidate> rows;
    for(unsigned time=0;time<count;++time) for(unsigned lane=0;lane<4;++lane) {
        const auto ordinal=time*4+lane+1;
        const std::int64_t center=1800000000000000000LL+time*1000000000LL;
        rows.push_back({id(ordinal),id(ordinal+1000),static_cast<int>(lane),1,
            "lower",11.2e9,center-1000000,center,center+1000000,
            500.0+lane*10000.0,.3,.1,.2});
    }
    return rows;
}
std::string fingerprint(const Result& result) {
    std::ostringstream out;out << std::hexfloat;
    out << result.config_digest << ' ' << result.input_candidate_count << ' '
        << result.used_candidate_count << ' ' << result.tracks.size() << '\n';
    for(const auto& t:result.tracks) {
        out << t.segment_id << ' ' << t.tracklet_id << ' ' << t.lane.channel << ' '
            << t.lane.edge << ' ' << t.lane.receiver_id << ' ' << t.lane.actual_rf_hz
            << ' ' << t.start_utc_ns << ' ' << t.end_utc_ns << ' ' << t.reference_utc_ns
            << ' ' << t.normalized_rate_hz_per_s << ' ' << t.normalized_intercept_hz
            << ' ' << t.residual_rms_hz << ' ' << t.residual_max_hz
            << ' ' << t.weighted_support << ' ' << t.points.size() << '\n';
        for(const auto& p:t.points) out << p.candidate_id << ' ' << p.source_group_id
            << ' ' << p.relative_alias_index << ' ' << p.normalized_raw_cfo_hz
            << ' ' << p.normalized_dealiased_cfo_hz << '\n';
    }
    return out.str();
}
struct Adapter {
    std::atomic<unsigned> completed{0};
    bool inject_failure=false;
    static void run(void* opaque,std::size_t count,void* ctx,void (*task)(void*,std::size_t)) {
        auto& self=*static_cast<Adapter*>(opaque);
        auto work=[&](std::size_t parity) {
            // Reverse visitation deliberately differs from the serial map order.
            for(std::size_t offset=parity;offset<count;offset+=2) {
                const auto index=count-1-offset;
                if(self.inject_failure && index==0) fail_next_allocation=true;
                task(ctx,index);
                assert(!fail_next_allocation);
                ++self.completed;
            }
        };
        std::thread worker([&]{work(1);});
        work(0);worker.join();
    }
};
}
int main() {
    Config config;config.slope_bins=3;config.intercept_bins=100;
    config.minimum_slope_hz_per_s=-1;config.maximum_slope_hz_per_s=1;
    config.alias_spacing_hz=100000;config.residual_gate_hz=1000;
    const auto rows=fixture(8),prefix=fixture(6);
    const auto expected=reconstruct(rows,config);
    assert(expected.tracks.size()==4);
    Adapter adapter;LaneExecution execution{&adapter,Adapter::run};
    assert(fingerprint(reconstruct(rows,config,execution))==fingerprint(expected));
    assert(adapter.completed==4);
    Reconstructor cached;
    assert(fingerprint(cached.reconstruct(prefix,config,execution))==
        fingerprint(reconstruct(prefix,config)));
    assert(fingerprint(cached.reconstruct(rows,config,execution))==fingerprint(expected));
    assert(cached.stats().last_extended_lanes==4);
    assert(fingerprint(cached.reconstruct(rows,config,execution))==fingerprint(expected));
    assert(cached.stats().last_reused_lanes==4);
    Adapter failing;failing.inject_failure=true;bool caught=false;
    try { (void)reconstruct(rows,config,LaneExecution{&failing,Adapter::run}); }
    catch(const std::bad_alloc&) { caught=true; }
    assert(caught && failing.completed==4); // Every callback joined before rethrow.
    assert(fingerprint(reconstruct(rows,config))==fingerprint(expected));
    Reconstructor recovering;
    (void)recovering.reconstruct(prefix,config,execution);
    failing.completed=0;caught=false;
    try { (void)recovering.reconstruct(rows,config,LaneExecution{&failing,Adapter::run}); }
    catch(const std::bad_alloc&) { caught=true; }
    assert(caught && failing.completed==4);
    assert(fingerprint(recovering.reconstruct(rows,config,execution))==fingerprint(expected));
    assert(recovering.stats().last_reused_lanes==4);
    caught=false;
    try { (void)reconstruct(rows,config,LaneExecution{nullptr,
        [](void*,std::size_t count,void* ctx,void (*task)(void*,std::size_t)) {
            auto duplicate=[&]{for(std::size_t i=0;i<count;++i) task(ctx,i);};
            std::thread worker(duplicate);duplicate();worker.join();
        }}); }
    catch(const std::logic_error&) { caught=true; }
    assert(caught);
    caught=false;
    try { (void)reconstruct(rows,config,LaneExecution{nullptr,
        [](void*,std::size_t count,void* ctx,void (*task)(void*,std::size_t)) {
            task(ctx,count);
        }}); }
    catch(const std::logic_error&) { caught=true; }
    assert(caught);
    caught=false;
    try { (void)reconstruct(rows,config,LaneExecution{nullptr,
        [](void*,std::size_t,void*,void (*)(void*,std::size_t)) {}}); }
    catch(const std::logic_error&) { caught=true; }
    assert(caught);
    caught=false;
    try { (void)reconstruct(rows,config,LaneExecution{nullptr,
        [](void*,std::size_t,void*,void (*)(void*,std::size_t)) {
            throw std::runtime_error("executor unavailable");
        }}); }
    catch(const std::runtime_error&) { caught=true; }
    assert(caught);
}
