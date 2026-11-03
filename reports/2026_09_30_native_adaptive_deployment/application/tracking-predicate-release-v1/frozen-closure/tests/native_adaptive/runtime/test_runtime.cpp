#include "runtime.hpp"
#include "projection.hpp"
#include "sha256.hpp"
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <vector>

using namespace leo::adaptive;
template<class F> static void throws(F f) {
    bool did=false; try {f();} catch(const std::exception&) {did=true;} assert(did);
}
static std::vector<std::vector<int16_t>> windows(size_t chunk) {
    constexpr uint32_t rate=2500000;
    const Visit v{1,42,UINT64_C(9007199254741093),UINT64_C(9007199255641093),rate,2,11200000000.0};
    std::vector<int16_t> iq(900000*4);
    for(size_t i=0;i<iq.size();++i) iq[i]=static_cast<int16_t>((i*73)%32767);
    std::vector<std::vector<int16_t>> result;
    WindowAssembler a(rate,2,[&](const Window& w){
        assert(w.first==v.first+w.index*300000); assert(w.samples==50000);
        result.emplace_back(w.iq,w.iq+w.samples*4);
    });
    a.begin(v);
    for(size_t off=0;off<900000;off+=chunk)
        a.push(v.first+off,iq.data()+off*4,std::min(chunk,900000-off));
    a.finish(); assert(a.stats().emitted==3); assert(a.stats().missing==0);
    assert(a.stats().discontinuities==0); return result;
}
struct Latch { std::mutex m; std::condition_variable cv; bool entered=false,release=false; };
static void blocked(void* ptr,size_t) {
    auto& x=*static_cast<Latch*>(ptr); std::unique_lock<std::mutex> lock(x.m);
    x.entered=true; x.cv.notify_all(); x.cv.wait(lock,[&]{return x.release;});
}
static void inc(void* ptr,size_t) { ++*static_cast<std::atomic<unsigned>*>(ptr); }
static uint64_t bits(double value) {
    uint64_t result=0; std::memcpy(&result,&value,sizeof(result)); return result;
}
struct DerivationFake { unsigned calls{};unsigned mode{}; };
static SupportDerivationStatus derive_support(void* context,std::uint32_t rate,
    std::uint32_t samples,std::int64_t epoch,double offset,SupportDerivation* output) {
    auto& fake=*static_cast<DerivationFake*>(context);++fake.calls;
    if(fake.mode==1) return SupportDerivationStatus::unavailable;
    if(!output) return SupportDerivationStatus::invalid_input;
    output->numeric=fractional_support(rate,samples,epoch,offset);
    char second[64],third[64];
    std::snprintf(second,sizeof(second),"%.17g",output->numeric.moment2);
    std::snprintf(third,sizeof(third),"%.17g",output->numeric.moment3);
    output->factorial_moment_lexemes={"1.0","0.0",second,third};
    if(fake.mode==2) output->factorial_moment_lexemes[2]="0.0";
    if(fake.mode==3) output->factorial_moment_lexemes[2]=std::string(65,'1');
    if(fake.mode==4) {
        std::snprintf(second,sizeof(second),"%a",output->numeric.moment2);
        output->factorial_moment_lexemes[2]=second;
    }
    if(fake.mode==5) output->factorial_moment_lexemes[2]="+"+
        output->factorial_moment_lexemes[2];
    if(fake.mode==6) output->factorial_moment_lexemes[2]=" "+
        output->factorial_moment_lexemes[2];
    if(fake.mode==7) output->factorial_moment_lexemes[2]="0"+
        output->factorial_moment_lexemes[2];
    return SupportDerivationStatus::ok;
}
int main() {
    assert(sha256("")=="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    assert(sha256("abc")=="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    assert(sha256(std::string(1000000,'a'))=="cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0");
    assert(windows(7919)==windows(900000));
    assert(windows(1)==windows(270001));
    std::vector<int16_t> iq(360*4,17);
    unsigned emitted=0;
    WindowAssembler a(1000,2,[&](const Window&){++emitted;});
    Visit v{1,1,0,360,1000,2,1e9}; a.begin(v);
    a.push(0,iq.data(),10); a.push(11,iq.data()+44,349); a.finish();
    assert(emitted==2); assert(a.stats().missing==1); assert(a.stats().discontinuities==1);
    a.begin(v); a.push(0,iq.data(),120);
    throws([&]{a.push(0,iq.data(),1);}); a.finish(); assert(a.stats().missing==3);
    throws([&]{a.push(0,iq.data(),1);});
    throws([&]{WindowAssembler bad(0,2,[](const Window&){});});
    throws([&]{Visit bad=v;bad.rate=0;a.begin(bad);});
    // No fabricated trailing window or cross-visit sample fill.
    v.visit=2;v.end=19;a.begin(v);a.push(0,iq.data(),19);a.finish();
    assert(a.stats().missing==3);
    const uint64_t large=UINT64_C(9007199254740993);
    assert(support_utc_ns(large,1790557997299661326LL,large+100,0.25,2500000)
           ==1790557997299701426LL);
    assert(support_utc_ns(0,100,0,0.5,1000000000)==100);
    assert(support_utc_ns(0,100,0,1.5,1000000000)==102);
    throws([]{support_utc_ns(0,INT64_MAX,1,0,1);});
    throws([]{support_utc_ns(3,0,2,0,1000);});
    const auto s=fractional_support(2500000,50000,100,0.25);
    assert(s.first>=0 && s.end<=50000 && s.first<s.center && s.center<s.end);
    assert(s.symbols>900 && s.moment2>0);
    assert(bits(s.moment2)==UINT64_C(0x3ef166f15ab86ced));
    assert(bits(s.moment3)==UINT64_C(0x3d263e0245b216c1));
    // Non-integral offsets translate every retained symbol equally.  The
    // central moments and their binary64 representation must not depend on
    // that translation or on wider host intermediates.
    for (double offset : {-0.75,-0.25,0.125,0.75}) {
        const auto translated=fractional_support(2500000,50000,100,offset);
        assert(translated.symbols==s.symbols);
        assert(bits(translated.moment2)==bits(s.moment2));
        assert(bits(translated.moment3)==bits(s.moment3));
    }
    throws([]{fractional_support(2500000,50000,50000,0);});
    ProjectionSource src{"sha256:"+std::string(64,'a'),"sha256:"+std::string(64,'b'),
        1,large,large+100,42,1790557997299661326LL,2500000,0,1,4,false,11.2e9,1000,true};
    FractionalCandidate candidate{0,100,0.25,500,0.2,0.05,0.15,true};
    Observation obs;assert(project(src,candidate,obs));
    assert(obs.candidate_id.size()==71 && obs.measured_cfo_hz==500);
    assert(obs.support_start_utc_ns<obs.support_center_utc_ns);
    assert(obs.support_center_utc_ns<obs.support_end_utc_ns);
    const auto original_id=obs.candidate_id;
    candidate.complete=false;assert(!project(src,candidate,obs));assert(obs.candidate_id==original_id);
    candidate.complete=true;candidate.margin=0;throws([&]{project(src,candidate,obs);});
    candidate.margin=0.15+5e-11;throws([&]{project(src,candidate,obs);});
    candidate.margin=0.15;
    auto invalid_source=src;invalid_source.anchor_utc_ns=-1;
    throws([&]{project(invalid_source,candidate,obs);});
    invalid_source=src;invalid_source.probe_ms=10;
    throws([&]{project(invalid_source,candidate,obs);});
    auto zero_margin=candidate;zero_margin.exact_score=zero_margin.control_score;zero_margin.margin=0;
    assert(!project(src,zero_margin,obs,0));
    DerivationFake fake;
    const std::string unit_manifest="sha256:"+std::string(64,'c');
    const SupportDerivationPort port{&fake,"unit-profile",
        unit_manifest,derive_support};
    SupportDerivation derived;
    Observation profiled;
    assert(project(src,candidate,port,profiled,derived)==SupportProjectionStatus::emitted);
    assert(fake.calls==1 && bits(profiled.moment2)==bits(obs.moment2) &&
        bits(profiled.moment3)==bits(obs.moment3) &&
        profiled.support_center_utc_ns==obs.support_center_utc_ns);
    candidate.complete=false;
    assert(project(src,candidate,port,profiled,derived)==SupportProjectionStatus::nonpassing);
    assert(fake.calls==1);
    candidate.complete=true;fake.mode=1;const auto profiled_id=profiled.candidate_id;
    assert(project(src,candidate,port,profiled,derived)==
        SupportProjectionStatus::derivation_unavailable);
    assert(profiled.candidate_id==profiled_id && fake.calls==2);
    fake.mode=2;
    assert(project(src,candidate,port,profiled,derived)==
        SupportProjectionStatus::invalid_derivation);
    assert(profiled.candidate_id==profiled_id && fake.calls==3);
    fake.mode=3;
    assert(project(src,candidate,port,profiled,derived)==
        SupportProjectionStatus::invalid_derivation);
    assert(profiled.candidate_id==profiled_id && fake.calls==4);
    for(unsigned mode=4;mode<=7;++mode) {
        fake.mode=mode;const auto calls=fake.calls;
        assert(project(src,candidate,port,profiled,derived)==
            SupportProjectionStatus::invalid_derivation);
        assert(fake.calls==calls+1 && profiled.candidate_id==profiled_id);
    }
    fake.mode=0;
    const auto derived_lexemes=derived.factorial_moment_lexemes;
    const auto invalid_without_callback=[&](FractionalCandidate invalid) {
        const auto calls=fake.calls;
        throws([&]{(void)project(src,invalid,port,profiled,derived);});
        assert(fake.calls==calls && profiled.candidate_id==profiled_id &&
            derived.factorial_moment_lexemes==derived_lexemes);
    };
    auto invalid_candidate=candidate;invalid_candidate.integer_epoch=-1;
    invalid_without_callback(invalid_candidate);
    invalid_candidate=candidate;invalid_candidate.integer_epoch=50'000;
    invalid_without_callback(invalid_candidate);
    invalid_candidate=candidate;
    invalid_candidate.fractional_offset=std::numeric_limits<double>::quiet_NaN();
    invalid_without_callback(invalid_candidate);
    invalid_candidate.fractional_offset=std::numeric_limits<double>::infinity();
    invalid_without_callback(invalid_candidate);
    invalid_candidate.fractional_offset=2.0001;
    invalid_without_callback(invalid_candidate);
    const SupportDerivationPort absent{};
    assert(project(src,candidate,absent,profiled,derived)==
        SupportProjectionStatus::derivation_unavailable);
    for(size_t workers:{1u,2u,4u}) {
        Executor pool(workers,128); std::atomic<unsigned> count{0};
        for(unsigned i=0;i<100;++i) assert(pool.submit({i,inc,&count}));
        pool.drain(); assert(count==100); assert(pool.stats().completed==100);
        assert(pool.stats().running==0 && pool.stats().queued==0);
        pool.stop(); assert(!pool.submit({101,inc,&count}));
    }
    { Executor pool(1,1); Latch latch; std::atomic<unsigned> count{0};
      assert(pool.submit({0,blocked,&latch}));
      {std::unique_lock<std::mutex> l(latch.m);latch.cv.wait(l,[&]{return latch.entered;});}
      assert(pool.submit({1,inc,&count})); assert(!pool.submit({2,inc,&count}));
      {std::lock_guard<std::mutex> l(latch.m);latch.release=true;latch.cv.notify_all();}
      pool.drain();assert(count==1);assert(pool.stats().rejected==1);
    }
    { Executor pool(1,1);
      assert(pool.submit({0,[](void*,size_t){throw std::runtime_error("injected");},nullptr}));
      pool.drain(); assert(pool.stats().failed==1); throws([&]{pool.rethrow_first_failure();}); }
    throws([]{Executor bad(0,1);});
    std::cout << "{\"status\":\"pass\",\"window_chunkings\":4,\"worker_counts\":[1,2,4],"
                 "\"coverage\":[\"gaps\",\"ordering\",\"bounds\",\"utc_precision\","
                 "\"fractional_support\",\"backpressure\",\"failure\"]}\n";
}
