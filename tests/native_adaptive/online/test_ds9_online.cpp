#include "online.hpp"
#include "tle_id.hpp"

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <unordered_map>
#include <vector>

namespace {
struct PointTrace {
    leo_point_score point{};
    std::vector<leo_track_score> tracks;
};
struct SearchTrace {
    std::vector<leo_search_evaluation> evaluations;
    std::vector<PointTrace> points;
};
SearchTrace* active_trace{};

std::vector<std::string> fields(const std::string& line) {
    std::vector<std::string> result;
    std::size_t begin = 0;
    for (;;) {
        const auto end = line.find('\t', begin);
        result.push_back(line.substr(begin, end - begin));
        if (end == std::string::npos) return result;
        begin = end + 1;
    }
}

template <class T> T integer(const std::string& text) {
    errno = 0;
    char* end = nullptr;
    const long long value = std::strtoll(text.c_str(), &end, 10);
    if (errno || end != text.c_str() + text.size() ||
        value < static_cast<long long>(std::numeric_limits<T>::min()) ||
        value > static_cast<long long>(std::numeric_limits<T>::max()))
        throw std::runtime_error("invalid integer fixture field");
    return static_cast<T>(value);
}

double number(const std::string& text) {
    char* end = nullptr;
    const double value = std::strtod(text.c_str(), &end);
    if (end != text.c_str() + text.size()) throw std::runtime_error("invalid number field");
    return value;
}

std::vector<leo_tle_record> tles(const std::string& path, std::size_t limit) {
    std::ifstream input(path);
    std::size_t count = 0;
    if (!(input >> count)) throw std::runtime_error("cannot read TLE count");
    input.ignore(1024, '\n');
    count = std::min(count, limit);
    std::vector<leo_tle_record> result(count);
    for (std::size_t index = 0; index < count; ++index) {
        std::string one, two;
        std::getline(input, one); std::getline(input, two);
        if (one.size() != 69 || two.size() != 69) throw std::runtime_error("bad TLE");
        if (!leo::adaptive::location::parse_tle_catalogue_id(
                std::string_view(one).substr(2,5),result[index].satellite_id))
            throw std::runtime_error("bad TLE catalogue identity");
        std::memcpy(result[index].line1, one.data(), 69);
        std::memcpy(result[index].line2, two.data(), 69);
        result[index].line1[69] = result[index].line2[69] = '\0';
    }
    return result;
}

leo_location_site site(double latitude_deg, double longitude_deg) {
    constexpr double pi = 3.14159265358979323846;
    constexpr double semi_major_axis_km = 6378.137;
    constexpr double flattening = 1.0 / 298.257223563;
    constexpr double eccentricity_squared = flattening * (2.0 - flattening);
    const double latitude = latitude_deg * pi / 180.0;
    const double longitude = longitude_deg * pi / 180.0;
    const double prime_vertical = semi_major_axis_km /
        std::sqrt(1.0 - eccentricity_squared * std::sin(latitude) * std::sin(latitude));
    leo_location_site result{};
    result.ecef_km[0] = prime_vertical * std::cos(latitude) * std::cos(longitude);
    result.ecef_km[1] = prime_vertical * std::cos(latitude) * std::sin(longitude);
    result.ecef_km[2] = prime_vertical * (1.0 - eccentricity_squared) * std::sin(latitude);
    result.up[0] = std::cos(latitude) * std::cos(longitude);
    result.up[1] = std::cos(latitude) * std::sin(longitude);
    result.up[2] = std::sin(latitude);
    return result;
}

bool same_double(double left,double right) {
    return std::memcmp(&left,&right,sizeof(left))==0;
}

bool same_trace(const SearchTrace& left,const SearchTrace& right) {
    if(left.evaluations.size()!=right.evaluations.size() ||
       left.points.size()!=right.points.size()) return false;
    for(std::size_t i=0;i<left.evaluations.size();++i) {
        const auto& a=left.evaluations[i];const auto& b=right.evaluations[i];
        if(!same_double(a.east_km,b.east_km) || !same_double(a.north_km,b.north_km) ||
           !same_double(a.weighted_mse_hz2,b.weighted_mse_hz2)) return false;
    }
    for(std::size_t i=0;i<left.points.size();++i) {
        const auto& a=left.points[i];const auto& b=right.points[i];
        if(!same_double(a.point.weighted_mse_hz2,b.point.weighted_mse_hz2) ||
           !same_double(a.point.residual_rmse_hz,b.point.residual_rmse_hz) ||
           a.point.matched_track_count!=b.point.matched_track_count ||
           a.point.unmatched_track_count!=b.point.unmatched_track_count ||
           a.tracks.size()!=b.tracks.size()) return false;
        for(std::size_t j=0;j<a.tracks.size();++j) {
            const auto& x=a.tracks[j];const auto& y=b.tracks[j];
            if(x.matched!=y.matched || x.candidate_id!=y.candidate_id || x.tau_s!=y.tau_s ||
               !same_double(x.heldout_rms_hz,y.heldout_rms_hz) ||
               !same_double(x.training_rms_hz,y.training_rms_hz) ||
               !same_double(x.frequency_offset_hz,y.frequency_offset_hz)) return false;
        }
    }
    return true;
}
}  // namespace

extern "C" leo_location_status __real_leo_search_submit(
    leo_search_context*,std::uint64_t,const leo_search_evaluation*,std::uint32_t);
extern "C" leo_location_status __wrap_leo_search_submit(
    leo_search_context* context,std::uint64_t generation,
    const leo_search_evaluation* values,std::uint32_t count) {
    const auto status=__real_leo_search_submit(context,generation,values,count);
    if(status==LEO_LOCATION_OK && active_trace)
        active_trace->evaluations.insert(active_trace->evaluations.end(),values,values+count);
    return status;
}

extern "C" leo_location_status __real_leo_point_score_finish(
    const leo_location_track*,std::uint32_t,const leo_track_score*,
    const leo_score_config*,leo_point_score*);
extern "C" leo_location_status __wrap_leo_point_score_finish(
    const leo_location_track* tracks,std::uint32_t count,const leo_track_score* scores,
    const leo_score_config* config,leo_point_score* point) {
    const auto status=__real_leo_point_score_finish(tracks,count,scores,config,point);
    if(status==LEO_LOCATION_OK && active_trace)
        active_trace->points.push_back(PointTrace{*point,{scores,scores+count}});
    return status;
}

int main(int argc, char** argv) {
    try {
        if (argc < 4 || argc > 6)
            throw std::runtime_error("usage: test_ds9_online CANDIDATES GRAPH TLES [--cache400|--cache-points N]");
        std::uint32_t cache_points=0;
        if(argc==5 && std::string(argv[4])=="--cache400") cache_points=400;
        else if(argc==6 && std::string(argv[4])=="--cache-points") {
            const auto parsed=integer<int>(argv[5]);
            if(parsed<1 || parsed>400) throw std::runtime_error("invalid cache point bound");
            cache_points=static_cast<std::uint32_t>(parsed);
        } else if(argc!=4) throw std::runtime_error("unknown diagnostic mode");
        std::ifstream graph_input(argv[2]);
        std::string line;
        if (!std::getline(graph_input, line)) throw std::runtime_error("missing graph metadata");
        const auto meta = fields(line);
        if (meta.size() != 4 || meta[0] != "META") throw std::runtime_error("bad graph metadata");
        const std::int64_t session_start = integer<std::int64_t>(meta[3]);
        if (!std::getline(graph_input, line)) throw std::runtime_error("missing graph header");
        std::unordered_map<std::string, leo::adaptive::pipeline::SupportAuthority> support;
        while (std::getline(graph_input, line)) {
            const auto row = fields(line);
            if (row.size() != 8) throw std::runtime_error("bad graph row");
            support.emplace(row[0], leo::adaptive::pipeline::SupportAuthority{
                integer<std::int64_t>(row[1]), integer<std::int64_t>(row[2]),
                integer<std::int64_t>(row[3]), row[4], row[5], row[6], row[7]});
        }

        std::ifstream candidate_input(argv[1]);
        if (!std::getline(candidate_input, line)) throw std::runtime_error("missing candidates");
        std::vector<leo::adaptive::tracking::Candidate> all;
        while (std::getline(candidate_input, line)) {
            const auto row = fields(line);
            if (row.size() != 13) throw std::runtime_error("bad candidate row");
            all.push_back(leo::adaptive::tracking::Candidate{
                row[0], row[1], integer<int>(row[2]), integer<int>(row[3]), row[4], number(row[5]),
                integer<std::int64_t>(row[6]), integer<std::int64_t>(row[7]),
                integer<std::int64_t>(row[8]), number(row[9]), number(row[10]),
                number(row[11]), number(row[12])});
        }
        const std::int64_t first_end = std::min_element(all.begin(), all.end(), [](const auto& a, const auto& b) {
            return a.support_end_utc_ns < b.support_end_utc_ns;
        })->support_end_utc_ns;
        const std::int64_t cutoff = first_end + 10'000'000'000LL;
        std::vector<leo::adaptive::tracking::Candidate> prefix;
        for (const auto& value : all) if (value.support_end_utc_ns <= cutoff) prefix.push_back(value);
        std::sort(prefix.begin(), prefix.end(), [](const auto& a, const auto& b) {
            return std::tie(a.support_end_utc_ns, a.candidate_id) <
                std::tie(b.support_end_utc_ns, b.candidate_id);
        });

        leo::adaptive::online::Config config;
        config.maximum_satellites = 20'000;
        config.maximum_knots = 64;
        config.maximum_orbit_bytes = 20'000U * 64U * sizeof(leo_orbit_state) * 2U;
        const auto as_observation=[&](const leo::adaptive::tracking::Candidate& candidate) {
            const auto found = support.find(candidate.candidate_id);
            if (found == support.end()) throw std::runtime_error("missing graph support");
            leo::adaptive::Observation observation{};
            observation.candidate_id = candidate.candidate_id;
            observation.source_group_id = candidate.source_group_id;
            observation.generation = 1;
            observation.receiver = static_cast<std::uint32_t>(candidate.receiver_id);
            observation.channel = static_cast<std::uint32_t>(candidate.channel);
            observation.upper_edge = candidate.edge == "upper";
            observation.actual_rf_hz = candidate.actual_rf_hz;
            observation.measured_cfo_hz = candidate.measured_cfo_hz;
            observation.exact_score = candidate.exact_score;
            observation.control_score = candidate.control_score;
            observation.margin = candidate.margin;
            observation.support_start_utc_ns = candidate.support_start_utc_ns;
            observation.support_center_utc_ns = candidate.support_center_utc_ns;
            observation.support_end_utc_ns = candidate.support_end_utc_ns;
            observation.standard_uncertainty_hz = 400.0;
            observation.moment2 = number(found->second.moment2);
            observation.moment3 = number(found->second.moment3);
            return std::make_pair(observation,found->second);
        };
        const auto ingest=[&](leo::adaptive::online::Coordinator& owner,
                              const std::vector<leo::adaptive::tracking::Candidate>& values) {
            for(const auto& candidate:values) {
                const auto converted=as_observation(candidate);
                if (owner.ingest(converted.first, converted.second,
                        converted.first.support_end_utc_ns).status !=
                        leo::adaptive::online::Status::ok)
                    throw std::runtime_error("DS9 prefix ingest failed");
            }
        };
        if(cache_points) {
            std::sort(all.begin(),all.end(),[](const auto& a,const auto& b) {
                return std::tie(a.support_end_utc_ns,a.candidate_id)<
                    std::tie(b.support_end_utc_ns,b.candidate_id);
            });
            std::vector<std::int64_t> cutoffs;
            auto causal=all.front().support_end_utc_ns;
            const auto last=all.back().support_end_utc_ns;
            while(causal<last) {
                causal=std::min(causal+static_cast<std::int64_t>(5'000'000'000LL),last);
                cutoffs.push_back(causal);
            }
            auto causal_prefix=[&](std::size_t ordinal) {
                std::vector<leo::adaptive::tracking::Candidate> result;
                for(const auto& item:all)
                    if(item.support_end_utc_ns<=cutoffs.at(ordinal-1)) result.push_back(item);
                return result;
            };
            const auto prefix58=causal_prefix(58);
            const auto prefix59=causal_prefix(59);
            const auto prefix60=causal_prefix(60);
            if(prefix58.size()!=11389 || prefix59.size()!=11566 || prefix60.size()!=11747)
                throw std::runtime_error("cache400 prefix shape differs");
            auto configured=[&](bool cache) {
                auto value=config;
                value.maximum_knots=128;
                value.maximum_orbit_bytes=20'000U*128U*sizeof(leo_orbit_state)*2U;
                value.publication_search_policy=
                    leo::adaptive::online::PublicationSearchPolicy::pin_started_snapshot;
                value.scoring_execution={2,nullptr,
                    [](void*,std::size_t count,void* context,void (*task)(void*,std::size_t)) {
                        std::vector<std::thread> threads;
                        for(std::size_t index=0;index<count;++index)
                            threads.emplace_back([=]{task(context,index);});
                        for(auto& thread:threads) thread.join();
                    }};
                value.maximum_exact_score_cache_bytes=cache?6U*1024U*1024U:0U;
                return value;
            };
            auto orbit_for=[&](leo::adaptive::online::Coordinator& owner) {
                leo::adaptive::online::OrbitBuild value{};
                value.generation=1;value.start_utc_ns=session_start;value.knot_start_s=-10;
                value.knot_step_s=10;value.knot_count=96;value.records=tles(argv[3],20'000);
                if(owner.replace_orbit(value)!=leo::adaptive::online::Status::ok)
                    throw std::runtime_error("cache400 orbit failed");
            };
            leo::adaptive::online::SearchConfig regional{};
            regional.origin_latitude_deg=38.5816;regional.origin_longitude_deg=-121.4944;
            regional.score=leo_score_default_config();
            regional.policy=leo_search_default_policy(250.0);
            regional.policy.budget_points=cache_points;
            if(cache_points<16) {
                if(cache_points!=1)
                    throw std::runtime_error("original regional policy requires at least 16 points; use one-point bounded diagnostic or 16+");
                regional.policy.radius_km=50.0;
                regional.policy.region_size_km=100.0;
                regional.policy.level_count=1;
                regional.policy.levels_km[0]=100.0;
            }
            auto search400=[&](leo::adaptive::online::Coordinator& owner,
                               const std::shared_ptr<const leo::adaptive::online::Snapshot>& snap) {
                leo::adaptive::online::SearchResult begun{};
                if(owner.begin_search(snap->generation,regional,&begun)!=
                        leo::adaptive::online::Status::ok)
                    throw std::runtime_error("cache400 search begin failed");
                const auto value=owner.resume_search(cache_points);
                if(value.evaluated_points!=cache_points || !value.has_incumbent)
                    throw std::runtime_error("cache400 search did not consume policy");
                return value;
            };
            auto timed_search=[&](leo::adaptive::online::Coordinator& owner,
                                  const std::shared_ptr<const leo::adaptive::online::Snapshot>& snap,
                                  SearchTrace* trace) {
                const auto before=std::chrono::steady_clock::now();
                active_trace=trace;
                auto result=search400(owner,snap);
                active_trace=nullptr;
                return std::make_pair(result,std::chrono::duration<double>(
                    std::chrono::steady_clock::now()-before).count());
            };
            const auto started_at=std::chrono::steady_clock::now();
            SearchTrace fill58_trace,warm59_trace,cold59_trace,warm60_trace,cold60_trace;
            leo::adaptive::online::SearchResult warm59_result{},warm60_result{};
            double fill58_seconds=0,warm59_seconds=0,warm60_seconds=0;
            leo::adaptive::online::ExactScoreCacheStats cache_stats{};
            {
                leo::adaptive::online::Coordinator cached(configured(true),
                    {meta[1],meta[2],session_start});
                if(cached.replace_stream_generation(1)!=leo::adaptive::online::Status::ok)
                    throw std::runtime_error("cache400 generation failed");
                ingest(cached,prefix58);
                std::shared_ptr<const leo::adaptive::online::Snapshot> snap58;
                if(cached.publish(prefix58.back().support_end_utc_ns,&snap58)!=
                        leo::adaptive::online::Status::ok)
                    throw std::runtime_error("cache400 publish58");
                orbit_for(cached);
                auto measured=timed_search(cached,snap58,&fill58_trace);
                fill58_seconds=measured.second;
                std::vector<leo::adaptive::tracking::Candidate> delta(
                    prefix59.begin()+static_cast<std::ptrdiff_t>(prefix58.size()),prefix59.end());
                ingest(cached,delta);
                std::shared_ptr<const leo::adaptive::online::Snapshot> snap59;
                if(cached.publish(prefix59.back().support_end_utc_ns,&snap59)!=
                        leo::adaptive::online::Status::ok)
                    throw std::runtime_error("cache400 publish59");
                measured=timed_search(cached,snap59,&warm59_trace);
                warm59_result=measured.first;warm59_seconds=measured.second;
                std::vector<leo::adaptive::tracking::Candidate> delta60(
                    prefix60.begin()+static_cast<std::ptrdiff_t>(prefix59.size()),prefix60.end());
                ingest(cached,delta60);
                std::shared_ptr<const leo::adaptive::online::Snapshot> snap60;
                if(cached.publish(prefix60.back().support_end_utc_ns,&snap60)!=
                        leo::adaptive::online::Status::ok)
                    throw std::runtime_error("cache400 publish60");
                measured=timed_search(cached,snap60,&warm60_trace);
                warm60_result=measured.first;warm60_seconds=measured.second;
                cache_stats=cached.exact_score_cache_stats();
            }
            leo::adaptive::online::SearchResult cold59_result{};
            double cold59_seconds=0;
            {
                leo::adaptive::online::Coordinator cold(configured(false),
                    {meta[1],meta[2],session_start});
                if(cold.replace_stream_generation(1)!=leo::adaptive::online::Status::ok)
                    throw std::runtime_error("cache400 cold generation failed");
                ingest(cold,prefix59);
                std::shared_ptr<const leo::adaptive::online::Snapshot> cold_snapshot;
                if(cold.publish(prefix59.back().support_end_utc_ns,&cold_snapshot)!=
                        leo::adaptive::online::Status::ok)
                    throw std::runtime_error("cache400 cold publish");
                orbit_for(cold);
                auto measured=timed_search(cold,cold_snapshot,&cold59_trace);
                cold59_result=measured.first;cold59_seconds=measured.second;
            }
            const auto same_science=[](const auto& warm,const auto& reference) {
                return warm.evaluated_points==reference.evaluated_points &&
                    warm.deferred_cells==reference.deferred_cells &&
                    warm.incumbent.east_km==reference.incumbent.east_km &&
                    warm.incumbent.north_km==reference.incumbent.north_km &&
                    warm.incumbent.weighted_mse_hz2==reference.incumbent.weighted_mse_hz2 &&
                    warm.incumbent_residual_rmse_hz==reference.incumbent_residual_rmse_hz &&
                    warm.incumbent_matched_tracks==reference.incumbent_matched_tracks &&
                    warm.incumbent_unmatched_tracks==reference.incumbent_unmatched_tracks &&
                    warm.incumbent_evaluated_satellite_tracks==
                        reference.incumbent_evaluated_satellite_tracks &&
                    warm.incumbent_rejected_satellite_tracks==
                        reference.incumbent_rejected_satellite_tracks;
            };
            leo::adaptive::online::SearchResult cold60_result{};
            double cold60_seconds=0;
            {
                leo::adaptive::online::Coordinator cold_last(configured(false),
                    {meta[1],meta[2],session_start});
                if(cold_last.replace_stream_generation(1)!=leo::adaptive::online::Status::ok)
                    throw std::runtime_error("cache400 cold60 generation failed");
                ingest(cold_last,prefix60);
                std::shared_ptr<const leo::adaptive::online::Snapshot> cold60_snapshot;
                if(cold_last.publish(prefix60.back().support_end_utc_ns,&cold60_snapshot)!=
                        leo::adaptive::online::Status::ok)
                    throw std::runtime_error("cache400 cold60 publish");
                orbit_for(cold_last);
                auto measured=timed_search(cold_last,cold60_snapshot,&cold60_trace);
                cold60_result=measured.first;cold60_seconds=measured.second;
            }
            if(warm59_trace.evaluations.size()!=cache_points ||
               warm59_trace.points.size()!=cache_points ||
               cold59_trace.evaluations.size()!=cache_points ||
               cold59_trace.points.size()!=cache_points ||
               !same_science(warm59_result,cold59_result) ||
               !same_trace(warm59_trace,cold59_trace))
                throw std::runtime_error("cache400 changed search science");
            if(warm60_trace.evaluations.size()!=cache_points ||
               warm60_trace.points.size()!=cache_points ||
               cold60_trace.evaluations.size()!=cache_points ||
               cold60_trace.points.size()!=cache_points ||
               !same_science(warm60_result,cold60_result) ||
               !same_trace(warm60_trace,cold60_trace))
                throw std::runtime_error("cache400 changed prefix60 search science");
            const double seconds=std::chrono::duration<double>(
                std::chrono::steady_clock::now()-started_at).count();
            std::cout<<std::setprecision(17)
                <<"{\"schema\":\"leo-online-exact-score-cache-trace/v1\","
                <<"\"prefixes\":[58,59,60],\"candidates\":["<<prefix58.size()<<','
                <<prefix59.size()<<','<<prefix60.size()
                <<"],\"catalogue_records\":11129,\"evaluated_points\":"<<cache_points<<','
                <<"\"track_hits\":"<<cache_stats.track_hits
                <<",\"track_misses\":"<<cache_stats.track_misses
                <<",\"retained_sites\":"<<cache_stats.retained_sites
                <<",\"retained_payload_bytes\":"<<cache_stats.retained_payload_bytes
                <<",\"search_seconds\":{\"fill58\":"<<fill58_seconds
                <<",\"warm59\":"<<warm59_seconds<<",\"cold59\":"<<cold59_seconds
                <<",\"warm60\":"<<warm60_seconds<<",\"cold60\":"<<cold60_seconds<<"}"
                <<",\"incumbent59_rmse_hz\":"<<warm59_result.incumbent_residual_rmse_hz
                <<",\"incumbent60_rmse_hz\":"<<warm60_result.incumbent_residual_rmse_hz
                <<",\"prefix60_evaluated_satellite_tracks\":"
                <<warm60_result.incumbent_evaluated_satellite_tracks
                <<",\"prefix60_rejected_satellite_tracks\":"
                <<warm60_result.incumbent_rejected_satellite_tracks
                <<",\"trace_points_compared\":"<<2U*cache_points
                <<",\"track_winners_compared\":"<<128U*cache_points<<','
                <<"\"cold_warm_science_bit_exact\":true,\"elapsed_seconds\":"
                <<seconds<<"}\n";
            return 0;
        }
        leo::adaptive::online::Coordinator coordinator(config, {
            meta[1], meta[2], session_start});
        if (coordinator.replace_stream_generation(1) != leo::adaptive::online::Status::ok)
            throw std::runtime_error("stream generation failed");
        ingest(coordinator,prefix);
        std::shared_ptr<const leo::adaptive::online::Snapshot> snapshot;
        const std::int64_t prefix_watermark = prefix.back().support_end_utc_ns;
        const auto publish_status = coordinator.publish(prefix_watermark, &snapshot);
        if (publish_status != leo::adaptive::online::Status::ok)
            throw std::runtime_error("DS9 prefix publication failed: " +
                std::to_string(static_cast<int>(publish_status)));
        const auto expected = leo::adaptive::tracking::reconstruct(prefix);
        const auto comparison = leo::adaptive::online::compare_reference(*snapshot, expected);
        if (!comparison.exact || prefix.size() != 492 || snapshot->tracking_result.tracks.size() != 11)
            throw std::runtime_error("DS9 causal prefix reference differs");

        { // Release the comparison coordinator before the full-catalogue searches.
        auto parallel_config=config;
        parallel_config.tracking_execution={nullptr,
            [](void*,std::size_t count,void* context,void (*task)(void*,std::size_t)) {
                auto run=[&](std::size_t parity) {
                    for(std::size_t offset=parity;offset<count;offset+=2)
                        task(context,count-1-offset);
                };
                std::thread worker([&]{run(1);});run(0);worker.join();
            }};
        leo::adaptive::online::Coordinator parallel(parallel_config,{meta[1],meta[2],session_start});
        if(parallel.replace_stream_generation(1)!=leo::adaptive::online::Status::ok)
            throw std::runtime_error("parallel generation failed");
        ingest(parallel,prefix);
        std::shared_ptr<const leo::adaptive::online::Snapshot> parallel_snapshot;
        if(parallel.publish(prefix_watermark,&parallel_snapshot)!=leo::adaptive::online::Status::ok ||
            !leo::adaptive::online::compare_reference(*parallel_snapshot,snapshot->tracking_result).exact)
            throw std::runtime_error("parallel DS9 tracking differs");
        const auto& expected_graph=snapshot->location_tracks.owned;
        const auto& actual_graph=parallel_snapshot->location_tracks.owned;
        if(expected_graph.size()!=actual_graph.size()) throw std::runtime_error("parallel graph count differs");
        for(std::size_t index=0;index<actual_graph.size();++index) {
            const auto& a=actual_graph[index];const auto& b=expected_graph[index];
            if(a.tracklet_id!=b.tracklet_id || a.support_digest!=b.support_digest ||
                a.partition_seed!=b.partition_seed || a.observation_ids!=b.observation_ids ||
                a.training_mask!=b.training_mask || a.times_s!=b.times_s || a.measured_hz!=b.measured_hz)
                throw std::runtime_error("parallel DS9 support authority differs");
        }

        }

        leo::adaptive::online::OrbitBuild orbit{};
        orbit.generation = 1;
        orbit.start_utc_ns = session_start;
        orbit.knot_start_s = -10.0;
        orbit.knot_step_s = 1.0;
        orbit.knot_count = 32;
        orbit.records = tles(argv[3], 20'000);
        if (coordinator.replace_orbit(orbit) != leo::adaptive::online::Status::ok)
            throw std::runtime_error("DS9 bounded orbit failed");
        leo::adaptive::online::SearchConfig search{};
        search.origin_latitude_deg = 38.5;
        search.origin_longitude_deg = -121.5;
        search.score = leo_score_default_config();
        search.policy.radius_km = 50.0;
        search.policy.region_size_km = 100.0;
        search.policy.level_count = 1;
        search.policy.levels_km[0] = 100.0;
        search.policy.budget_points = 1;
        leo::adaptive::online::SearchResult started{};
        if (coordinator.begin_search(snapshot->generation, search, &started) !=
                leo::adaptive::online::Status::ok)
            throw std::runtime_error("DS9 bounded search did not begin");
        const auto result = coordinator.resume_search(1);
        if (result.state != leo::adaptive::online::SearchState::complete ||
            result.evaluated_points != 1 || !result.has_incumbent ||
            !std::isfinite(result.incumbent.weighted_mse_hz2) ||
            !std::isfinite(result.incumbent_residual_rmse_hz) ||
            result.incumbent_matched_tracks == 0 ||
            result.incumbent_evaluated_satellite_tracks == 0)
            throw std::runtime_error("DS9 real native score did not complete");

        search.policy.level_count=2;
        search.policy.levels_km[0]=100.0;
        search.policy.levels_km[1]=50.0;
        search.policy.budget_points=5;
        if (coordinator.begin_search(snapshot->generation,search,&started)!=
                leo::adaptive::online::Status::ok)
            throw std::runtime_error("DS9 five-point control did not begin");
        const auto five_point_control=coordinator.resume_search(5);
        if(five_point_control.state!=leo::adaptive::online::SearchState::complete ||
                five_point_control.evaluated_points!=5)
            throw std::runtime_error("DS9 five-point control did not complete");

        auto pinned_config=config;
        pinned_config.publication_search_policy=
            leo::adaptive::online::PublicationSearchPolicy::pin_started_snapshot;
        leo::adaptive::online::Coordinator pinned(pinned_config,{
            meta[1],meta[2],session_start});
        if(pinned.replace_stream_generation(1)!=leo::adaptive::online::Status::ok)
            throw std::runtime_error("DS9 pinned stream generation failed");
        ingest(pinned,prefix);
        std::shared_ptr<const leo::adaptive::online::Snapshot> pinned_snapshot;
        if(pinned.publish(prefix_watermark,&pinned_snapshot)!=
                leo::adaptive::online::Status::ok || !pinned_snapshot ||
                pinned.replace_orbit(orbit)!=leo::adaptive::online::Status::ok)
            throw std::runtime_error("DS9 pinned setup failed");
        if(pinned.begin_search(pinned_snapshot->generation,search,&started)!=
                leo::adaptive::online::Status::ok)
            throw std::runtime_error("DS9 pinned search did not begin");
        auto sliced=pinned.resume_search(1);
        const auto later=std::find_if(all.begin(),all.end(),[&](const auto& candidate) {
            return candidate.support_end_utc_ns>prefix_watermark &&
                support.count(candidate.candidate_id)!=0;
        });
        if(later==all.end()) throw std::runtime_error("DS9 later publication is absent");
        const auto later_observation=as_observation(*later);
        if(pinned.ingest(later_observation.first,later_observation.second,
                    later_observation.first.support_end_utc_ns).status!=
                leo::adaptive::online::Status::ok)
            throw std::runtime_error("DS9 later ingest failed");
        std::shared_ptr<const leo::adaptive::online::Snapshot> newer_snapshot;
        if(pinned.publish(later_observation.first.support_end_utc_ns,&newer_snapshot)!=
                leo::adaptive::online::Status::ok || !newer_snapshot ||
                newer_snapshot->generation==pinned_snapshot->generation)
            throw std::runtime_error("DS9 newer publication failed");
        while(sliced.state==leo::adaptive::online::SearchState::running_unconverged) {
            const auto before=sliced.evaluated_points;
            sliced=pinned.resume_search(1);
            if(sliced.evaluated_points!=before+1)
                throw std::runtime_error("DS9 one-point slice did not progress");
        }
        if(sliced.state!=five_point_control.state ||
                sliced.snapshot_generation!=pinned_snapshot->generation ||
                sliced.evaluated_points!=five_point_control.evaluated_points ||
                sliced.deferred_cells!=five_point_control.deferred_cells ||
                sliced.incumbent.east_km!=five_point_control.incumbent.east_km ||
                sliced.incumbent.north_km!=five_point_control.incumbent.north_km ||
                sliced.incumbent.weighted_mse_hz2!=
                    five_point_control.incumbent.weighted_mse_hz2 ||
                sliced.incumbent_residual_rmse_hz!=
                    five_point_control.incumbent_residual_rmse_hz ||
                sliced.incumbent_matched_tracks!=
                    five_point_control.incumbent_matched_tracks ||
                sliced.incumbent_unmatched_tracks!=
                    five_point_control.incumbent_unmatched_tracks ||
                sliced.incumbent_evaluated_satellite_tracks!=
                    five_point_control.incumbent_evaluated_satellite_tracks ||
                sliced.incumbent_rejected_satellite_tracks!=
                    five_point_control.incumbent_rejected_satellite_tracks)
            throw std::runtime_error("DS9 pinned sliced score differs from control");

        // Independent public-ABI score of the identical immutable prefix and
        // site. The coordinator result must be the native score, not merely a
        // finite unmatched-penalty incumbent supplied by the search adapter.
        std::unique_ptr<leo_orbit_context, decltype(&leo_orbit_context_destroy)> direct_orbit(
            leo_orbit_context_create(20'000, 64), &leo_orbit_context_destroy);
        leo_orbit_snapshot direct_snapshot{};
        if (!direct_orbit || leo_orbit_build_tle(
                direct_orbit.get(), 2, orbit.start_utc_ns, orbit.knot_start_s,
                orbit.knot_step_s, orbit.knot_count, orbit.records.data(),
                static_cast<std::uint32_t>(orbit.records.size()), &direct_snapshot) !=
                LEO_LOCATION_OK)
            throw std::runtime_error("direct comparison orbit failed");
        std::uint32_t maximum_observations = 0;
        for (const auto& track : snapshot->location_tracks.records)
            maximum_observations = std::max(maximum_observations, track.observation_count);
        std::unique_ptr<leo_score_context, decltype(&leo_score_context_destroy)> direct_scorer(
            leo_score_context_create(maximum_observations, 11), &leo_score_context_destroy);
        std::vector<leo_track_score> direct_tracks(snapshot->location_tracks.records.size());
        leo_track_scores_clear(direct_tracks.data(), static_cast<std::uint32_t>(direct_tracks.size()));
        const leo_location_site direct_site = site(search.origin_latitude_deg, search.origin_longitude_deg);
        leo_score_stats direct_stats{};
        leo_point_score direct_point{};
        if (!direct_scorer || leo_score_partition(
                direct_scorer.get(), &direct_snapshot,
                snapshot->location_tracks.records.data(),
                static_cast<std::uint32_t>(snapshot->location_tracks.records.size()),
                &direct_site, &search.score, 0, direct_snapshot.satellite_count,
                direct_tracks.data(), &direct_stats) != LEO_LOCATION_OK ||
            leo_point_score_finish(
                snapshot->location_tracks.records.data(),
                static_cast<std::uint32_t>(snapshot->location_tracks.records.size()),
                direct_tracks.data(), &search.score, &direct_point) != LEO_LOCATION_OK ||
            direct_point.weighted_mse_hz2 != result.incumbent.weighted_mse_hz2 ||
            direct_point.residual_rmse_hz != result.incumbent_residual_rmse_hz ||
            direct_point.matched_track_count != result.incumbent_matched_tracks ||
            direct_point.unmatched_track_count != result.incumbent_unmatched_tracks ||
            direct_stats.evaluated_satellite_tracks !=
                result.incumbent_evaluated_satellite_tracks ||
            direct_stats.rejected_satellite_tracks !=
                result.incumbent_rejected_satellite_tracks)
            throw std::runtime_error("coordinator score differs from direct public ABI");
        std::cout << std::setprecision(17)
                  << "{\"prefix_candidates\":" << prefix.size()
                  << ",\"tracks\":" << snapshot->tracking_result.tracks.size()
                  << ",\"catalogue_records\":"<<orbit.records.size()
                  << ",\"scored_points\":1,\"pinned_scored_points\":5,\"matched_tracks\":"
                  << result.incumbent_matched_tracks << ",\"unmatched_tracks\":"
                  << result.incumbent_unmatched_tracks << ",\"score_hz\":"
                  << result.incumbent_residual_rmse_hz
                  << ",\"evaluated_satellite_tracks\":"
                  << result.incumbent_evaluated_satellite_tracks
                  << ",\"rejected_satellite_tracks\":"
                  << result.incumbent_rejected_satellite_tracks << "}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
