#include "live.hpp"

#include <cassert>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <stdexcept>
#include <thread>

using namespace leo::adaptive;
using namespace leo::adaptive::application::live;
namespace {
constexpr std::uint64_t base=(UINT64_C(1)<<54)+9000;
constexpr std::int64_t utc=INT64_C(1790740000000000000);

leo_tle_record tle() {
    leo_tle_record value{}; value.satellite_id=44714;
    constexpr char one[]="1 44714U 19074B   26270.09087237  .00034246  00000-0  33881-3 0  9999";
    constexpr char two[]="2 44714  53.1459 294.7156 0002678  78.6558 281.4759 15.65554847380103";
    static_assert(sizeof(one)==70 && sizeof(two)==70);
    std::memcpy(value.line1,one,sizeof(one)); std::memcpy(value.line2,two,sizeof(two));
    return value;
}

AnalysisConfig config() {
    ingest::Authority authority{7,2500000,"sha256:"+std::string(64,'a'),
        "sha256:"+std::string(64,'b'),{{2,123,4,1500000000,11.2e9,true}}};
    online::Config online; online.history_window_ns=10'000'000'000LL;
    online.maximum_satellites=1; online.maximum_knots=32;
    online.maximum_orbit_bytes=32U*sizeof(leo_orbit_state)*2U;
    online::SearchConfig search{}; search.origin_latitude_deg=37.8;
    search.origin_longitude_deg=-122.4; search.score=leo_score_default_config();
    search.policy.radius_km=1; search.policy.region_size_km=2;
    search.policy.level_count=1; search.policy.levels_km[0]=2;
    search.policy.budget_points=1;
    return {authority,{2500000,1000000,120000000000ULL,10,100,1024},online,
        {"fake-live","sha256:"+std::string(64,'a'),utc+100},{tle()},search,
        100000000,10000000000ULL,1,1.0,32,false,1,{}};
}

leo_scanner_event candidate(unsigned index) {
    leo_scanner_event event{}; event.kind=LEO_SCANNER_CANDIDATE;
    event.visit=index; event.valid_start=base+static_cast<std::uint64_t>(index)*2500000;
    event.valid_end=event.valid_start+300000; event.target=0; event.profile=2;
    event.attested_profile_crc32=124; event.frequency_hz=1500000000;
    event.receiver_id=0; event.probe_index=0; event.candidate_index=0;
    event.candidate.epoch=100; event.candidate.fractional_epoch_status=1;
    event.candidate.fractional_epoch_offset_samples=.25;
    event.candidate.fractional_tracking_cfo_hz=1000+index*500;
    event.candidate.fractional_exact_score=.2;
    event.candidate.fractional_control_score=.05;
    event.candidate.fractional_margin=.15;
    const auto now=static_cast<std::uint64_t>(std::chrono::duration_cast<
        std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count());
    event.detector_enqueued_monotonic_ns=now;
    event.detector_started_monotonic_ns=now;
    event.detector_finished_monotonic_ns=now;
    return event;
}

struct SupportFake {
    bool unavailable{};
    std::atomic<unsigned> calls{0};
};

std::string support_number(double value) {
    char buffer[64];
    std::snprintf(buffer,sizeof(buffer),"%.17g",value);
    std::string output(buffer);
    const auto exponent=output.find('e');
    if(exponent==std::string::npos) output.push_back('0');
    else output.insert(exponent,1,'0');
    return output;
}

SupportDerivationStatus derive_support(void* context,std::uint32_t rate,
    std::uint32_t samples,std::int64_t epoch,double offset,SupportDerivation* output) {
    auto& fake=*static_cast<SupportFake*>(context);
    ++fake.calls;
    if(fake.unavailable) return SupportDerivationStatus::unavailable;
    if(!output) return SupportDerivationStatus::invalid_input;
    output->numeric=fractional_support(rate,samples,epoch,offset);
    output->factorial_moment_lexemes={"1.0","0.0",
        support_number(output->numeric.moment2),support_number(output->numeric.moment3)};
    return SupportDerivationStatus::ok;
}

int count_cancel(void* context) {
    ++*static_cast<std::atomic<unsigned>*>(context);
    return 0;
}

void fake_e2e() {
    auto value=config(); value.publication_interval_ns=1'000'000'000ULL;
    Analysis analysis(std::move(value));
    assert(analysis.observe({1000,1200,base,utc,utc+200,true})==timing::Status::ok);
    for (unsigned i=0;i<8;++i) analysis.event(candidate(i));
    assert(analysis.observe({8000001000ULL,8000001200ULL,base+20000000,
        utc+8000000000LL,utc+8000000200LL,true})==timing::Status::ok);
    analysis.detach_cancel();
    const auto result=analysis.finish_after_rf_stopped();
    assert(result.scanner_candidates==8 && result.accepted_candidates==8);
    assert(!result.session.queue_dropped && !result.session.rejected);
    assert(result.publications>=1 && result.orbit_builds>=1 && result.searches_started>=1);
    assert(result.timing_qualified);
    assert(result.latest_measured_source_progress_utc_before_ns==utc+8000000000LL);
    assert(result.latest_measured_source_progress_utc_after_ns==utc+8000000200LL);
    assert(result.latest_causal_frontier_utc_ns==utc+7900000000LL);
    assert(result.last_snapshot_watermark_utc_ns>0 &&
        result.last_result_snapshot_watermark_utc_ns==result.last_snapshot_watermark_utc_ns);
    assert(result.publication_compute_count>=1 && result.publication_compute_max_ns>0 &&
        result.publication_compute_total_ns>=result.publication_compute_max_ns);
    assert(result.publication_cadence_requests==8 && result.publication_cadence_serviced==1 &&
        result.publication_cadence_misses==7 && !result.publication_cadence_pending);
    assert(result.publication_cadence_requests==result.publication_cadence_serviced+
        result.publication_cadence_misses);
    assert(result.snapshot_source_age_count==result.publications &&
        result.snapshot_source_age_lower_current_ns<=result.snapshot_source_age_upper_current_ns &&
        result.snapshot_source_age_lower_max_ns<=result.snapshot_source_age_upper_max_ns);
    assert(result.result_source_age_count==result.searches_complete &&
        result.result_source_age_lower_current_ns<=result.result_source_age_upper_current_ns &&
        result.snapshot_result_duration_count==result.searches_complete &&
        result.snapshot_result_duration_max_ns>=result.snapshot_result_duration_current_ns);
    assert(!result.exact_score_cache.enabled && !result.exact_score_cache.track_hits &&
        !result.exact_score_cache.track_misses && !result.exact_score_cache.retained_sites);
}

void exact_score_cache_stats_are_owner_published() {
    auto value=config();
    value.caller_driven=true;
    value.publication_interval_ns=1'000'000'000ULL;
    value.online.maximum_exact_score_cache_bytes=1024U*1024U;
    Analysis analysis(std::move(value));
    assert(analysis.observe({1000,1200,base,utc,utc+200,true})==timing::Status::ok);
    for (unsigned i=0;i<8;++i) analysis.event(candidate(i));
    assert(analysis.observe({8000001000ULL,8000001200ULL,base+20000000,
        utc+8000000000LL,utc+8000000200LL,true})==timing::Status::ok);
    const auto processed=analysis.poll();
    const auto published=analysis.progress();
    assert(processed.exact_score_cache.enabled);
    assert(processed.exact_score_cache.track_misses>0);
    assert(processed.exact_score_cache.retained_sites==1);
    assert(processed.exact_score_cache.retained_payload_bytes>0);
    assert(published.exact_score_cache.track_hits==processed.exact_score_cache.track_hits);
    assert(published.exact_score_cache.track_misses==processed.exact_score_cache.track_misses);
    assert(published.exact_score_cache.retained_sites==processed.exact_score_cache.retained_sites);
    assert(published.exact_score_cache.retained_payload_bytes==
        processed.exact_score_cache.retained_payload_bytes);
    analysis.detach_cancel();
    (void)analysis.finish_after_rf_stopped();
}

void invalid_construction_does_not_terminate() {
    auto invalid=config(); invalid.catalogue.clear(); bool threw=false;
    try { Analysis analysis(std::move(invalid)); }
    catch (const std::invalid_argument&) { threw=true; }
    assert(threw);
    invalid=config(); invalid.publication_interval_ns=UINT64_MAX; threw=false;
    try { Analysis analysis(std::move(invalid)); }
    catch (const std::invalid_argument&) { threw=true; }
    assert(threw);
    invalid=config(); invalid.analysis_workers=0; threw=false;
    try { Analysis analysis(std::move(invalid)); }
    catch (const std::invalid_argument&) { threw=true; }
    assert(threw);
    invalid=config(); invalid.analysis_workers=5; threw=false;
    try { Analysis analysis(std::move(invalid)); }
    catch (const std::invalid_argument&) { threw=true; }
    assert(threw);

    invalid=config();
    invalid.support_derivation.profile_name="partial";
    threw=false;
    try { Analysis analysis(std::move(invalid)); }
    catch (const std::invalid_argument&) { threw=true; }
    assert(threw);
    SupportFake fake;
    const std::string malformed_name="profile";
    const std::string malformed_manifest="sha256:"+std::string(64,'c');
    invalid=config();
    invalid.support_derivation={nullptr,malformed_name,malformed_manifest,derive_support};
    threw=false;
    try { Analysis analysis(std::move(invalid)); }
    catch (const std::invalid_argument&) { threw=true; }
    assert(threw);
    invalid=config();
    invalid.support_derivation.context=&fake;
    threw=false;
    try { Analysis analysis(std::move(invalid)); }
    catch (const std::invalid_argument&) { threw=true; }
    assert(threw);
}

void optional_support_profile_binding_and_failure() {
    SupportFake fake;
    std::string name="test-support-profile";
    std::string manifest="sha256:"+std::string(64,'c');
    auto value=config(); value.caller_driven=true;
    value.support_derivation={&fake,name,manifest,derive_support};
    Analysis profiled(std::move(value));
    name="mutated";manifest="sha256:"+std::string(64,'d');
    const auto initial=profiled.progress();
    assert(initial.support_profile_bound);
    assert(initial.support_profile.profile_name=="test-support-profile");
    assert(initial.support_profile.profile_manifest_digest=="sha256:"+std::string(64,'c'));
    assert(initial.timing_qualified);
    assert(profiled.observe({1000,1200,base,utc,utc+200,true})==timing::Status::ok);
    profiled.event(candidate(0));
    const auto processed=profiled.poll();
    assert(fake.calls==1 && processed.session.profile_prepared==1);
    assert(processed.session.support_derived==1 && processed.session.consumed==1);
    assert(!processed.session.support_unhealthy && processed.timing_qualified);
    profiled.detach_cancel();
    (void)profiled.finish_after_rf_stopped();

    fake.unavailable=true;
    const std::string failure_name="test-support-profile";
    const std::string failure_manifest="sha256:"+std::string(64,'c');
    value=config(); value.caller_driven=true;
    value.support_derivation={&fake,failure_name,failure_manifest,derive_support};
    Analysis failed(std::move(value));
    std::atomic<unsigned> cancellations{0};
    failed.set_cancel(&cancellations,count_cancel);
    assert(failed.observe({1000,1200,base,utc,utc+200,true})==timing::Status::ok);
    failed.event(candidate(0));
    bool threw=false;
    try { (void)failed.poll(); }
    catch (const std::runtime_error&) { threw=true; }
    assert(threw && cancellations.load()==1);
    const auto failure=failed.progress();
    assert(!failure.timing_qualified);
    assert(failure.support_profile_bound && failure.session.profile_prepared==1);
    assert(failure.session.support_unavailable==1 && failure.session.support_unhealthy);
    assert(!failure.session.queued && !failure.session.support_derivation_inflight);
    failed.event(candidate(1));
    failed.detach_cancel();
    bool finish_threw=false;
    try { (void)failed.finish_after_rf_stopped(); }
    catch (const std::runtime_error&) { finish_threw=true; }
    assert(finish_threw);
}

void unused_external_dispatch(void*,std::size_t,void*,void (*)(void*,std::size_t)) {
    assert(false);
}

void owned_tracking_execution_lifecycle_and_conflict() {
    auto value=config(); value.analysis_workers=2U;
    value.publication_interval_ns=1'000'000'000ULL;
    {
        Analysis analysis(std::move(value));
        assert(analysis.observe({1000,1200,base,utc,utc+200,true})==timing::Status::ok);
        for (unsigned i=0;i<8;++i) analysis.event(candidate(i));
        assert(analysis.observe({8000001000ULL,8000001200ULL,base+20000000,
            utc+8000000000LL,utc+8000000200LL,true})==timing::Status::ok);
        analysis.detach_cancel();
        const auto result=analysis.finish_after_rf_stopped();
        assert(result.accepted_candidates==8U && !result.search_failures);
    }

    value=config(); value.analysis_workers=2U;
    value.online.tracking_execution={nullptr,unused_external_dispatch};
    bool threw=false;
    try { Analysis analysis(std::move(value)); }
    catch (const std::invalid_argument&) { threw=true; }
    assert(threw);

    value=config(); value.analysis_workers=2U;
    value.online.scoring_execution={2U,nullptr,unused_external_dispatch};
    threw=false;
    try { Analysis analysis(std::move(value)); }
    catch (const std::invalid_argument&) { threw=true; }
    assert(threw);

    value=config(); value.analysis_workers=2U;
    value.online.scoring_execution.workers=3U;
    threw=false;
    try { Analysis analysis(std::move(value)); }
    catch (const std::invalid_argument&) { threw=true; }
    assert(threw);

    value=config(); value.analysis_workers=2U;
    int external_context=0;
    value.online.scoring_execution.context=&external_context;
    threw=false;
    try { Analysis analysis(std::move(value)); }
    catch (const std::invalid_argument&) { threw=true; }
    assert(threw);

    value=config(); value.analysis_workers=1U;
    value.online.tracking_execution={nullptr,unused_external_dispatch};
    value.online.scoring_execution={2U,nullptr,unused_external_dispatch};
    Analysis compatible(std::move(value));
    compatible.detach_cancel();
    (void)compatible.finish_after_rf_stopped();
}

void full_history_profile_constructs_explicitly() {
    auto value=config();
    value.online.history_window_ns=600'000'000'000LL;
    value.online.maximum_knots=96;
    value.online.maximum_orbit_bytes=96U*sizeof(leo_orbit_state)*2U;
    value.maximum_detector_latency_ns=60'000'000'000ULL;
    value.orbit_knot_step_s=10;
    value.orbit_knot_count=96;
    Analysis analysis(std::move(value));
    bool rejected=false;
    try { (void)analysis.poll(); } catch (const std::logic_error&) { rejected=true; }
    assert(rejected);
    analysis.detach_cancel();
    const auto summary=analysis.finish_after_rf_stopped();
    assert(!summary.publications && !summary.timing_failures);
}

void caller_driven_search_survives_publication() {
    auto value=config();
    value.caller_driven=true;
    value.online.publication_search_policy=online::PublicationSearchPolicy::pin_started_snapshot;
    value.publication_interval_ns=1'000'000'000ULL;
    value.search.policy.level_count=2;
    value.search.policy.levels_km[1]=1;
    value.search.policy.budget_points=5;
    Analysis interleaved(value), control(value), stopped(value), expired(value);
    auto seed=[](Analysis& analysis) {
        assert(analysis.observe({1000,1200,base,utc,utc+200,true})==timing::Status::ok);
        for (unsigned i=0;i<8;++i) analysis.event(candidate(i));
        assert(analysis.observe({8000001000ULL,8000001200ULL,base+20000000,
            utc+8000000000LL,utc+8000000200LL,true})==timing::Status::ok);
    };
    auto append=[](Analysis& analysis) {
        analysis.event(candidate(8));
        assert(analysis.observe({9000001000ULL,9000001200ULL,base+22500000,
            utc+9000000000LL,utc+9000000200LL,true})==timing::Status::ok);
    };
    auto complete=[](Analysis& analysis,std::uint64_t count) {
        Summary result;
        for (unsigned iteration=0;iteration<20;++iteration) {
            result=analysis.poll();
            if (result.searches_complete==count) return result;
        }
        throw std::runtime_error("bounded caller-driven search made no progress");
    };
    seed(interleaved); seed(control);
    const auto initial=interleaved.poll();
    assert(initial.searches_started==1 && !initial.searches_complete);
    assert(initial.last_search.evaluated_points==1);
    const auto first_control=complete(control,1);
    append(interleaved);
    const auto newer=interleaved.poll();
    assert(newer.publications==2 && newer.publications_with_tracks==2);
    assert(newer.searches_started==1 && newer.search_pending);
    assert(newer.snapshot_generation>newer.last_search.snapshot_generation);
    assert(newer.last_search.snapshot_generation==initial.snapshot_generation);
    const auto first=complete(interleaved,1);
    assert(first.last_search.snapshot_generation==initial.snapshot_generation);
    assert(first.last_search.evaluated_points==5);
    assert(first.last_search.incumbent.weighted_mse_hz2==
        first_control.last_search.incumbent.weighted_mse_hz2);
    const auto latest=complete(interleaved,2);
    append(control);
    const auto latest_control=complete(control,2);
    assert(!latest.search_pending && latest.searches_started==2);
    assert(latest.last_search.snapshot_generation==latest.snapshot_generation);
    assert(latest.last_search.evaluated_points==5 && latest.result_source_age_count==2);
    assert(latest.last_search.incumbent.weighted_mse_hz2==
        latest_control.last_search.incumbent.weighted_mse_hz2);
    assert(latest.last_search.incumbent.east_km==latest_control.last_search.incumbent.east_km);
    assert(latest.last_search.incumbent.north_km==latest_control.last_search.incumbent.north_km);
    assert(!latest.search_failures && !latest.searches_stale);
    assert(interleaved.progress().searches_complete==2);
    interleaved.detach_cancel(); control.detach_cancel();
    assert(interleaved.finish_after_rf_stopped().searches_complete==2);
    (void)control.finish_after_rf_stopped();
    bool rejected=false;
    try { (void)interleaved.poll(); } catch (const std::logic_error&) { rejected=true; }
    assert(rejected);

    // Shutdown exposes unfinished work instead of claiming that the latest
    // snapshot was searched simply because an older search has an incumbent.
    seed(stopped); (void)stopped.poll(); append(stopped); (void)stopped.poll();
    stopped.detach_cancel();
    const auto incomplete=stopped.finish_after_rf_stopped();
    assert(incomplete.search_pending && incomplete.searches_complete==0);
    assert(incomplete.last_search.state==online::SearchState::running_unconverged);
    assert(incomplete.last_search.snapshot_generation<incomplete.snapshot_generation);

    seed(expired); (void)expired.poll(); append(expired); (void)expired.poll();
    assert(expired.observe({20000001000ULL,20000001200ULL,base+50000000,
        utc+20000000000LL,utc+20000000200LL,true})==timing::Status::ok);
    (void)expired.poll();
    const auto stale=expired.poll();
    assert(stale.last_search.state==online::SearchState::stale);
    assert(stale.searches_stale>=1 && !stale.search_pending && !stale.search_failures);
    expired.detach_cancel(); (void)expired.finish_after_rf_stopped();
}

struct BlockingCancel {
    std::mutex mutex; std::condition_variable changed;
    bool entered{},release{},destroyed{};
};
int blocking_cancel(void* context) {
    auto& value=*static_cast<BlockingCancel*>(context);
    std::unique_lock<std::mutex> lock(value.mutex);
    assert(!value.destroyed); value.entered=true; value.changed.notify_all();
    value.changed.wait(lock,[&] { return value.release; });
    assert(!value.destroyed); return 0;
}

void detach_waits_for_cancel() {
    Analysis analysis(config()); BlockingCancel state;
    analysis.set_cancel(&state,blocking_cancel);
    leo_scanner_event drop{}; drop.kind=LEO_SCANNER_QUEUE_DROP;
    std::thread event_thread([&] { analysis.event(drop); });
    {
        std::unique_lock<std::mutex> lock(state.mutex);
        state.changed.wait(lock,[&] { return state.entered; });
    }
    std::atomic<bool> detached{false};
    std::thread detach_thread([&] { analysis.detach_cancel(); detached=true; });
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
    assert(!detached.load());
    {
        std::lock_guard<std::mutex> lock(state.mutex); state.release=true;
    }
    state.changed.notify_all(); event_thread.join(); detach_thread.join();
    {
        std::lock_guard<std::mutex> lock(state.mutex); state.destroyed=true;
    }
    const auto result=analysis.finish_after_rf_stopped();
    assert(detached.load() && result.scanner_queue_drops==1 && !result.timing_qualified);
}

void detector_failure_is_fail_closed() {
    Analysis analysis(config()); analysis.detach_cancel();
    leo_scanner_event failure{}; failure.kind=LEO_SCANNER_DETECTOR_FAILURE;
    const auto now=static_cast<std::uint64_t>(std::chrono::duration_cast<
        std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count());
    failure.detector_enqueued_monotonic_ns=now;
    failure.detector_started_monotonic_ns=now;
    failure.detector_finished_monotonic_ns=now;
    analysis.event(failure);
    const auto result=analysis.finish_after_rf_stopped();
    assert(result.detector_failures==1 && !result.timing_qualified);
}

void caller_owner_overlap_and_failure_are_explicit() {
    auto value=config(); value.caller_driven=true;
    value.catalogue.front().line1[0]='X';
    Analysis analysis(std::move(value)); BlockingCancel state;
    analysis.set_cancel(&state,blocking_cancel);
    assert(analysis.observe({1000,1200,base,utc,utc+200,true})==timing::Status::ok);
    for (unsigned i=0;i<8;++i) analysis.event(candidate(i));
    bool failed=false;
    std::thread owner([&] {
        try { (void)analysis.poll(); }
        catch (const std::runtime_error&) { failed=true; }
    });
    {
        std::unique_lock<std::mutex> lock(state.mutex);
        assert(state.changed.wait_for(lock,std::chrono::seconds(5),[&] { return state.entered; }));
    }
    bool poll_rejected=false,finish_rejected=false;
    try { (void)analysis.poll(); } catch (const std::logic_error&) { poll_rejected=true; }
    try { (void)analysis.finish_after_rf_stopped(); }
    catch (const std::logic_error&) { finish_rejected=true; }
    assert(poll_rejected && finish_rejected && !analysis.progress().timing_qualified);
    {
        std::lock_guard<std::mutex> lock(state.mutex); state.release=true;
    }
    state.changed.notify_all(); owner.join();
    assert(failed);
    analysis.detach_cancel();
    bool finish_failed=false;
    try { (void)analysis.finish_after_rf_stopped(); }
    catch (const std::runtime_error&) { finish_failed=true; }
    assert(finish_failed);
}

void consumed_duplicate_is_visible() {
    Analysis analysis(config());
    assert(analysis.observe({1000,1200,base,utc,utc+200,true})==timing::Status::ok);
    const auto event=candidate(0);
    analysis.event(event); analysis.event(event);
    assert(analysis.observe({1000001000ULL,1000001200ULL,base+2500000,
        utc+1000000000LL,utc+1000000200LL,true})==timing::Status::ok);
    analysis.detach_cancel();
    const auto result=analysis.finish_after_rf_stopped();
    assert(result.session.rejected==1);
}

void delayed_candidate_after_result_is_fail_closed() {
    auto value=config(); value.maximum_detector_latency_ns=1'000'000;
    Analysis analysis(std::move(value));
    leo_scanner_event result{}; result.kind=LEO_SCANNER_DETECTOR_RESULT;
    const auto now=static_cast<std::uint64_t>(std::chrono::duration_cast<
        std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count());
    result.detector_enqueued_monotonic_ns=now;
    result.detector_started_monotonic_ns=now;
    result.detector_finished_monotonic_ns=now;
    analysis.event(result);
    assert(analysis.observe({1000,1200,base,utc,utc+200,true})==timing::Status::ok);
    std::this_thread::sleep_for(std::chrono::milliseconds(2));
    auto delayed=candidate(0);
    delayed.detector_enqueued_monotonic_ns=now;
    delayed.detector_started_monotonic_ns=now;
    delayed.detector_finished_monotonic_ns=now;
    analysis.event(delayed); analysis.detach_cancel();
    const auto summary=analysis.finish_after_rf_stopped();
    assert(summary.detector_latency_violations==1 && !summary.timing_qualified);
}

void history_capacity_loss_is_visible() {
    auto value=config(); value.online.maximum_history_observations=1;
    Analysis analysis(std::move(value));
    assert(analysis.observe({1000,1200,base,utc,utc+200,true})==timing::Status::ok);
    analysis.event(candidate(0)); analysis.event(candidate(1));
    assert(analysis.observe({1000001000ULL,1000001200ULL,base+2500000,
        utc+1000000000LL,utc+1000000200LL,true})==timing::Status::ok);
    analysis.detach_cancel();
    const auto summary=analysis.finish_after_rf_stopped();
    assert(summary.session.history_capacity_evictions==1);
}

void missing_detector_timing_is_fail_closed() {
    Analysis analysis(config());
    leo_scanner_event result{}; result.kind=LEO_SCANNER_DETECTOR_RESULT;
    analysis.event(result); analysis.detach_cancel();
    const auto summary=analysis.finish_after_rf_stopped();
    assert(summary.detector_latency_violations==1 && !summary.timing_qualified);
}
} // namespace

int main() {
    invalid_construction_does_not_terminate(); full_history_profile_constructs_explicitly();
    optional_support_profile_binding_and_failure();
    owned_tracking_execution_lifecycle_and_conflict();
    detach_waits_for_cancel(); caller_driven_search_survives_publication();
    detector_failure_is_fail_closed(); caller_owner_overlap_and_failure_are_explicit();
    consumed_duplicate_is_visible();
    delayed_candidate_after_result_is_fail_closed(); history_capacity_loss_is_visible();
    missing_detector_timing_is_fail_closed(); fake_e2e();
    exact_score_cache_stats_are_owner_published();
}
