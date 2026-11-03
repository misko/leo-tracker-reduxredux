#include "session.hpp"
#include <cassert>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <mutex>
#include <stdexcept>
#include <thread>
using namespace leo::adaptive;
namespace {
constexpr std::uint64_t base=(UINT64_C(1)<<54)+123;
constexpr std::int64_t utc=1790740000000000000LL;
online::Config analysis() {
    online::Config c;c.maximum_history_observations=1000;c.maximum_satellites=1;
    c.maximum_knots=2;c.maximum_observations_per_track=1000;c.maximum_search_points=10;
    return c;
}
ingest::Authority authority() {
    return {7,2500000,"sha256:"+std::string(64,'a'),"sha256:"+std::string(64,'b'),
        {{2,123,4,1500000000,11.2e9,true}}};
}
leo_scanner_event event(unsigned visit) {
    leo_scanner_event e{};e.kind=LEO_SCANNER_CANDIDATE;e.visit=visit;
    e.valid_start=base+static_cast<std::uint64_t>(visit)*2500000;
    e.valid_end=e.valid_start+300000;e.profile=2;e.attested_profile_crc32=123;
    e.frequency_hz=1500000000;
    auto& c=e.candidate;c.epoch=100;c.fractional_epoch_status=1;
    c.fractional_epoch_offset_samples=.25;c.fractional_tracking_cfo_hz=1000+visit*500;
    c.fractional_exact_score=.2;c.fractional_control_score=.05;c.fractional_margin=.15;
    return e;
}
struct DerivationFake {
    std::atomic<unsigned> calls{0},active{0},overlaps{0};
    bool unavailable{},block_first{};
    std::mutex mutex;
    std::condition_variable changed;
    bool entered{},release{};
    std::thread::id callback_thread;
};
std::string exact_with_trailing_zero(double value) {
    char buffer[64];std::snprintf(buffer,sizeof(buffer),"%.17g",value);
    std::string output(buffer);const auto exponent=output.find('e');
    if(exponent==std::string::npos) output.push_back('0');
    else output.insert(exponent,1,'0');
    return output;
}
SupportDerivationStatus derive(void* context,std::uint32_t rate,std::uint32_t samples,
    std::int64_t epoch,double offset,SupportDerivation* output) {
    auto& fake=*static_cast<DerivationFake*>(context);
    fake.callback_thread=std::this_thread::get_id();
    const auto call=++fake.calls;
    if(fake.active.fetch_add(1)!=0) ++fake.overlaps;
    if(fake.block_first && call==1) {
        std::unique_lock<std::mutex> lock(fake.mutex);fake.entered=true;fake.changed.notify_all();
        fake.changed.wait(lock,[&]{return fake.release;});
    }
    const auto finish=[&](SupportDerivationStatus status) {
        --fake.active;return status;
    };
    if(fake.unavailable) return finish(SupportDerivationStatus::unavailable);
    if(!output) return finish(SupportDerivationStatus::invalid_input);
    output->numeric=fractional_support(rate,samples,epoch,offset);
    output->factorial_moment_lexemes={"1.0","0.0",
        exact_with_trailing_zero(output->numeric.moment2),
        exact_with_trailing_zero(output->numeric.moment3)};
    return finish(SupportDerivationStatus::ok);
}
void bounded_queue_and_tracking() {
    application::Session s(authority(),{2500000,1000000,120000000000ULL,10,100,8},
        analysis(),{"recorded-session","sha256:"+std::string(64,'a'),utc},2);
    assert(s.observe({10000,10200,base,utc,utc+200,true})==timing::Status::ok);
    assert(s.accept(event(0)).queued && s.accept(event(1)).queued);
    auto dropped=s.accept(event(2));
    assert(dropped.projection==ingest::Status::emitted && !dropped.queued);
    assert(s.stats().queued==2 && s.stats().queue_dropped==1);
    std::shared_ptr<const online::Snapshot> snapshot;
    assert(s.publish(&snapshot)==online::Status::invalid && !snapshot);
    assert(s.consume(1)==1 && s.stats().queued==1);
    assert(s.consume(2)==1);
    for(unsigned i=2;i<10;++i) { assert(s.accept(event(i)).queued);assert(s.consume(1)==1); }
    assert(s.publish(&snapshot)==online::Status::ok);
    assert(snapshot && snapshot->retained_observation_count==10);
    assert(!snapshot->tracking_result.tracks.empty());
    assert(s.stats().consumed==10 && s.stats().rejected==0 && s.stats().high_water==2);
}
void producer_and_analysis_owner() {
    application::Session s(authority(),{2500000,1000000,120000000000ULL,10,100,8},
        analysis(),{"recorded-session","sha256:"+std::string(64,'a'),utc},8);
    assert(s.observe({10000,10200,base,utc,utc+200,true})==timing::Status::ok);
    std::atomic<bool> done{false};
    std::thread producer([&]{for(unsigned i=0;i<100;++i) (void)s.accept(event(i));done=true;});
    while(!done || s.stats().queued) { s.consume(3);std::this_thread::yield(); }
    producer.join();const auto stats=s.stats();
    assert(stats.projected==100 && stats.consumed+stats.queue_dropped==100);
    assert(!stats.rejected && stats.high_water<=8 && !stats.queued);
}
void quiet_watermark_preserves_pending_evidence() {
    application::Session s(authority(),{2500000,1000000,120000000000ULL,10,100,8},
        analysis(),{"recorded-session","sha256:"+std::string(64,'a'),utc},2);
    assert(s.observe({10000,10200,base,utc,utc+200,true})==timing::Status::ok);
    assert(s.accept(event(0)).queued);
    const auto future=utc+700'000'000'000LL;
    assert(s.watermark()==0);
    assert(s.advance_watermark(future)==online::Status::invalid);
    assert(s.watermark()==0);
    assert(s.stats().queued==1 && s.stats().consumed==0);
    assert(s.consume(1)==1 && s.stats().consumed==1 && !s.stats().rejected);
    assert(s.watermark()>utc && s.watermark()<utc+1'000'000'000LL);
    // Rejected advancement must not have moved the coordinator clock.
    assert(s.advance_watermark(utc+1'000'000'000LL)==online::Status::ok);
    assert(s.advance_watermark(future)==online::Status::ok);
    assert(s.watermark()==future);
}
void in_window_capacity_loss_is_visible() {
    auto config=analysis();config.maximum_history_observations=2;
    application::Session s(authority(),{2500000,1000000,120000000000ULL,10,100,8},
        config,{"capacity-session","sha256:"+std::string(64,'a'),utc},2);
    assert(s.observe({10000,10200,base,utc,utc+200,true})==timing::Status::ok);
    for(unsigned i=0;i<4;++i) { assert(s.accept(event(i)).queued);assert(s.consume(1)==1); }
    assert(s.stats().consumed==4 && s.stats().history_capacity_evictions==2);
    assert(s.advance_watermark(utc+700'000'000'000LL)==online::Status::ok);
    assert(s.stats().history_capacity_evictions==2);
}

// Independent detector lanes can finish in reverse order. Test the public
// session boundary before enabling that execution strategy in the scanner.
void detector_completion_order_preserves_final_science() {
    auto run=[](unsigned mode) {
        application::Session s(authority(),{2500000,1000000,120000000000ULL,10,100,8},
            analysis(),{"reordered-session","sha256:"+std::string(64,'a'),utc},16);
        assert(s.observe({10000,10200,base,utc,utc+200,true})==timing::Status::ok);
        if(mode==2) {
            std::atomic<unsigned> finished{0};
            auto lane=[&](unsigned parity) {
                for(unsigned i=parity;i<10;i+=2) assert(s.accept(event(i)).queued);
                ++finished;
            };
            std::thread first(lane,0),second(lane,1);
            while(finished.load()!=2 || s.stats().queued) {
                s.consume(2);std::this_thread::yield();
            }
            first.join();second.join();
        } else {
            for(unsigned i=0;i<10;++i) {
                assert(s.accept(event(mode==1?9-i:i)).queued);
                const auto before=s.watermark();
                assert(s.consume(1)==1 && s.watermark()>=before);
            }
        }
        const auto stats=s.stats();
        assert(stats.consumed==10 && !stats.rejected && !stats.queue_dropped);
        std::shared_ptr<const online::Snapshot> snapshot;
        assert(s.publish(&snapshot)==online::Status::ok);
        assert(snapshot && snapshot->retained_observation_count==10);
        assert(!snapshot->tracking_result.tracks.empty());
        return snapshot;
    };
    const auto serial=run(0);
    for(unsigned mode=1;mode<=2;++mode) {
        const auto reordered=run(mode);
        assert(reordered->watermark_utc_ns==serial->watermark_utc_ns);
        assert(online::compare_reference(*reordered,serial->tracking_result).exact);
        const auto& expected=serial->location_tracks.owned;
        const auto& actual=reordered->location_tracks.owned;
        assert(actual.size()==expected.size());
        for(std::size_t i=0;i<actual.size();++i) {
            assert(actual[i].tracklet_id==expected[i].tracklet_id);
            assert(actual[i].support_digest==expected[i].support_digest);
            assert(actual[i].partition_seed==expected[i].partition_seed);
            assert(actual[i].observation_ids==expected[i].observation_ids);
            assert(actual[i].times_s==expected[i].times_s);
            assert(actual[i].measured_hz==expected[i].measured_hz);
            assert(actual[i].training_mask==expected[i].training_mask);
        }
    }
}

std::shared_ptr<const online::Snapshot> published(application::Session& session) {
    assert(session.observe({10000,10200,base,utc,utc+200,true})==timing::Status::ok);
    for(unsigned i=0;i<10;++i) {
        assert(session.accept(event(i)).queued);
        assert(session.consume(1)==1);
    }
    std::shared_ptr<const online::Snapshot> snapshot;
    assert(session.publish(&snapshot)==online::Status::ok && snapshot);
    return snapshot;
}

void profiled_support_authority_is_session_bound() {
    DerivationFake fake;
    std::string profile="unit-server-authority";
    std::string manifest="sha256:"+std::string(64,'c');
    SupportDerivationPort port{&fake,profile,manifest,derive};
    application::Session profiled(authority(),
        {2500000,1000000,120000000000ULL,10,100,8},analysis(),
        {"profiled-session","sha256:"+std::string(64,'a'),utc},16,port);
    profile="mutated-after-copy";manifest="sha256:"+std::string(64,'d');
    const auto* binding=profiled.support_profile_binding();
    assert(binding && binding->profile_name=="unit-server-authority" &&
        binding->profile_manifest_digest=="sha256:"+std::string(64,'c'));
    const auto profiled_snapshot=published(profiled);
    assert(fake.calls==10 && !fake.overlaps);

    application::Session portable(authority(),
        {2500000,1000000,120000000000ULL,10,100,8},analysis(),
        {"profiled-session","sha256:"+std::string(64,'a'),utc},16);
    assert(portable.support_profile_binding()==nullptr);
    const auto portable_snapshot=published(portable);
    assert(online::compare_reference(*profiled_snapshot,
        portable_snapshot->tracking_result).exact);
    assert(profiled_snapshot->location_tracks.owned.size()==
        portable_snapshot->location_tracks.owned.size());
    bool authority_differs=false;
    for(std::size_t i=0;i<profiled_snapshot->location_tracks.owned.size();++i) {
        const auto& left=profiled_snapshot->location_tracks.owned[i];
        const auto& right=portable_snapshot->location_tracks.owned[i];
        assert(left.tracklet_id==right.tracklet_id &&
            left.observation_ids==right.observation_ids);
        authority_differs=authority_differs || left.support_digest!=right.support_digest;
    }
    assert(authority_differs);

    fake.unavailable=true;
    application::Session failure(authority(),
        {2500000,1000000,120000000000ULL,10,100,8},analysis(),
        {"failure-session","sha256:"+std::string(64,'a'),utc},2,
        {&fake,"unit-server-authority","sha256:"+std::string(64,'c'),derive});
    assert(failure.observe({10000,10200,base,utc,utc+200,true})==timing::Status::ok);
    const auto first=failure.accept(event(0));
    const auto second=failure.accept(event(1));
    assert(first.projection==ingest::Status::emitted && first.queued && first.deferred);
    assert(second.projection==ingest::Status::emitted && second.queued && second.deferred);
    assert(fake.calls==10);
    const auto failed=failure.consume_reported(1);
    assert(failed.dequeued==1 && !failed.ingested &&
        failed.status==application::ConsumeStatus::support_unavailable);
    const auto failed_stats=failure.stats();
    assert(failed_stats.profile_prepared==2 && failed_stats.projected==0 &&
        failed_stats.support_unavailable==1 && failed_stats.support_unhealthy &&
        failed_stats.discarded_after_support_failure==1 && !failed_stats.queued &&
        !failed_stats.support_derivation_inflight);
    std::shared_ptr<const online::Snapshot> forbidden;
    assert(failure.publish(&forbidden)==online::Status::invalid && !forbidden);
    assert(failure.advance_watermark(utc+1'000'000'000LL)==online::Status::invalid);
    const auto after_failure=failure.accept(event(2));
    assert(after_failure.projection==ingest::Status::invalid_event &&
        !after_failure.queued && !after_failure.deferred);
    assert(failure.stats().rejected_after_support_failure==1);
    bool threw=false;
    try { (void)failure.consume(1); }
    catch(const std::runtime_error&) { threw=true; }
    assert(threw);
}

void profiled_port_validation_and_serialization() {
    const auto construct=[](const SupportDerivationPort& port) {
        return std::make_unique<application::Session>(authority(),
            timing::Config{2500000,1000000,120000000000ULL,10,100,8},analysis(),
            online::SessionAuthority{"bad-profile","sha256:"+std::string(64,'a'),utc},2,port);
    };
    DerivationFake fake;bool rejected=false;
    try { (void)construct({&fake,"","sha256:"+std::string(64,'c'),derive}); }
    catch(const std::invalid_argument&) { rejected=true; }
    assert(rejected);rejected=false;
    try { (void)construct({&fake,"profile","bad",derive}); }
    catch(const std::invalid_argument&) { rejected=true; }
    assert(rejected);rejected=false;
    try { (void)construct({nullptr,"profile","sha256:"+std::string(64,'c'),derive}); }
    catch(const std::invalid_argument&) { rejected=true; }
    assert(rejected);

    fake.block_first=true;
    application::Session session(authority(),
        {2500000,1000000,120000000000ULL,10,100,8},analysis(),
        {"serialized-profile","sha256:"+std::string(64,'a'),utc},4,
        {&fake,"profile","sha256:"+std::string(64,'c'),derive});
    assert(session.observe({10000,10200,base,utc,utc+200,true})==timing::Status::ok);
    const auto accepted=session.accept(event(0));
    assert(accepted.queued && accepted.deferred && fake.calls==0);
    application::ConsumeReceipt consumed;
    std::thread consumer([&]{consumed=session.consume_reported(1);});
    const auto consumer_id=consumer.get_id();
    {
        std::unique_lock<std::mutex> lock(fake.mutex);
        assert(fake.changed.wait_for(lock,std::chrono::seconds(2),
            [&]{return fake.entered;}));
    }
    assert(session.stats().support_derivation_inflight);
    std::mutex progress_mutex;std::condition_variable progress_changed;
    bool producer_finished=false;
    std::thread producer([&] {
        assert(session.observe({1000010000,1000010200,base+2500000,utc+1000000000LL,
            utc+1000000200LL,true})==timing::Status::ok);
        const auto next=session.accept(event(1));
        assert(next.queued && next.deferred);
        std::lock_guard<std::mutex> lock(progress_mutex);
        producer_finished=true;progress_changed.notify_all();
    });
    {
        std::unique_lock<std::mutex> lock(progress_mutex);
        assert(progress_changed.wait_for(lock,std::chrono::seconds(2),
            [&]{return producer_finished;}));
    }
    producer.join();
    std::shared_ptr<const online::Snapshot> forbidden;
    assert(session.publish(&forbidden)==online::Status::invalid && !forbidden);
    assert(session.advance_watermark(utc+2'000'000'000LL)==online::Status::invalid);
    {
        std::lock_guard<std::mutex> lock(fake.mutex);fake.release=true;
    }
    fake.changed.notify_all();consumer.join();
    assert(consumed.status==application::ConsumeStatus::ok && consumed.dequeued==1 &&
        consumed.ingested==1 && fake.callback_thread==consumer_id);
    assert(session.consume_reported(1).ingested==1);
    const auto stats=session.stats();
    assert(fake.calls==2 && !fake.overlaps && !stats.queued &&
        stats.profile_prepared==2 && stats.support_derived==2 &&
        stats.projected==2 && stats.consumed==2 &&
        stats.support_derivation_count==2 && !stats.support_unhealthy &&
        !stats.support_derivation_inflight);
}

void profiled_duplicate_fails_closed_without_partial_publication() {
    DerivationFake fake;
    application::Session session(authority(),
        {2500000,1000000,120000000000ULL,10,100,8},analysis(),
        {"duplicate-profile","sha256:"+std::string(64,'a'),utc},4,
        {&fake,"profile","sha256:"+std::string(64,'c'),derive});
    assert(session.observe({10000,10200,base,utc,utc+200,true})==timing::Status::ok);
    assert(session.accept(event(0)).deferred);
    assert(session.accept(event(0)).deferred);
    const auto receipt=session.consume_reported(2);
    assert(receipt.dequeued==2 && receipt.ingested==1 &&
        receipt.status==application::ConsumeStatus::coordinator_rejected);
    const auto stats=session.stats();
    assert(stats.projected==2 && stats.support_derived==2 && stats.consumed==1 &&
        stats.rejected==1 && stats.support_unhealthy && !stats.queued);
    std::shared_ptr<const online::Snapshot> forbidden;
    assert(session.publish(&forbidden)==online::Status::invalid && !forbidden);
    bool threw=false;
    try { (void)session.consume(1); }
    catch(const std::runtime_error&) { threw=true; }
    assert(threw);
}

void portable_report_preserves_rejection_without_changing_legacy_behavior() {
    application::Session session(authority(),
        {2500000,1000000,120000000000ULL,10,100,8},analysis(),
        {"portable-report","sha256:"+std::string(64,'a'),utc},4);
    assert(session.observe({10000,10200,base,utc,utc+200,true})==timing::Status::ok);
    assert(session.accept(event(0)).queued);
    assert(session.accept(event(0)).queued);
    assert(session.accept(event(1)).queued);
    const auto receipt=session.consume_reported(3);
    assert(receipt.dequeued==3 && receipt.ingested==2 &&
        receipt.status==application::ConsumeStatus::coordinator_rejected);
    const auto stats=session.stats();
    assert(stats.consumed==2 && stats.rejected==1 && !stats.support_unhealthy);
    assert(session.consume(1)==0);
}

void profiled_bounded_batch_queue() {
    DerivationFake fake;
    application::Session session(authority(),
        {2500000,1000000,120000000000ULL,10,100,8},analysis(),
        {"profiled-batch","sha256:"+std::string(64,'a'),utc},4,
        {&fake,"profile","sha256:"+std::string(64,'c'),derive});
    assert(session.observe({10000,10200,base,utc,utc+200,true})==timing::Status::ok);
    for(unsigned i=0;i<4;++i) {
        const auto accepted=session.accept(event(i));
        assert(accepted.projection==ingest::Status::emitted && accepted.queued &&
            accepted.deferred);
    }
    const auto dropped=session.accept(event(4));
    assert(dropped.projection==ingest::Status::emitted && !dropped.queued &&
        !dropped.deferred && fake.calls==0);
    const auto full=session.stats();
    assert(full.profile_prepared==5 && full.high_water==4 && full.queued==4 &&
        full.queue_dropped==1 && !full.projected && !full.support_derived);
    std::shared_ptr<const online::Snapshot> forbidden;
    assert(session.publish(&forbidden)==online::Status::invalid && !forbidden);
    assert(session.advance_watermark(utc+2'000'000'000LL)==online::Status::invalid);
    const auto first=session.consume_reported(2);
    assert(first.status==application::ConsumeStatus::ok && first.dequeued==2 &&
        first.ingested==2 && fake.calls==2);
    const auto second=session.consume_reported(2);
    assert(second.status==application::ConsumeStatus::ok && second.dequeued==2 &&
        second.ingested==2 && fake.calls==4);
    const auto drained=session.stats();
    assert(drained.profile_prepared==5 && drained.projected==4 &&
        drained.support_derived==4 && drained.consumed==4 && !drained.rejected &&
        !drained.queued && !drained.support_unhealthy);
    std::shared_ptr<const online::Snapshot> snapshot;
    assert(session.publish(&snapshot)==online::Status::ok && snapshot &&
        snapshot->retained_observation_count==4);
}
}
int main() { bounded_queue_and_tracking();producer_and_analysis_owner();
    quiet_watermark_preserves_pending_evidence();in_window_capacity_loss_is_visible();
    detector_completion_order_preserves_final_science();
    profiled_support_authority_is_session_bound();
    profiled_port_validation_and_serialization();
    profiled_duplicate_fails_closed_without_partial_publication();
    portable_report_preserves_rejection_without_changing_legacy_behavior();
    profiled_bounded_batch_queue(); }
