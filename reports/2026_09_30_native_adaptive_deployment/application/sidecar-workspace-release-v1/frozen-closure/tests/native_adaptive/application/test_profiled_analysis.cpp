#define main leo_portable_paced_analysis_main_not_used
#include "test_paced_analysis.cpp"
#undef main

#include "../../../native/adaptive/runtime/server_compat/server_compat.hpp"

namespace {

using leo::adaptive::pipeline::SupportAuthority;
using leo::adaptive::server_compat::CacheStats;
using leo::adaptive::server_compat::SupportDeriver;

struct ProfiledRun {
    Summary summary;
    CacheStats cache;
    double wall_s{};
};

void observe_exact(Analysis& analysis,const ProjectionSource& authority,
                   std::uint64_t counter) {
    if (analysis.observe(bracket(authority,counter))!=timing::Status::ok)
        throw std::runtime_error("profiled Analysis timing observation failed");
}

ProfiledRun run_profiled(AnalysisConfig config,const ProjectionSource& authority,
                         const std::vector<SavedEvent>& events,std::uint32_t workers) {
    SupportDeriver deriver(leo::adaptive::server_compat::authority_binding());
    config.support_derivation=leo::adaptive::server_compat::derivation_port(deriver);
    config.caller_driven=true;
    config.analysis_workers=workers;
    const auto begun=Clock::now();
    Summary summary;
    {
        Analysis analysis(std::move(config));
        std::uint64_t prior=UINT64_MAX;
        for (std::size_t index=0;index<events.size();) {
            const auto counter=events[index].counter;
            std::size_t end=index+1;
            while (end<events.size() && events[end].counter==counter) ++end;
            const auto window=lattice_counter(authority,counter);
            if (window!=prior) {
                observe_exact(analysis,authority,window);
                prior=window;
            }
            const auto release=lattice_counter(authority,events[index].event.valid_end);
            if (release!=prior) {
                observe_exact(analysis,authority,release);
                prior=release;
            }
            for (;index<end;++index) {
                auto event=events[index].event;
                const auto now=static_cast<std::uint64_t>(std::chrono::duration_cast<
                    std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count());
                event.detector_enqueued_monotonic_ns=now;
                event.detector_started_monotonic_ns=now;
                event.detector_finished_monotonic_ns=now;
                analysis.event(event);
            }
            // Caller-driven polling makes derivation ownership explicit and
            // keeps this compressed historical replay within the bounded queue.
            analysis.poll();
        }
        analysis.detach_cancel();
        summary=analysis.finish_after_rf_stopped();
    }
    return {std::move(summary),deriver.cache_stats(),
        std::chrono::duration<double>(Clock::now()-begun).count()};
}

struct BackgroundRun {
    Run run;
    CacheStats cache;
};

BackgroundRun run_profiled_background(AnalysisConfig config,
                                      const ProjectionSource& authority,
                                      const std::vector<SavedEvent>& events,
                                      std::uint32_t workers,double pace) {
    SupportDeriver deriver(leo::adaptive::server_compat::authority_binding());
    config.support_derivation=leo::adaptive::server_compat::derivation_port(deriver);
    config.analysis_workers=workers;
    auto result=run(config,authority,events,pace,true);
    return {std::move(result),deriver.cache_stats()};
}

Reference finish_reference(const AnalysisConfig& config,online::Coordinator& coordinator,
                           std::int64_t watermark) {
    std::shared_ptr<const online::Snapshot> snapshot;
    if (coordinator.publish(watermark,&snapshot)!=online::Status::ok || !snapshot ||
        snapshot->retained_observation_count!=11747 ||
        snapshot->location_tracks.records.size()!=64)
        throw std::runtime_error("profiled reference publication failed");
    double required_first=std::numeric_limits<double>::infinity();
    double required_last=-std::numeric_limits<double>::infinity();
    for (const auto& track:snapshot->location_tracks.records) {
        required_first=std::min(required_first,
            track.times_s[0]+config.search.score.tau_first_s-config.orbit_knot_step_s);
        required_last=std::max(required_last,
            track.times_s[track.observation_count-1]+config.search.score.tau_last_s+
                config.orbit_knot_step_s);
    }
    online::OrbitBuild orbit{};
    orbit.generation=1;
    orbit.start_utc_ns=config.session.session_start_utc_ns;
    orbit.knot_start_s=std::floor(required_first/config.orbit_knot_step_s)*
        config.orbit_knot_step_s;
    orbit.knot_step_s=config.orbit_knot_step_s;
    orbit.knot_count=config.orbit_knot_count;
    orbit.records=config.catalogue;
    if (required_last>orbit.knot_start_s+(orbit.knot_count-1)*orbit.knot_step_s ||
        coordinator.replace_orbit(orbit)!=online::Status::ok)
        throw std::runtime_error("profiled reference orbit failed");
    online::SearchResult started{};
    if (coordinator.begin_search(snapshot->generation,config.search,&started)!=online::Status::ok)
        throw std::runtime_error("profiled reference search begin failed");
    const auto result=coordinator.resume_search(1);
    if (result.state!=online::SearchState::complete || result.evaluated_points!=1 ||
        !result.has_incumbent)
        throw std::runtime_error("profiled reference search failed");
    return {snapshot->location_tracks.records.size(),result,0.0};
}

struct ProfiledReference {
    Reference result;
    CacheStats cache;
    double wall_s{};
};

ProfiledReference profiled_reference(const AnalysisConfig& config,
                                     const ProjectionSource& authority,
                                     const std::vector<SavedEvent>& events) {
    const auto begun=Clock::now();
    SupportDeriver deriver(leo::adaptive::server_compat::authority_binding());
    const auto port=leo::adaptive::server_compat::derivation_port(deriver);
    timing::Timebase clock(config.timing);
    if (clock.begin(config.authority.generation)!=timing::Status::ok)
        throw std::runtime_error("profiled reference clock failed");
    online::Coordinator coordinator(config.online,config.session);
    if (coordinator.replace_stream_generation(config.authority.generation)!=online::Status::ok)
        throw std::runtime_error("profiled reference generation failed");
    std::uint64_t prior=UINT64_MAX;
    std::int64_t watermark=0;
    std::size_t emitted=0,nonpassing=0;
    for (std::size_t index=0;index<events.size();) {
        const auto counter=events[index].counter;
        std::size_t end=index+1;
        while (end<events.size() && events[end].counter==counter) ++end;
        const auto window=lattice_counter(authority,counter);
        if (window!=prior) {
            if (clock.observe(bracket(authority,window))!=timing::Status::ok)
                throw std::runtime_error("profiled reference window bracket failed");
            prior=window;
        }
        const auto release=lattice_counter(authority,events[index].event.valid_end);
        if (release!=prior) {
            if (clock.observe(bracket(authority,release))!=timing::Status::ok)
                throw std::runtime_error("profiled reference release bracket failed");
            prior=release;
        }
        for (;index<end;++index) {
            Observation observation;
            SupportDerivation support;
            const auto status=ingest::project_event(config.authority,clock,events[index].event,
                port,observation,support);
            if (status==ingest::Status::nonpassing) {
                ++nonpassing;
                continue;
            }
            if (status!=ingest::Status::emitted || !events[index].passing)
                throw std::runtime_error("profiled reference projection status mismatch");
            const auto& original=events[index].projected;
            if (observation.candidate_id!=original.candidate_id ||
                observation.source_group_id!=original.source_group_id ||
                observation.support_start_utc_ns!=original.support_start_utc_ns ||
                observation.support_center_utc_ns!=original.support_center_utc_ns ||
                observation.support_end_utc_ns!=original.support_end_utc_ns)
                throw std::runtime_error("profiled lattice UTC differs from original authority");
            watermark=std::max(watermark,observation.support_end_utc_ns);
            SupportAuthority exact{observation.support_start_utc_ns,
                observation.support_center_utc_ns,observation.support_end_utc_ns,
                support.factorial_moment_lexemes[0],support.factorial_moment_lexemes[1],
                support.factorial_moment_lexemes[2],support.factorial_moment_lexemes[3]};
            if (coordinator.ingest(observation,exact,watermark).status!=online::Status::ok)
                throw std::runtime_error("profiled reference ingest failed");
            ++emitted;
        }
    }
    if (emitted!=11747 || nonpassing!=12934 || coordinator.history_capacity_evictions())
        throw std::runtime_error("profiled reference evidence accounting failed");
    auto result=finish_reference(config,coordinator,watermark);
    const auto elapsed=std::chrono::duration<double>(Clock::now()-begun).count();
    result.wall_s=elapsed;
    return {std::move(result),deriver.cache_stats(),elapsed};
}

void require_profiled(const Summary& value,std::uint32_t workers) {
    const auto binding=leo::adaptive::server_compat::authority_binding();
    if (!full_lossless(value) || !value.support_profile_bound ||
        value.support_profile.profile_name!=binding.profile_name ||
        value.support_profile.profile_manifest_digest!=binding.profile_manifest_digest ||
        value.session.profile_prepared!=11747 || value.session.support_derived!=11747 ||
        value.session.support_derivation_count!=11747 || value.session.support_invalid ||
        value.session.support_unavailable || value.session.support_unhealthy ||
        value.session.discarded_after_support_failure ||
        value.last_search.state!=online::SearchState::complete ||
        value.last_search.evaluated_points!=1 || !value.last_search.has_incumbent ||
        value.last_search.incumbent_matched_tracks!=64 ||
        value.last_search.incumbent_unmatched_tracks!=0)
        throw std::runtime_error("profiled Analysis run failed for workers="+
            std::to_string(workers));
}

void same_result(const online::SearchResult& left,const online::SearchResult& right,
                 const char* message) {
    if (left.state!=right.state || left.evaluated_points!=right.evaluated_points ||
        left.has_incumbent!=right.has_incumbent ||
        left.incumbent.east_km!=right.incumbent.east_km ||
        left.incumbent.north_km!=right.incumbent.north_km ||
        left.incumbent.weighted_mse_hz2!=right.incumbent.weighted_mse_hz2 ||
        left.incumbent_residual_rmse_hz!=right.incumbent_residual_rmse_hz ||
        left.incumbent_matched_tracks!=right.incumbent_matched_tracks ||
        left.incumbent_unmatched_tracks!=right.incumbent_unmatched_tracks ||
        left.incumbent_evaluated_satellite_tracks!=right.incumbent_evaluated_satellite_tracks ||
        left.incumbent_rejected_satellite_tracks!=right.incumbent_rejected_satellite_tracks)
        throw std::runtime_error(message);
}

}  // namespace

int main(int argc,char** argv) {
    try {
        const bool background=argc==11 && std::string(argv[5])=="--background-pace" &&
            std::string(argv[7])=="--analysis-workers" &&
            std::string(argv[9])=="--expected-mse";
        if (argc!=5 && !background) throw std::runtime_error(
            "usage: test-profiled-analysis PROJECTION TARGETS TLES SEARCH "
            "[--background-pace SCALE --analysis-workers 1..4 --expected-mse VALUE]");
        const auto all=rows(argv[1]);
        const auto metadata=targets(argv[2]);
        const auto catalogue=tles(argv[3]);
        const auto location=search(argv[4]);
        if (catalogue.size()!=11129 || location.budget!=1)
            throw std::runtime_error("bad profiled Analysis fixture");
        const auto events=select_events(all,metadata,true);
        auto config=configuration(all.front().source,metadata,catalogue,location,
            600'000'000'000ULL);
        // Independent portable verification proves that the replay lattice maps
        // back to the original absolute-counter authority before either profile
        // implementation is allowed to derive support.
        verify_projection_authority(all.front().source,config.authority,events,11747);

        if (background) {
            const auto pace=number(argv[6]);
            const auto workers=unsigned_integer<std::uint32_t>(argv[8]);
            const auto expected_mse=number(argv[10]);
            if (!(pace>0 && pace<=1) || workers<1 || workers>4 || expected_mse<0)
                throw std::runtime_error("bad profiled background configuration");
            const auto measured=run_profiled_background(
                config,all.front().source,events,workers,pace);
            require_profiled(measured.run.summary,workers);
            const auto& summary=measured.run.summary;
            const auto& result=summary.last_search;
            const auto rmse_delta=std::abs(std::sqrt(result.incumbent.weighted_mse_hz2)-
                std::sqrt(expected_mse));
            if (rmse_delta>1e-6)
                throw std::runtime_error("profiled background/reference RMSE differs");
            const auto binding=leo::adaptive::server_compat::authority_binding();
            std::cout<<std::setprecision(17)
                <<"{\"schema\":\"leo-profiled-analysis-replay/v1\","
                <<"\"mode\":\"independent-producer-background-owner\","
                <<"\"scope\":\"recorded-candidates-no-iq-no-detector-no-rf\","
                <<"\"support_profile_name\":\""<<binding.profile_name<<"\","
                <<"\"support_profile_manifest_digest\":\""
                <<binding.profile_manifest_digest<<"\",\"source_rows\":"<<all.size()
                <<",\"profile_prepared\":"<<summary.session.profile_prepared
                <<",\"support_derived\":"<<summary.session.support_derived
                <<",\"nonpassing\":"<<summary.session.nonpassing
                <<",\"analysis_workers\":"<<workers<<",\"pace_scale\":"<<pace
                <<",\"tracks\":64,\"matched_tracks\":"
                <<result.incumbent_matched_tracks<<",\"unmatched_tracks\":"
                <<result.incumbent_unmatched_tracks<<",\"catalogue_records\":"
                <<catalogue.size()<<",\"east_km\":"<<result.incumbent.east_km
                <<",\"north_km\":"<<result.incumbent.north_km
                <<",\"weighted_mse_hz2\":"<<result.incumbent.weighted_mse_hz2
                <<",\"residual_rmse_hz\":"<<result.incumbent_residual_rmse_hz
                <<",\"evaluated_satellite_tracks\":"
                <<result.incumbent_evaluated_satellite_tracks
                <<",\"rejected_satellite_tracks\":"
                <<result.incumbent_rejected_satellite_tracks
                <<",\"expected_weighted_mse_hz2\":"<<expected_mse
                <<",\"rmse_delta_hz\":"<<rmse_delta
                <<",\"wall_seconds\":"<<measured.run.wall_s
                <<",\"producer_wall_seconds\":"<<measured.run.producer_wall_s
                <<",\"producer_finish_tail_seconds\":"<<measured.run.finish_tail_s
                <<",\"source_span_seconds\":"<<measured.run.source_span_s
                <<",\"producer_callback_max_ns\":"<<measured.run.maximum_callback_ns
                <<",\"queue_high_water\":"<<summary.session.high_water
                <<",\"queue_dropped\":"<<summary.session.queue_dropped
                <<",\"derivation_count\":"<<summary.session.support_derivation_count
                <<",\"derivation_total_ns\":"<<summary.session.support_derivation_total_ns
                <<",\"derivation_max_ns\":"<<summary.session.support_derivation_max_ns
                <<",\"result_source_age_lower_max_ns\":"
                <<summary.result_source_age_lower_max_ns
                <<",\"result_source_age_upper_max_ns\":"
                <<summary.result_source_age_upper_max_ns
                <<",\"cache_hits\":"<<measured.cache.hits
                <<",\"cache_misses\":"<<measured.cache.misses
                <<",\"reference_evaluated_in_process\":false,"
                <<"\"lattice_utc_matches_original_authority\":true,"
                <<"\"queue_loss\":false,\"five_second_freshness_claimed\":false,"
                <<"\"strict_pipeline_parity\":false,"
                <<"\"open_c4_duplicate_rank_ties\":6,\"qualified\":true}\n";
            return 0;
        }

        const auto reference=profiled_reference(config,all.front().source,events);
        const auto one=run_profiled(config,all.front().source,events,1);
        const auto two=run_profiled(config,all.front().source,events,2);
        require_profiled(one.summary,1);
        require_profiled(two.summary,2);
        same_result(one.summary.last_search,two.summary.last_search,
            "one/two-worker profiled Analysis results differ");
        same_result(one.summary.last_search,reference.result.search,
            "profiled Analysis/reference results differ");

        const auto binding=leo::adaptive::server_compat::authority_binding();
        std::cout<<std::setprecision(17)
            <<"{\"schema\":\"leo-profiled-analysis-replay/v1\","
            <<"\"scope\":\"recorded-candidates-no-iq-no-detector-no-rf\","
            <<"\"support_profile_name\":\""<<binding.profile_name<<"\","
            <<"\"support_profile_manifest_digest\":\""
            <<binding.profile_manifest_digest<<"\","
            <<"\"source_rows\":"<<all.size()<<",\"profile_prepared\":11747,"
            <<"\"nonpassing\":12934,\"tracks\":"<<reference.result.tracks
            <<",\"matched_tracks\":"<<reference.result.search.incumbent_matched_tracks
            <<",\"catalogue_records\":"<<catalogue.size()
            <<",\"weighted_mse_hz2\":"
            <<reference.result.search.incumbent.weighted_mse_hz2
            <<",\"reference_wall_seconds\":"<<reference.wall_s
            <<",\"one_worker_wall_seconds\":"<<one.wall_s
            <<",\"two_worker_wall_seconds\":"<<two.wall_s
            <<",\"reference_cache_hits\":"<<reference.cache.hits
            <<",\"reference_cache_misses\":"<<reference.cache.misses
            <<",\"one_worker_cache_hits\":"<<one.cache.hits
            <<",\"one_worker_cache_misses\":"<<one.cache.misses
            <<",\"two_worker_cache_hits\":"<<two.cache.hits
            <<",\"two_worker_cache_misses\":"<<two.cache.misses
            <<",\"one_two_worker_exact\":true,\"independent_reference_exact\":true,"
            <<"\"lattice_utc_matches_original_authority\":true,"
            <<"\"queue_loss\":false,\"strict_pipeline_parity\":false,"
            <<"\"open_c4_duplicate_rank_ties\":6,\"qualified\":true}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr<<error.what()<<'\n';
        return 1;
    }
}
