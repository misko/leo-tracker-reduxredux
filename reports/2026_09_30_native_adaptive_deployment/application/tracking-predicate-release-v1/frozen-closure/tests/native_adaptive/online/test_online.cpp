#include "online.hpp"

#include <algorithm>
#include <atomic>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {
using leo::adaptive::Observation;
using leo::adaptive::online::Config;
using leo::adaptive::online::Coordinator;
using leo::adaptive::online::OrbitBuild;
using leo::adaptive::online::PublicationSearchPolicy;
using leo::adaptive::online::SearchConfig;
using leo::adaptive::online::SearchState;
using leo::adaptive::online::SessionAuthority;
using leo::adaptive::online::Status;

void require(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}

std::string identity(int value) {
    std::ostringstream output;
    output << "sha256:" << std::hex << std::setfill('0') << std::setw(64) << value;
    return output.str();
}

Observation observation(int index, std::uint64_t generation, std::int64_t base) {
    constexpr double spacing = 1.0 / 4.4e-6;
    const std::int64_t center = base + static_cast<std::int64_t>(index) * 600'000'000LL;
    const double time = 0.6 * index;
    const int alias = index % 3 - 1;
    return Observation{
        identity(index + 1), identity(index + 101), generation,
        static_cast<std::uint64_t>(index + 1), 0, 1, static_cast<std::uint32_t>(index), false,
        11'200'000'000.0, 31'000.0 + 1'250.0 * time + alias * spacing,
        1.25, 0.25, 1.0,
        center - 20'000'000, center, center + 20'000'000,
        400.0, 1.0e-5, 0.0,
    };
}

std::vector<leo_tle_record> read_tles(const std::string& path, std::size_t limit) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open TLE fixture");
    std::size_t count = 0;
    input >> count;
    input.ignore(1024, '\n');
    count = std::min(count, limit);
    std::vector<leo_tle_record> records(count);
    for (std::size_t index = 0; index < count; ++index) {
        std::string line1;
        std::string line2;
        std::getline(input, line1);
        std::getline(input, line2);
        if (line1.size() != 69 || line2.size() != 69)
            throw std::runtime_error("invalid TLE fixture");
        records[index].satellite_id = static_cast<std::int32_t>(index + 1);
        std::memcpy(records[index].line1, line1.data(), 69);
        std::memcpy(records[index].line2, line2.data(), 69);
        records[index].line1[69] = '\0';
        records[index].line2[69] = '\0';
    }
    return records;
}

SearchConfig search_config() {
    SearchConfig value{};
    value.origin_latitude_deg = 38.5;
    value.origin_longitude_deg = -121.5;
    value.score = leo_score_default_config();
    value.policy.radius_km = 50.0;
    value.policy.region_size_km = 100.0;
    value.policy.level_count = 2;
    value.policy.levels_km[0] = 100.0;
    value.policy.levels_km[1] = 50.0;
    value.policy.budget_points = 5;
    return value;
}

void require_same_search_result(
    const leo::adaptive::online::SearchResult& left,
    const leo::adaptive::online::SearchResult& right) {
    require(left.state==right.state && left.status==right.status &&
            left.search_generation==right.search_generation &&
            left.snapshot_generation==right.snapshot_generation &&
            left.orbit_generation==right.orbit_generation &&
            left.evaluated_points==right.evaluated_points &&
            left.deferred_cells==right.deferred_cells &&
            left.required_points==right.required_points &&
            left.has_incumbent==right.has_incumbent &&
            left.incumbent.east_km==right.incumbent.east_km &&
            left.incumbent.north_km==right.incumbent.north_km &&
            left.incumbent.weighted_mse_hz2==right.incumbent.weighted_mse_hz2 &&
            left.incumbent_residual_rmse_hz==right.incumbent_residual_rmse_hz &&
            left.incumbent_matched_tracks==right.incumbent_matched_tracks &&
            left.incumbent_unmatched_tracks==right.incumbent_unmatched_tracks &&
            left.incumbent_evaluated_satellite_tracks==
                right.incumbent_evaluated_satellite_tracks &&
            left.incumbent_rejected_satellite_tracks==
                right.incumbent_rejected_satellite_tracks,
            "resumable search result differs from uninterrupted reference");
}

void require_same_search_science(
    const leo::adaptive::online::SearchResult& left,
    const leo::adaptive::online::SearchResult& right) {
    require(left.state==right.state && left.status==right.status &&
            left.evaluated_points==right.evaluated_points &&
            left.deferred_cells==right.deferred_cells &&
            left.required_points==right.required_points &&
            left.has_incumbent==right.has_incumbent &&
            left.incumbent.east_km==right.incumbent.east_km &&
            left.incumbent.north_km==right.incumbent.north_km &&
            left.incumbent.weighted_mse_hz2==right.incumbent.weighted_mse_hz2 &&
            left.incumbent_residual_rmse_hz==right.incumbent_residual_rmse_hz &&
            left.incumbent_matched_tracks==right.incumbent_matched_tracks &&
            left.incumbent_unmatched_tracks==right.incumbent_unmatched_tracks &&
            left.incumbent_evaluated_satellite_tracks==
                right.incumbent_evaluated_satellite_tracks &&
            left.incumbent_rejected_satellite_tracks==
                right.incumbent_rejected_satellite_tracks,
            "scoring execution changed search science");
}

Config small_config(PublicationSearchPolicy policy) {
    Config config;
    config.maximum_satellites=8;
    config.maximum_knots=64;
    config.maximum_orbit_bytes=8U*64U*sizeof(leo_orbit_state)*2U;
    config.publication_search_policy=policy;
    return config;
}

struct ScoringDispatch {
    enum class Mode { normal, throw_after_drain, duplicate_first, skip_last };
    std::atomic<unsigned> calls{};
    Mode mode{Mode::normal};

    static void run(void* opaque, std::size_t count, void* context,
                    void (*task)(void*, std::size_t)) {
        auto& dispatch=*static_cast<ScoringDispatch*>(opaque);
        ++dispatch.calls;
        std::vector<std::thread> threads;
        threads.reserve(count);
        const std::size_t limit=dispatch.mode==Mode::skip_last && count ? count-1 : count;
        for(std::size_t index=0;index<limit;++index)
            threads.emplace_back([=] { task(context,index); });
        for(auto& thread:threads) thread.join();
        if(dispatch.mode==Mode::duplicate_first && count) task(context,0);
        if(dispatch.mode==Mode::throw_after_drain)
            throw std::runtime_error("injected scoring dispatch failure");
    }
};

void prepare_search_fixture(
    Coordinator& coordinator,
    const std::string& tle_path,
    std::uint64_t stream_generation,
    std::int64_t base,
    std::shared_ptr<const leo::adaptive::online::Snapshot>* snapshot) {
    require(coordinator.replace_stream_generation(stream_generation)==Status::ok,
            "search fixture stream generation failed");
    std::int64_t watermark=0;
    for(int index=0;index<9;++index) {
        const auto value=observation(index,stream_generation,base);
        watermark=value.support_end_utc_ns;
        require(coordinator.ingest(value,watermark).status==Status::ok,
                "search fixture ingest failed");
    }
    require(coordinator.publish(watermark,snapshot)==Status::ok && *snapshot,
            "search fixture publication failed");
    OrbitBuild orbit{};
    orbit.generation=1;
    orbit.start_utc_ns=base;
    orbit.knot_start_s=-10.0;
    orbit.knot_step_s=1.0;
    orbit.knot_count=32;
    orbit.records=read_tles(tle_path,8);
    require(coordinator.replace_orbit(orbit)==Status::ok,
            "search fixture orbit failed");
}

void test_causal_snapshots_and_search(const std::string& tle_path) {
    constexpr std::int64_t base = 1'790'557'997'299'661'326LL;
    Config config;
    config.maximum_satellites = 8;
    config.maximum_knots = 64;
    config.maximum_orbit_bytes = 8U * 64U * sizeof(leo_orbit_state) * 2U;
    Coordinator coordinator(config, SessionAuthority{
        "online-unit", identity(900), base});
    require(coordinator.replace_stream_generation(7) == Status::ok,
            "stream generation was not installed");

    Observation future = observation(0, 7, base);
    require(coordinator.ingest(future, future.support_end_utc_ns - 1).status ==
                Status::future_observation,
            "future observation was accepted");
    Observation stale = future;
    stale.generation = 6;
    require(coordinator.ingest(stale, stale.support_end_utc_ns).status ==
                Status::stale_generation,
            "stale observation generation was accepted");

    std::vector<leo::adaptive::tracking::Candidate> reference_input;
    std::int64_t watermark = 0;
    for (int index = 0; index < 9; ++index) {
        const Observation value = observation(index, 7, base);
        watermark = value.support_end_utc_ns;
        require(coordinator.ingest(value, watermark).status == Status::ok,
                "valid observation was rejected");
        reference_input.push_back(leo::adaptive::tracking::Candidate{
            value.candidate_id, value.source_group_id, 0, 1, "lower", value.actual_rf_hz,
            value.support_start_utc_ns, value.support_center_utc_ns,
            value.support_end_utc_ns, value.measured_cfo_hz,
            value.exact_score, value.control_score, value.margin});
    }
    require(coordinator.ingest(observation(8, 7, base), watermark).status == Status::duplicate,
            "duplicate observation was accepted");

    std::shared_ptr<const leo::adaptive::online::Snapshot> first;
    require(coordinator.publish(watermark, &first) == Status::ok && first,
            "causal prefix publication failed");
    require(first->retained_observation_count == 9 &&
                first->tracking_result.tracks.size() == 1 &&
                first->location_tracks.records.size() == 1,
            "published prefix contents differ");
    const auto expected = leo::adaptive::tracking::reconstruct(reference_input);
    require(leo::adaptive::online::compare_reference(*first, expected).exact,
            "same-prefix reference differs");

    leo::adaptive::online::SearchResult started{};
    require(coordinator.begin_search(first->generation, search_config(), &started) ==
                Status::no_orbit,
            "search began without an orbit snapshot");

    OrbitBuild orbit{};
    orbit.generation = 1;
    orbit.start_utc_ns = base;
    orbit.knot_start_s = -10.0;
    orbit.knot_step_s = 1.0;
    orbit.knot_count = 32;
    orbit.records = read_tles(tle_path, 8);
    require(coordinator.replace_orbit(orbit) == Status::ok, "TLE orbit build failed");
    require(coordinator.begin_search(first->generation, search_config(), &started) == Status::ok,
            "location search did not begin");
    auto partial = coordinator.resume_search(1);
    require(partial.state == SearchState::running_unconverged &&
                partial.evaluated_points == 1 && partial.required_points == 4 &&
                partial.has_incumbent,
            "point budget did not return an explicit resumable result");

    // Raw append is coalesced and must not invalidate this immutable-prefix search.
    Observation later = observation(20, 7, base);
    require(coordinator.ingest(later, later.support_end_utc_ns).status == Status::ok,
            "coalesced append failed");
    auto complete = coordinator.resume_search(4);
    require(complete.state == SearchState::complete && complete.evaluated_points == 5,
            "resumed native search did not converge");

    require(coordinator.begin_search(first->generation, search_config(), &started) == Status::ok,
            "second search did not begin");
    require(coordinator.cancel_search().state == SearchState::cancelled,
            "search cancellation was not explicit");

    require(coordinator.begin_search(first->generation, search_config(), &started) == Status::ok,
            "staleness search did not begin");
    std::shared_ptr<const leo::adaptive::online::Snapshot> second;
    require(coordinator.publish(later.support_end_utc_ns, &second) == Status::ok &&
                second->generation != first->generation,
            "replacement publication failed");
    require(coordinator.resume_search(5).state == SearchState::stale,
            "published generation did not invalidate old search");
    require(first->tracking_result.tracks.size() == 1,
            "old immutable snapshot changed after replacement");

    require(coordinator.begin_search(second->generation, search_config(), &started) == Status::ok,
            "orbit staleness search did not begin");
    orbit.generation = 2;
    require(coordinator.replace_orbit(orbit) == Status::ok,
            "replacement TLE generation failed");
    require(coordinator.resume_search(5).state == SearchState::stale,
            "TLE replacement did not invalidate search");
    std::shared_ptr<const leo::adaptive::online::Snapshot> regressed;
    require(coordinator.publish(watermark, &regressed) == Status::invalid,
            "publication watermark regressed");
    require(coordinator.begin_search(second->generation, search_config(), &started) == Status::ok,
            "expiry search did not begin");
    require(coordinator.advance_watermark(
                second->watermark_utc_ns + config.history_window_ns + 1) == Status::ok,
            "watermark advance failed");
    require(coordinator.resume_search(5).state == SearchState::stale &&
                !coordinator.current_snapshot(),
            "expired published evidence remained current");
}

void test_pinned_snapshot_search(const std::string& tle_path) {
    constexpr std::int64_t base=1'790'557'997'299'661'326LL;
    const auto authority=SessionAuthority{"pinned-unit",identity(903),base};

    Coordinator uninterrupted(
        small_config(PublicationSearchPolicy::invalidate_on_publish),authority);
    std::shared_ptr<const leo::adaptive::online::Snapshot> reference_snapshot;
    prepare_search_fixture(uninterrupted,tle_path,7,base,&reference_snapshot);
    leo::adaptive::online::SearchResult started{};
    require(uninterrupted.begin_search(
                reference_snapshot->generation,search_config(),&started)==Status::ok,
            "uninterrupted search did not begin");
    const auto reference=uninterrupted.resume_search(5);
    require(reference.state==SearchState::complete && reference.evaluated_points==5,
            "uninterrupted search did not complete");

    Coordinator sliced(
        small_config(PublicationSearchPolicy::pin_started_snapshot),authority);
    std::shared_ptr<const leo::adaptive::online::Snapshot> first;
    prepare_search_fixture(sliced,tle_path,7,base,&first);
    require(sliced.begin_search(first->generation,search_config(),&started)==Status::ok,
            "pinned search did not begin");
    auto result=sliced.resume_search(1);
    require(result.state==SearchState::running_unconverged &&
                result.evaluated_points==1 && result.required_points==4,
            "first bounded search slice did not expose the refinement batch");

    const auto later=observation(20,7,base);
    require(sliced.ingest(later,later.support_end_utc_ns).status==Status::ok,
            "pinned search append failed");
    std::shared_ptr<const leo::adaptive::online::Snapshot> second;
    require(sliced.publish(later.support_end_utc_ns,&second)==Status::ok &&
                second->generation!=first->generation,
            "pinned search replacement publication failed");
    result=sliced.resume_search(1);
    require(result.state==SearchState::running_unconverged &&
                result.evaluated_points==2 && result.required_points==3,
            "partial native batch did not advance by one point");

    const auto newest=observation(21,7,base);
    require(sliced.ingest(newest,newest.support_end_utc_ns).status==Status::ok,
            "second pinned search append failed");
    std::shared_ptr<const leo::adaptive::online::Snapshot> third;
    require(sliced.publish(newest.support_end_utc_ns,&third)==Status::ok &&
                third->generation!=second->generation,
            "second pinned replacement publication failed");
    while(result.state==SearchState::running_unconverged) {
        const auto before=result.evaluated_points;
        result=sliced.resume_search(1);
        require(result.evaluated_points==before+1,
                "bounded one-point slice did not make deterministic progress");
    }
    require(result.state==SearchState::complete &&
                result.snapshot_generation==first->generation &&
                sliced.current_snapshot()==third,
            "pinned search lost snapshot provenance or newest publication");
    require_same_search_result(reference,result);
    const auto completed_again=sliced.resume_search(1);
    require_same_search_result(result,completed_again);
    require(sliced.begin_search(first->generation,search_config(),&started)==Status::invalid,
            "obsolete snapshot was accepted for a new search");
    require(sliced.begin_search(third->generation,search_config(),&started)==Status::ok &&
                sliced.resume_search(1).evaluated_points==1,
            "newest snapshot search did not start after pinned completion");
    const auto partial_before_cancel=sliced.resume_search(1);
    require(partial_before_cancel.state==SearchState::running_unconverged &&
                partial_before_cancel.evaluated_points==2,
            "cancel test did not enter a partial native batch");
    const auto cancelled=sliced.cancel_search();
    require(cancelled.state==SearchState::cancelled &&
                cancelled.evaluated_points==partial_before_cancel.evaluated_points &&
                cancelled.has_incumbent &&
                cancelled.incumbent.weighted_mse_hz2==
                    partial_before_cancel.incumbent.weighted_mse_hz2,
            "mid-batch cancellation lost truthful partial progress");
    const auto cancelled_again=sliced.resume_search(1);
    require(cancelled_again.state==cancelled.state &&
                cancelled_again.evaluated_points==cancelled.evaluated_points &&
                cancelled_again.incumbent.weighted_mse_hz2==
                    cancelled.incumbent.weighted_mse_hz2,
            "resume after cancellation changed the final result");

    Coordinator expiring(
        small_config(PublicationSearchPolicy::pin_started_snapshot),authority);
    std::shared_ptr<const leo::adaptive::online::Snapshot> expiring_first;
    prepare_search_fixture(expiring,tle_path,7,base,&expiring_first);
    require(expiring.begin_search(
                expiring_first->generation,search_config(),&started)==Status::ok &&
                expiring.resume_search(1).state==SearchState::running_unconverged,
            "expiry search did not start");
    require(expiring.ingest(later,later.support_end_utc_ns).status==Status::ok,
            "expiry append failed");
    std::shared_ptr<const leo::adaptive::online::Snapshot> expiring_second;
    require(expiring.publish(later.support_end_utc_ns,&expiring_second)==Status::ok,
            "expiry replacement publication failed");
    require(expiring.advance_watermark(
                expiring_first->watermark_utc_ns+
                small_config(PublicationSearchPolicy::pin_started_snapshot).history_window_ns+1)==
                Status::ok,
            "pinned expiry watermark failed");
    const auto expired=expiring.resume_search(1);
    require(expired.state==SearchState::stale &&
                expired.snapshot_generation==expiring_first->generation &&
                expiring.current_snapshot()==expiring_second,
            "expired pinned search did not fail stale while preserving newer current snapshot");

    Coordinator stream_changed(
        small_config(PublicationSearchPolicy::pin_started_snapshot),authority);
    std::shared_ptr<const leo::adaptive::online::Snapshot> stream_snapshot;
    prepare_search_fixture(stream_changed,tle_path,7,base,&stream_snapshot);
    require(stream_changed.begin_search(
                stream_snapshot->generation,search_config(),&started)==Status::ok &&
                stream_changed.resume_search(1).state==SearchState::running_unconverged,
            "stream replacement search did not start");
    require(stream_changed.replace_stream_generation(8)==Status::ok &&
                stream_changed.resume_search(1).state==SearchState::stale,
            "stream replacement did not stale pinned search");

    Coordinator orbit_changed(
        small_config(PublicationSearchPolicy::pin_started_snapshot),authority);
    std::shared_ptr<const leo::adaptive::online::Snapshot> orbit_snapshot;
    prepare_search_fixture(orbit_changed,tle_path,7,base,&orbit_snapshot);
    require(orbit_changed.begin_search(
                orbit_snapshot->generation,search_config(),&started)==Status::ok &&
                orbit_changed.resume_search(1).state==SearchState::running_unconverged,
            "orbit replacement search did not start");
    OrbitBuild replacement{};
    replacement.generation=2;
    replacement.start_utc_ns=base;
    replacement.knot_start_s=-10.0;
    replacement.knot_step_s=1.0;
    replacement.knot_count=32;
    replacement.records=read_tles(tle_path,8);
    require(orbit_changed.replace_orbit(replacement)==Status::ok &&
                orbit_changed.resume_search(1).state==SearchState::stale,
            "orbit replacement did not stale pinned search");

    auto invalid_config=small_config(PublicationSearchPolicy::invalidate_on_publish);
    invalid_config.publication_search_policy=static_cast<PublicationSearchPolicy>(999);
    bool rejected=false;
    try {
        Coordinator invalid(invalid_config,authority);
    } catch(const std::invalid_argument&) {
        rejected=true;
    }
    require(rejected,"unknown publication search policy was accepted");
}

void test_execution_failure_preserves_publication() {
    constexpr std::int64_t base=1'790'557'997'299'661'326LL;
    struct Dispatch { unsigned fail=0;unsigned calls=0; } dispatch;
    auto config=small_config(PublicationSearchPolicy::invalidate_on_publish);
    config.tracking_execution={&dispatch,
        [](void* opaque,std::size_t count,void* context,void (*task)(void*,std::size_t)) {
            auto& state=*static_cast<Dispatch*>(opaque);++state.calls;
            if(state.fail==1) throw std::runtime_error("execution unavailable");
            if(state.fail==2) throw std::invalid_argument("executor rejected dispatch");
            for(std::size_t i=count;i>0;--i) task(context,i-1);
        }};
    Coordinator coordinator(config,{"execution",identity(999),base});
    require(coordinator.replace_stream_generation(1)==Status::ok,"execution generation");
    std::int64_t watermark=0;
    for(int i=0;i<9;++i) {
        const auto value=observation(i,1,base);watermark=value.support_end_utc_ns;
        require(coordinator.ingest(value,watermark).status==Status::ok,"execution ingest");
    }
    std::shared_ptr<const leo::adaptive::online::Snapshot> first,next;
    require(coordinator.publish(watermark,&first)==Status::ok && first,"execution publication");
    const auto added=observation(9,1,base);watermark=added.support_end_utc_ns;
    require(coordinator.ingest(added,watermark).status==Status::ok,"execution extra ingest");
    dispatch.fail=1;
    require(coordinator.publish(watermark,&next)==Status::error && !next &&
        coordinator.current_snapshot()==first,"failed dispatch changed publication");
    dispatch.fail=2;
    require(coordinator.publish(watermark,&next)==Status::error && !next &&
        coordinator.current_snapshot()==first,"dispatch argument error changed publication");
    dispatch.fail=0;
    require(coordinator.publish(watermark,&next)==Status::ok && next &&
        next->generation==first->generation+1 && dispatch.calls==4,
        "dispatch recovery lost publication generation");
}

void test_scoring_execution(const std::string& tle_path) {
    constexpr std::int64_t base=1'790'557'997'299'661'326LL;
    const auto authority=SessionAuthority{"score-execution",identity(997),base};
    auto run_search=[&](std::uint32_t workers,ScoringDispatch* dispatch) {
        auto config=small_config(PublicationSearchPolicy::pin_started_snapshot);
        config.scoring_execution={workers,dispatch,
            workers==1 ? nullptr : &ScoringDispatch::run};
        Coordinator coordinator(config,authority);
        std::shared_ptr<const leo::adaptive::online::Snapshot> snapshot;
        prepare_search_fixture(coordinator,tle_path,7,base,&snapshot);
        leo::adaptive::online::SearchResult started{};
        require(coordinator.begin_search(
                    snapshot->generation,search_config(),&started)==Status::ok,
                "scoring execution search did not begin");
        const auto result=coordinator.resume_search(5);
        require(result.state==SearchState::complete && result.evaluated_points==5,
                "scoring execution search did not complete");
        return result;
    };

    const auto serial=run_search(1,nullptr);
    for(std::uint32_t workers:{2U,4U}) {
        ScoringDispatch dispatch;
        const auto parallel=run_search(workers,&dispatch);
        require_same_search_result(serial,parallel);
        require(dispatch.calls==5,
                "scoring dispatcher was not called once per evaluated point");
    }

    for(const auto execution:{
            leo::adaptive::online::ScoringExecution{0,nullptr,nullptr},
            leo::adaptive::online::ScoringExecution{5,nullptr,&ScoringDispatch::run},
            leo::adaptive::online::ScoringExecution{2,nullptr,nullptr},
            leo::adaptive::online::ScoringExecution{1,reinterpret_cast<void*>(1),nullptr},
            leo::adaptive::online::ScoringExecution{1,nullptr,&ScoringDispatch::run}}) {
        auto invalid_config=small_config(PublicationSearchPolicy::invalidate_on_publish);
        invalid_config.scoring_execution=execution;
        bool rejected=false;
        try { Coordinator invalid(invalid_config,authority); }
        catch(const std::invalid_argument&) { rejected=true; }
        require(rejected,"invalid scoring execution configuration was accepted");
    }

    auto failure_config=small_config(PublicationSearchPolicy::pin_started_snapshot);
    ScoringDispatch failing;
    failure_config.scoring_execution={2,&failing,&ScoringDispatch::run};
    Coordinator coordinator(failure_config,authority);
    std::shared_ptr<const leo::adaptive::online::Snapshot> snapshot;
    prepare_search_fixture(coordinator,tle_path,7,base,&snapshot);
    leo::adaptive::online::SearchResult started{};
    require(coordinator.begin_search(snapshot->generation,search_config(),&started)==Status::ok,
            "failure scoring search did not begin");
    failing.mode=ScoringDispatch::Mode::throw_after_drain;
    auto failed=coordinator.resume_search(1);
    require(failed.state==SearchState::error && failed.evaluated_points==0 &&
                !failed.has_incumbent,
            "dispatcher failure committed a partial point");
    require(coordinator.begin_search(snapshot->generation,search_config(),&started)==Status::ok,
            "scoring dispatcher did not recover for a new search");
    failing.mode=ScoringDispatch::Mode::duplicate_first;
    failed=coordinator.resume_search(1);
    require(failed.state==SearchState::error && failed.evaluated_points==0 &&
                !failed.has_incumbent,
            "duplicate scoring callback committed a partial point");
    require(coordinator.begin_search(snapshot->generation,search_config(),&started)==Status::ok,
            "scoring dispatcher did not recover after duplicate callback");
    failing.mode=ScoringDispatch::Mode::skip_last;
    failed=coordinator.resume_search(1);
    require(failed.state==SearchState::error && failed.evaluated_points==0 &&
                !failed.has_incumbent,
            "missing scoring callback committed a partial point");
    require(coordinator.begin_search(snapshot->generation,search_config(),&started)==Status::ok,
            "scoring dispatcher did not recover after missing callback");
    failing.mode=ScoringDispatch::Mode::normal;
    require_same_search_science(serial,coordinator.resume_search(5));
}

void test_bounded_history() {
    constexpr std::int64_t base = 1'790'557'997'299'661'326LL;
    Config config;
    config.maximum_history_observations = 3;
    config.history_window_ns = 2'000'000'000LL;
    config.maximum_satellites = 1;
    config.maximum_knots = 2;
    config.maximum_orbit_bytes = 2U * sizeof(leo_orbit_state) * 2U;
    Coordinator coordinator(config, SessionAuthority{"bounded", identity(901), base});
    require(coordinator.replace_stream_generation(1) == Status::ok, "generation failed");
    std::size_t pruned = 0;
    for (int index = 0; index < 5; ++index) {
        const Observation value = observation(index, 1, base);
        const auto receipt = coordinator.ingest(value, value.support_end_utc_ns);
        require(receipt.status == Status::ok, "bounded ingest failed");
        pruned += receipt.pruned_observations;
    }
    require(coordinator.retained_observations() <= 3 && pruned >= 2,
            "history bounds were not enforced");
    // A long window forces count pressure independently of temporal expiry.
    config.history_window_ns = 600'000'000'000LL;
    Coordinator count_limited(config, SessionAuthority{"capacity", identity(902), base});
    require(count_limited.replace_stream_generation(1)==Status::ok,"generation failed");
    for(int index=0;index<5;++index) {
        const auto value=observation(index,1,base);
        require(count_limited.ingest(value,value.support_end_utc_ns).status==Status::ok,
                "capacity ingest failed");
    }
    require(count_limited.history_capacity_evictions()==2,
            "in-window capacity loss was hidden");
    require(count_limited.advance_watermark(base+700'000'000'000LL)==Status::ok &&
            count_limited.retained_observations()==0 &&
            count_limited.history_capacity_evictions()==2,
            "temporal expiry changed capacity telemetry");
    require(count_limited.replace_stream_generation(2)==Status::ok &&
            count_limited.history_capacity_evictions()==0,
            "new generation retained old capacity telemetry");
}
}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: test_online TLES.txt");
        test_causal_snapshots_and_search(argv[1]);
        test_pinned_snapshot_search(argv[1]);
        test_bounded_history();
        test_execution_failure_preserves_publication();
        test_scoring_execution(argv[1]);
        std::cout << "online coordinator unit tests passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
