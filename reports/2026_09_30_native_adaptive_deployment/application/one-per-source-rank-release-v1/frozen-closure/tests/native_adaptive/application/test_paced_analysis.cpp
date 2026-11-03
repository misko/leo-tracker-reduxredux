#include "live.hpp"
#include "execution.hpp"
#include "../location/tle_id.hpp"

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <string_view>
#include <sys/resource.h>
#include <thread>
#include <tuple>
#include <unordered_set>
#include <vector>

namespace {
using namespace leo::adaptive;
using namespace leo::adaptive::application::live;
using Clock = std::chrono::steady_clock;
constexpr double full_reference_mse_hz2=64906.771460780015;
constexpr double full_reference_rmse_tolerance_hz=1e-6;

std::vector<std::string> fields(const std::string& line) {
    std::vector<std::string> result;
    std::size_t begin=0;
    for (;;) {
        const auto end=line.find('\t',begin);
        result.push_back(line.substr(begin,end-begin));
        if (end==std::string::npos) return result;
        begin=end+1;
    }
}

template<class T> T unsigned_integer(const std::string& text) {
    static_assert(std::numeric_limits<T>::is_integer && !std::numeric_limits<T>::is_signed);
    if (text.empty() || text.front()=='-') throw std::runtime_error("invalid unsigned integer");
    errno=0; char* end=nullptr; const auto value=std::strtoull(text.c_str(),&end,10);
    if (errno || end!=text.c_str()+text.size() || value>std::numeric_limits<T>::max())
        throw std::runtime_error("invalid unsigned integer");
    return static_cast<T>(value);
}

template<class T> T signed_integer(const std::string& text) {
    static_assert(std::numeric_limits<T>::is_integer && std::numeric_limits<T>::is_signed);
    if (text.empty()) throw std::runtime_error("invalid signed integer");
    errno=0; char* end=nullptr; const auto value=std::strtoll(text.c_str(),&end,10);
    if (errno || end!=text.c_str()+text.size() || value<std::numeric_limits<T>::min() ||
        value>std::numeric_limits<T>::max()) throw std::runtime_error("invalid signed integer");
    return static_cast<T>(value);
}

double number(const std::string& text) {
    if (text.empty()) throw std::runtime_error("invalid number");
    errno=0; char* end=nullptr; const double value=std::strtod(text.c_str(),&end);
    if (errno || end!=text.c_str()+text.size() || !std::isfinite(value))
        throw std::runtime_error("invalid number");
    return value;
}

std::uint64_t process_status_kib(const std::string& key) {
    std::ifstream input("/proc/self/status");
    std::string name,unit; std::uint64_t value=0;
    while (input>>name) {
        if (name==key) {
            if (!(input>>value>>unit) || unit!="kB") return 0;
            return value;
        }
        std::string rest; std::getline(input,rest);
    }
    return 0;
}

struct Row { ProjectionSource source; FractionalCandidate candidate; };

std::vector<Row> rows(const std::string& path) {
    std::ifstream input(path); if (!input) throw std::runtime_error("cannot open projection rows");
    std::vector<Row> result; result.reserve(24681); std::string line;
    while (std::getline(input,line)) {
        if (line.size()>4096 || result.size()>=25000) throw std::runtime_error("oversized rows");
        const auto f=fields(line); if (f.size()!=23) throw std::runtime_error("bad row");
        Row row;
        row.source.rate=unsigned_integer<std::uint32_t>(f[0]);
        row.source.anchor_counter=unsigned_integer<std::uint64_t>(f[1]);
        row.source.anchor_utc_ns=signed_integer<std::int64_t>(f[2]);
        row.source.generation=unsigned_integer<std::uint64_t>(f[3]);
        row.source.visit=unsigned_integer<std::uint64_t>(f[4]);
        row.source.window_counter=unsigned_integer<std::uint64_t>(f[5]);
        row.source.probe_index=unsigned_integer<std::uint32_t>(f[6]);
        row.source.receiver=unsigned_integer<std::uint32_t>(f[7]);
        row.source.channel=unsigned_integer<std::uint32_t>(f[8]);
        const auto upper=unsigned_integer<unsigned>(f[9]);
        if (upper>1) throw std::runtime_error("bad edge");
        row.source.upper_edge=upper!=0; row.source.actual_rf_hz=number(f[10]);
        row.source.utc_bracket_width_ns=number(f[11]);
        row.source.input_digest=f[12]; row.source.analysis_digest=f[13];
        if (unsigned_integer<unsigned>(f[14])!=1) throw std::runtime_error("unqualified row");
        row.source.continuity_qualified=true;
        row.candidate.rank=unsigned_integer<std::uint32_t>(f[15]);
        row.candidate.integer_epoch=signed_integer<std::int64_t>(f[16]);
        row.candidate.fractional_offset=number(f[17]);
        row.candidate.tracking_cfo_hz=number(f[18]);
        row.candidate.exact_score=number(f[19]); row.candidate.control_score=number(f[20]);
        row.candidate.margin=number(f[21]);
        const auto complete=unsigned_integer<unsigned>(f[22]);
        if (complete>1 || row.source.probe_index!=0 ||
            row.candidate.rank>=LEO_NATIVE_GLRT_MAX_CANDIDATES)
            throw std::runtime_error("row exceeds scanner event contract");
        row.candidate.complete=complete==1; result.push_back(std::move(row));
    }
    if (!input.eof() || result.size()!=24681) throw std::runtime_error("unexpected row count");
    return result;
}

struct Target {
    std::uint32_t target{},profile{},profile_crc32{},channel{};
    std::uint64_t tuning_frequency_hz{}; bool upper_edge{}; double actual_rf_hz{};
};

std::vector<Target> targets(const std::string& path) {
    std::ifstream input(path); std::string line;
    if (!std::getline(input,line) || fields(line).size()!=8) throw std::runtime_error("bad targets");
    std::vector<Target> result;
    while (std::getline(input,line)) {
        const auto f=fields(line); if (f.size()!=8) throw std::runtime_error("bad target row");
        Target target;
        target.target=unsigned_integer<std::uint32_t>(f[0]);
        target.profile=unsigned_integer<std::uint32_t>(f[1]);
        target.profile_crc32=unsigned_integer<std::uint32_t>(f[2]);
        if (f[3]!="historical-unavailable" || target.profile_crc32)
            throw std::runtime_error("unexpected historical profile authority");
        target.tuning_frequency_hz=unsigned_integer<std::uint64_t>(f[4]);
        target.channel=unsigned_integer<std::uint32_t>(f[5]);
        if (f[6]=="upper") target.upper_edge=true;
        else if (f[6]!="lower") throw std::runtime_error("bad target edge");
        target.actual_rf_hz=number(f[7]);
        if (target.target!=result.size()) throw std::runtime_error("bad target order");
        result.push_back(target);
    }
    if (!input.eof() || result.size()!=4) throw std::runtime_error("unexpected targets");
    return result;
}

const Target& target_for(const std::vector<Target>& values,const ProjectionSource& source) {
    const auto found=std::find_if(values.begin(),values.end(),[&](const Target& value) {
        return value.channel==source.channel && value.upper_edge==source.upper_edge &&
            value.actual_rf_hz==source.actual_rf_hz;
    });
    if (found==values.end()) throw std::runtime_error("missing target authority");
    return *found;
}

std::vector<leo_tle_record> tles(const std::string& path) {
    std::ifstream input(path); std::size_t count=0;
    if (!(input>>count) || !count || count>20000) throw std::runtime_error("bad TLE count");
    input.ignore(1024,'\n'); std::vector<leo_tle_record> result(count);
    std::unordered_set<std::int32_t> identifiers;
    for (std::size_t index=0;index<count;++index) {
        std::string one,two; std::getline(input,one); std::getline(input,two);
        std::int32_t first=0,second=0;
        if (one.size()!=69 || two.size()!=69 ||
            !location::parse_tle_catalogue_id(std::string_view(one).substr(2,5),first) ||
            !location::parse_tle_catalogue_id(std::string_view(two).substr(2,5),second) ||
            first!=second || !identifiers.insert(first).second) throw std::runtime_error("bad TLE");
        result[index].satellite_id=first;
        std::memcpy(result[index].line1,one.data(),69); std::memcpy(result[index].line2,two.data(),69);
        result[index].line1[69]=result[index].line2[69]='\0';
    }
    std::string extra; while (std::getline(input,extra)) if (!extra.empty())
        throw std::runtime_error("trailing TLE data");
    return result;
}

struct Search { double latitude{},longitude{},radius{},region{},level{}; std::uint32_t budget{}; };
Search search(const std::string& path) {
    std::ifstream input(path); std::string header,line,extra;
    if (!std::getline(input,header) || !std::getline(input,line) || std::getline(input,extra))
        throw std::runtime_error("bad search metadata");
    const auto f=fields(line); if (f.size()!=6) throw std::runtime_error("bad search row");
    return {number(f[0]),number(f[1]),number(f[2]),number(f[3]),number(f[4]),
        unsigned_integer<std::uint32_t>(f[5])};
}

struct SavedEvent {
    std::uint64_t counter{};
    leo_scanner_event event{};
    bool passing{};
    Observation projected;
};

leo_scanner_event scanner_event(const Row& row,const Target& target) {
    leo_scanner_event value{}; value.kind=LEO_SCANNER_CANDIDATE;
    value.visit=row.source.visit; value.valid_start=row.source.window_counter;
    value.valid_end=value.valid_start+static_cast<std::uint64_t>(row.source.rate)*120/1000;
    value.target=target.target; value.profile=target.profile;
    value.attested_profile_crc32=target.profile_crc32;
    value.frequency_hz=target.tuning_frequency_hz;
    value.receiver_id=static_cast<std::int32_t>(row.source.receiver);
    value.probe_index=static_cast<std::int32_t>(row.source.probe_index);
    value.candidate_index=row.candidate.rank; value.candidate.epoch=row.candidate.integer_epoch;
    value.candidate.fractional_epoch_status=row.candidate.complete ? 1 : 2;
    value.candidate.fractional_epoch_offset_samples=row.candidate.fractional_offset;
    value.candidate.fractional_tracking_cfo_hz=row.candidate.tracking_cfo_hz;
    value.candidate.fractional_exact_score=row.candidate.exact_score;
    value.candidate.fractional_control_score=row.candidate.control_score;
    value.candidate.fractional_margin=row.candidate.margin;
    return value;
}

std::vector<SavedEvent> select_events(const std::vector<Row>& all,
                                      const std::vector<Target>& metadata,bool full) {
    const auto& authority=all.front().source;
    std::int64_t first_end=std::numeric_limits<std::int64_t>::max();
    for (const auto& row:all) {
        Observation observation;
        if (project(row.source,row.candidate,observation))
            first_end=std::min(first_end,observation.support_end_utc_ns);
    }
    if (first_end==std::numeric_limits<std::int64_t>::max()) throw std::runtime_error("no evidence");
    const auto cutoff=first_end+10'000'000'000LL;
    std::vector<SavedEvent> result; result.reserve(846);
    for (const auto& row:all) {
        Observation observation; const bool passing=project(row.source,row.candidate,observation);
        const auto window_end=support_utc_ns(authority.anchor_counter,authority.anchor_utc_ns,
            row.source.window_counter,static_cast<double>(authority.rate/50),authority.rate);
        if (!full && ((passing && observation.support_end_utc_ns>cutoff) ||
                      (!passing && window_end>cutoff)))
            continue;
        result.push_back({row.source.window_counter,
            scanner_event(row,target_for(metadata,row.source)),passing,std::move(observation)});
    }
    std::stable_sort(result.begin(),result.end(),[](const SavedEvent& left,const SavedEvent& right) {
        return std::tie(left.counter,left.event.visit,left.event.receiver_id,left.event.candidate_index)<
            std::tie(right.counter,right.event.visit,right.event.receiver_id,right.event.candidate_index);
    });
    if (result.size()!=(full ? 24681U : 846U))
        throw std::runtime_error("unexpected selected event count");
    return result;
}

std::uint64_t lattice_counter(const ProjectionSource& authority,std::uint64_t counter) {
    if (counter<authority.anchor_counter) throw std::runtime_error("counter precedes authority");
    const auto period=authority.rate/std::gcd<std::uint32_t>(authority.rate,1000000000U);
    return authority.anchor_counter+(counter-authority.anchor_counter)/period*period;
}

timing::Bracket bracket(const ProjectionSource& authority,std::uint64_t requested_counter) {
    const auto counter=lattice_counter(authority,requested_counter);
    const auto ticks=counter-authority.anchor_counter;
    if (ticks>UINT64_MAX/1000000000ULL) throw std::runtime_error("counter conversion overflow");
    const auto elapsed=ticks*1000000000ULL/authority.rate;
    const auto width=static_cast<std::uint64_t>(authority.utc_bracket_width_ns);
    if (!width || static_cast<double>(width)!=authority.utc_bracket_width_ns ||
        elapsed>static_cast<std::uint64_t>(INT64_MAX-authority.anchor_utc_ns))
        throw std::runtime_error("bad bracket authority");
    const auto midpoint=authority.anchor_utc_ns+static_cast<std::int64_t>(elapsed);
    constexpr std::uint64_t monotonic_origin=1000000000ULL;
    return {monotonic_origin+elapsed-width/2,monotonic_origin+elapsed+(width-width/2),counter,
        midpoint-static_cast<std::int64_t>(width/2),
        midpoint+static_cast<std::int64_t>(width-width/2),true};
}

void verify_projection_authority(const ProjectionSource& authority,
                                 const ingest::Authority& ingest_authority,
                                 const std::vector<SavedEvent>& events,
                                 std::size_t expected_emitted) {
    timing::Timebase clock({authority.rate,1'000'000'000,600'000'000'000ULL,0,0,64});
    if (clock.begin(authority.generation)!=timing::Status::ok)
        throw std::runtime_error("cannot begin replay verification clock");
    std::uint64_t prior=UINT64_MAX; std::size_t emitted=0;
    for (const auto& saved:events) {
        const auto counter=lattice_counter(authority,saved.counter);
        if (counter!=prior) {
            if (clock.observe(bracket(authority,counter))!=timing::Status::ok)
                throw std::runtime_error("lattice bracket rejected");
            prior=counter;
        }
        Observation actual;
        const auto status=ingest::project_event(ingest_authority,clock,saved.event,actual);
        if (status!=(saved.passing ? ingest::Status::emitted : ingest::Status::nonpassing))
            throw std::runtime_error("lattice projection status mismatch");
        if (saved.passing) {
            ++emitted;
            if (actual.candidate_id!=saved.projected.candidate_id ||
                actual.source_group_id!=saved.projected.source_group_id ||
                actual.support_start_utc_ns!=saved.projected.support_start_utc_ns ||
                actual.support_center_utc_ns!=saved.projected.support_center_utc_ns ||
                actual.support_end_utc_ns!=saved.projected.support_end_utc_ns ||
                actual.moment2!=saved.projected.moment2 || actual.moment3!=saved.projected.moment3)
                throw std::runtime_error("lattice projection authority differs from persisted anchor");
        }
    }
    if (emitted!=expected_emitted) throw std::runtime_error("unexpected verified projection count");
}

AnalysisConfig configuration(const ProjectionSource& source,const std::vector<Target>& metadata,
                             const std::vector<leo_tle_record>& catalogue,const Search& location,
                             std::uint64_t publication_interval_ns) {
    ingest::Authority authority{source.generation,source.rate,source.input_digest,
        source.analysis_digest,{}};
    for (const auto& target:metadata) authority.targets.push_back({target.profile,
        target.profile_crc32,target.channel,target.tuning_frequency_hz,target.actual_rf_hz,
        target.upper_edge});
    authority.profile_authority=ingest::ProfileAuthority::historical_metadata;
    online::Config online; online.history_window_ns=600'000'000'000LL;
    online.maximum_satellites=static_cast<std::uint32_t>(catalogue.size());
    online.maximum_knots=96;
    online.maximum_orbit_bytes=catalogue.size()*96U*sizeof(leo_orbit_state)*2U;
    online.maximum_search_points=1;
    online::SearchConfig search_config{}; search_config.origin_latitude_deg=location.latitude;
    search_config.origin_longitude_deg=location.longitude;
    search_config.score=leo_score_default_config(); search_config.policy.radius_km=location.radius;
    search_config.policy.region_size_km=location.region; search_config.policy.level_count=1;
    search_config.policy.levels_km[0]=location.level; search_config.policy.budget_points=location.budget;
    return {std::move(authority),{source.rate,1'000'000'000,600'000'000'000ULL,0,0,64},online,
        {"scan-fw-3cfdaa6d75762cad",source.input_digest,source.anchor_utc_ns},catalogue,search_config,
        60'000'000'000ULL,publication_interval_ns,1,10.0,96};
}

struct Run {
    Summary summary;
    double wall_s{},producer_wall_s{},finish_tail_s{},source_span_s{};
    std::uint64_t maximum_callback_ns{},maximum_schedule_lateness_ns{};
};

struct Reference {
    std::size_t tracks{};
    online::SearchResult search;
    double wall_s{};
};

Reference synchronous_reference(const AnalysisConfig& config,
                                const std::vector<SavedEvent>& events) {
    const auto begun=Clock::now();
    online::Coordinator coordinator(config.online,config.session);
    if (coordinator.replace_stream_generation(config.authority.generation)!=online::Status::ok)
        throw std::runtime_error("reference generation failed");
    std::int64_t watermark=0; std::size_t accepted=0;
    for (const auto& saved:events) if (saved.passing) {
        watermark=std::max(watermark,saved.projected.support_end_utc_ns);
        const auto receipt=coordinator.ingest(saved.projected,watermark);
        if (receipt.status!=online::Status::ok) throw std::runtime_error("reference ingest failed");
        ++accepted;
    }
    if (accepted!=11747 || coordinator.history_capacity_evictions())
        throw std::runtime_error("reference evidence loss");
    std::shared_ptr<const online::Snapshot> snapshot;
    if (coordinator.publish(watermark,&snapshot)!=online::Status::ok || !snapshot ||
        snapshot->retained_observation_count!=accepted || snapshot->location_tracks.records.empty())
        throw std::runtime_error("reference publication failed");
    double required_first=std::numeric_limits<double>::infinity();
    double required_last=-std::numeric_limits<double>::infinity();
    for (const auto& track:snapshot->location_tracks.records) {
        required_first=std::min(required_first,
            track.times_s[0]+config.search.score.tau_first_s-config.orbit_knot_step_s);
        required_last=std::max(required_last,
            track.times_s[track.observation_count-1]+config.search.score.tau_last_s+
                config.orbit_knot_step_s);
    }
    online::OrbitBuild orbit{}; orbit.generation=1;
    orbit.start_utc_ns=config.session.session_start_utc_ns;
    orbit.knot_start_s=std::floor(required_first/config.orbit_knot_step_s)*
        config.orbit_knot_step_s;
    orbit.knot_step_s=config.orbit_knot_step_s; orbit.knot_count=config.orbit_knot_count;
    orbit.records=config.catalogue;
    if (required_last>orbit.knot_start_s+(orbit.knot_count-1)*orbit.knot_step_s ||
        coordinator.replace_orbit(orbit)!=online::Status::ok)
        throw std::runtime_error("reference orbit failed");
    online::SearchResult started{};
    if (coordinator.begin_search(snapshot->generation,config.search,&started)!=online::Status::ok)
        throw std::runtime_error("reference search begin failed");
    const auto result=coordinator.resume_search(1);
    if (result.state!=online::SearchState::complete || result.evaluated_points!=1 ||
        !result.has_incumbent) throw std::runtime_error("reference search failed");
    return {snapshot->location_tracks.records.size(),result,
        std::chrono::duration<double>(Clock::now()-begun).count()};
}

Run run(const AnalysisConfig& config,const ProjectionSource& authority,
        const std::vector<SavedEvent>& events,double pace,bool release_at_valid_end) {
    Analysis analysis(config); std::uint64_t callback_max=0;
    std::uint64_t schedule_lateness_max=0;
    std::exception_ptr producer_failure;
    const auto begun=Clock::now();
    auto producer_ended=begun;
    std::thread producer([&] {
        try {
            std::uint64_t prior=UINT64_MAX;
            const auto first_release=release_at_valid_end ?
                events.front().event.valid_end : events.front().counter;
            for (std::size_t index=0;index<events.size();) {
                const auto& first=events[index];
                std::size_t end=index+1;
                while (end<events.size() && events[end].counter==first.counter) ++end;
                const auto window_counter=lattice_counter(authority,first.counter);
                const auto release=release_at_valid_end ? first.event.valid_end : first.counter;
                if (pace>0) {
                    const long double seconds=static_cast<long double>(release-first_release)/
                        authority.rate*pace;
                    const auto deadline=begun+std::chrono::nanoseconds(
                        static_cast<std::int64_t>(seconds*1000000000.0L));
                    std::this_thread::sleep_until(deadline);
                    const auto woke=Clock::now();
                    if (woke>deadline) schedule_lateness_max=std::max(schedule_lateness_max,
                        static_cast<std::uint64_t>(std::chrono::duration_cast<
                            std::chrono::nanoseconds>(woke-deadline).count()));
                }
                // Deliver the historical pre-window bracket only when the
                // release deadline is reached. Observing it before sleeping
                // would falsely advance measured source progress into the future.
                if (window_counter!=prior) {
                    if (analysis.observe(bracket(authority,window_counter))!=timing::Status::ok)
                        throw std::runtime_error("paced pre-window timing observation failed");
                    prior=window_counter;
                }
                if (release_at_valid_end) {
                    const auto release_counter=lattice_counter(authority,release);
                    if (release_counter!=prior) {
                        if (analysis.observe(bracket(authority,release_counter))!=timing::Status::ok)
                            throw std::runtime_error("paced release timing observation failed");
                        prior=release_counter;
                    }
                }
                for (;index<end;++index) {
                    auto event=events[index].event;
                    event.detector_enqueued_monotonic_ns=static_cast<std::uint64_t>(
                        std::chrono::duration_cast<std::chrono::nanoseconds>(
                            Clock::now().time_since_epoch()).count());
                    // Persisted projection rows contain candidate science, not live
                    // detector timing. Equal synthetic timestamps attest only that
                    // this CPU replay delivers the already-computed row immediately.
                    event.detector_started_monotonic_ns=event.detector_enqueued_monotonic_ns;
                    event.detector_finished_monotonic_ns=event.detector_enqueued_monotonic_ns;
                    const auto before=Clock::now(); analysis.event(event); const auto after=Clock::now();
                    callback_max=std::max(callback_max,static_cast<std::uint64_t>(
                        std::chrono::duration_cast<std::chrono::nanoseconds>(after-before).count()));
                }
            }
            if (!release_at_valid_end) {
                const auto final_counter=events.back().counter+authority.rate;
                if (analysis.observe(bracket(authority,final_counter))!=timing::Status::ok)
                    throw std::runtime_error("final timing observation failed");
            }
            producer_ended=Clock::now();
        } catch (...) {
            producer_ended=Clock::now();
            producer_failure=std::current_exception();
        }
    });
    producer.join(); if (producer_failure) std::rethrow_exception(producer_failure);
    analysis.detach_cancel(); const auto summary=analysis.finish_after_rf_stopped();
    const auto ended=Clock::now();
    const auto first_release=release_at_valid_end ? events.front().event.valid_end : events.front().counter;
    const auto last_release=release_at_valid_end ? events.back().event.valid_end : events.back().counter;
    return {summary,std::chrono::duration<double>(ended-begun).count(),
        std::chrono::duration<double>(producer_ended-begun).count(),
        std::chrono::duration<double>(ended-producer_ended).count(),
        static_cast<double>(last_release-first_release)/authority.rate,
        callback_max,schedule_lateness_max};
}

void qualified(const Summary& value) {
    if (!value.timing_qualified || value.scanner_candidates!=846 ||
        value.accepted_candidates!=394 || value.session.projected!=394 ||
        value.session.consumed!=394 || value.session.nonpassing!=452 ||
        value.session.queue_dropped || value.session.rejected || value.session.invalid ||
        value.session.timing_unavailable || value.session.history_capacity_evictions ||
        value.publication_failures || value.search_failures ||
        !value.publications || value.orbit_builds!=1 || !value.searches_started ||
        value.last_search.state!=online::SearchState::complete ||
        value.last_search.snapshot_generation!=value.snapshot_generation ||
        value.last_search.orbit_generation!=value.orbit_generation ||
        value.last_search.evaluated_points!=1 || !value.last_search.has_incumbent ||
        value.last_search.incumbent_matched_tracks!=11 || value.last_search.incumbent_unmatched_tracks)
        throw std::runtime_error("Analysis replay was not lossless and complete: candidates="+
            std::to_string(value.scanner_candidates)+" accepted="+
            std::to_string(value.accepted_candidates)+" projected="+
            std::to_string(value.session.projected)+" consumed="+
            std::to_string(value.session.consumed)+" nonpassing="+
            std::to_string(value.session.nonpassing)+" rejected="+
            std::to_string(value.session.rejected)+" publications="+
            std::to_string(value.publications)+" orbit="+std::to_string(value.orbit_builds)+
            " searches="+std::to_string(value.searches_started)+" failures="+
            std::to_string(value.search_failures)+" state="+
            std::to_string(static_cast<unsigned>(value.last_search.state))+" evaluated="+
            std::to_string(value.last_search.evaluated_points)+" matched="+
            std::to_string(value.last_search.incumbent_matched_tracks));
}

bool full_lossless(const Summary& value) {
    return value.timing_qualified && value.scanner_candidates==24681 &&
        value.accepted_candidates==11747 && value.session.projected==11747 &&
        value.session.consumed==11747 && value.session.nonpassing==12934 &&
        !value.session.queue_dropped && !value.session.rejected && !value.session.invalid &&
        !value.session.timing_unavailable && !value.session.history_capacity_evictions &&
        !value.application_queue_overflows && !value.invalid_candidate_events &&
        !value.timing_failures && !value.publication_failures && !value.search_failures;
}

void same_science(const Summary& left,const Summary& right) {
    const auto& a=left.last_search; const auto& b=right.last_search;
    if (a.incumbent.east_km!=b.incumbent.east_km ||
        a.incumbent.north_km!=b.incumbent.north_km ||
        a.incumbent.weighted_mse_hz2!=b.incumbent.weighted_mse_hz2 ||
        a.incumbent_residual_rmse_hz!=b.incumbent_residual_rmse_hz ||
        a.incumbent_matched_tracks!=b.incumbent_matched_tracks ||
        a.incumbent_unmatched_tracks!=b.incumbent_unmatched_tracks ||
        a.incumbent_evaluated_satellite_tracks!=b.incumbent_evaluated_satellite_tracks ||
        a.incumbent_rejected_satellite_tracks!=b.incumbent_rejected_satellite_tracks)
        throw std::runtime_error("paced and unpaced scientific results differ");
}
} // namespace

int main(int argc,char** argv) {
    try {
        std::uint32_t analysis_workers=1;
        std::size_t exact_score_cache_bytes=0;
        bool workers_seen=false,cache_seen=false;
        while (argc>=3) {
            const std::string option=argv[argc-2];
            if (option=="--analysis-workers") {
                if (workers_seen) throw std::runtime_error("duplicate analysis worker option");
                analysis_workers=unsigned_integer<std::uint32_t>(argv[argc-1]);
                workers_seen=true; argc-=2;
            } else if (option=="--exact-score-cache-bytes") {
                if (cache_seen) throw std::runtime_error("duplicate exact score cache option");
                exact_score_cache_bytes=unsigned_integer<std::size_t>(argv[argc-1]);
                if (exact_score_cache_bytes!=0 && exact_score_cache_bytes!=6U*1024U*1024U)
                    throw std::runtime_error("exact score cache must be zero or 6291456 bytes");
                cache_seen=true; argc-=2;
            } else break;
        }
        application::ExecutionBudget{analysis_workers,0,analysis_workers}.validate(
            application::ExecutionMode::replay);
        if (argc!=6 && argc!=7) throw std::runtime_error(
            "usage: test-paced-analysis PROJECTION TARGETS TLES SEARCH [prefix|full-reference|full-continuous|full-coalesced|full-pinned-coalesced] PACE_SCALE [--analysis-workers 1..4] [--exact-score-cache-bytes 0|6291456]");
        const std::string mode=argc==6 ? "prefix" : argv[5];
        if (mode!="prefix" && mode!="full-reference" && mode!="full-continuous" &&
            mode!="full-coalesced" && mode!="full-pinned-coalesced")
            throw std::runtime_error("bad replay mode");
        if (mode=="full-reference" && analysis_workers!=1)
            throw std::runtime_error("reference control is serial");
        if (mode=="full-reference" && exact_score_cache_bytes)
            throw std::runtime_error("reference control does not use the score cache");
        const double pace=number(argv[argc-1]);
        if (pace<0 || pace>1 || ((mode=="full-continuous" || mode=="full-coalesced" ||
            mode=="full-pinned-coalesced") &&
            pace<=0) || (mode=="full-reference" && pace!=0))
            throw std::runtime_error("bad pace");
        const bool full=mode!="prefix";
        const auto all=rows(argv[1]); const auto metadata=targets(argv[2]);
        const auto catalogue=tles(argv[3]); const auto location=search(argv[4]);
        if (catalogue.size()!=11129 || location.budget!=1) throw std::runtime_error("bad DS9 fixture");
        const auto events=select_events(all,metadata,full);
        const std::uint64_t publication_interval=
            (mode=="full-coalesced" || mode=="full-pinned-coalesced") ?
            600'000'000'000ULL : 5'000'000'000ULL;
        auto config=configuration(all.front().source,metadata,catalogue,location,
            publication_interval);
        config.analysis_workers=analysis_workers;
        config.online.maximum_exact_score_cache_bytes=exact_score_cache_bytes;
        if (mode=="full-pinned-coalesced") {
            config.online.publication_search_policy=
                online::PublicationSearchPolicy::pin_started_snapshot;
        }
        verify_projection_authority(all.front().source,config.authority,events,
            full ? 11747U : 394U);
        Reference reference{};
        if (mode=="full-reference") {
            reference=synchronous_reference(config,events);
            rusage usage{};
            if (getrusage(RUSAGE_SELF,&usage)) throw std::runtime_error("getrusage failed");
            const auto process_hwm=process_status_kib("VmHWM:");
            const auto process_rss=process_status_kib("VmRSS:");
            std::cout<<"{\"schema\":\"leo-paced-analysis-reference/v1\","
                "\"scope\":\"synchronous-public-coordinator-no-iq-no-detector-no-rf\","
                "\"mode\":\"full-reference\",\"source_rows\":"<<all.size()
                <<",\"event_rows\":"<<events.size()<<",\"accepted_observations\":11747,"
                "\"tracks\":"<<reference.tracks<<",\"matched_tracks\":"
                <<reference.search.incumbent_matched_tracks<<",\"unmatched_tracks\":"
                <<reference.search.incumbent_unmatched_tracks<<",\"catalogue_records\":"
                <<catalogue.size()<<",\"weighted_mse_hz2\":"<<std::setprecision(17)
                <<reference.search.incumbent.weighted_mse_hz2<<",\"wall_seconds\":"
                <<reference.wall_s<<",\"getrusage_maxrss_kib\":"<<usage.ru_maxrss
                <<",\"process_vm_hwm_kib\":"<<process_hwm
                <<",\"process_vm_rss_kib\":"<<process_rss
                <<",\"full_600s_evidence_span_exercised\":false}\n";
            return 0;
        }
        Run unpaced{};
        if (!full) unpaced=run(config,all.front().source,events,0,false);
        const auto paced=run(config,all.front().source,events,pace,full);
        if (!full) {
            qualified(unpaced.summary); qualified(paced.summary);
            same_science(unpaced.summary,paced.summary);
        }
        const bool lossless=full ? full_lossless(paced.summary) : true;
        const bool search_complete=paced.summary.last_search.state==online::SearchState::complete &&
            paced.summary.last_search.evaluated_points==1 && paced.summary.last_search.has_incumbent;
        const bool searches_settled=paced.summary.searches_started>0 &&
            paced.summary.searches_complete==paced.summary.searches_started &&
            paced.summary.result_source_age_count==paced.summary.searches_complete &&
            !paced.summary.search_pending && !paced.summary.searches_stale;
        const bool reference_exact=!full || (search_complete &&
            paced.summary.last_search.incumbent_matched_tracks+
                paced.summary.last_search.incumbent_unmatched_tracks==64 &&
            paced.summary.last_search.incumbent_matched_tracks==64 &&
            paced.summary.last_search.incumbent_unmatched_tracks==0 &&
            std::abs(std::sqrt(paced.summary.last_search.incumbent.weighted_mse_hz2)-
                std::sqrt(full_reference_mse_hz2))<=full_reference_rmse_tolerance_hz);
        constexpr std::uint64_t freshness_budget_ns=5'000'000'000ULL;
        const bool freshness_qualified=mode=="full-continuous" &&
            searches_settled &&
            paced.summary.publication_cadence_requests>0 &&
            paced.summary.publication_cadence_requests==
                paced.summary.publication_cadence_serviced+
                paced.summary.publication_cadence_misses+
                static_cast<std::uint64_t>(paced.summary.publication_cadence_pending) &&
            !paced.summary.publication_cadence_pending &&
            paced.summary.result_source_age_count>0 &&
            paced.summary.publication_cadence_misses==0 &&
            paced.summary.publication_lag_max_ns<=freshness_budget_ns &&
            paced.summary.snapshot_source_age_upper_max_ns<=freshness_budget_ns &&
            paced.summary.result_source_age_upper_max_ns<=freshness_budget_ns &&
            paced.summary.snapshot_result_duration_max_ns<=freshness_budget_ns &&
            paced.finish_tail_s<=static_cast<double>(freshness_budget_ns)/1e9 &&
            paced.producer_wall_s<=paced.source_span_s*pace+
                static_cast<double>(freshness_budget_ns)/1e9 &&
            paced.maximum_callback_ns<=freshness_budget_ns &&
            paced.maximum_schedule_lateness_ns<=freshness_budget_ns;
        const auto& cache=paced.summary.exact_score_cache;
        const bool cache_telemetry_valid=
            cache.enabled==(exact_score_cache_bytes!=0) &&
            cache.retained_payload_bytes<=exact_score_cache_bytes;
        const bool cache_reuse_exercised=cache.track_hits>0 && cache.track_misses>0;
        const bool cache_reuse_qualified=
            mode!="full-continuous" || !cache.enabled || cache_reuse_exercised;
        const bool qualified_run=!full || (lossless && search_complete && reference_exact &&
            cache_telemetry_valid && cache_reuse_qualified && searches_settled &&
            (mode=="full-coalesced" ||
                mode=="full-pinned-coalesced" || freshness_qualified));
        rusage usage{}; if (getrusage(RUSAGE_SELF,&usage)) throw std::runtime_error("getrusage failed");
        const auto process_hwm=process_status_kib("VmHWM:");
        const auto process_rss=process_status_kib("VmRSS:");
        std::cout<<"{\"schema\":\"leo-paced-analysis-replay/v4\",\"scope\":"
            "\"persisted-projected-events-no-iq-no-detector-no-rf\",\"mode\":\""<<mode
            <<"\",\"publication_search_policy\":\""
            <<(config.online.publication_search_policy==
                online::PublicationSearchPolicy::pin_started_snapshot ?
                "pin_started_snapshot":"invalidate_on_publish")
            <<"\",\"analysis_workers\":"<<analysis_workers
            <<",\"detector_workers\":0,\"configured_cpu_lanes\":"<<analysis_workers
            <<",\"exact_score_cache_budget_bytes\":"<<exact_score_cache_bytes
            <<",\"exact_score_cache_enabled\":"<<(cache.enabled?"true":"false")
            <<",\"exact_score_cache_track_hits\":"<<cache.track_hits
            <<",\"exact_score_cache_track_misses\":"<<cache.track_misses
            <<",\"exact_score_cache_cold_fallback_points\":"<<cache.cold_fallback_points
            <<",\"exact_score_cache_retained_sites\":"<<cache.retained_sites
            <<",\"exact_score_cache_retained_payload_bytes\":"
            <<cache.retained_payload_bytes
            <<",\"source_rows\":"<<all.size()
            <<",\"event_rows\":"<<events.size()<<",\"accepted_observations\":"
            <<paced.summary.accepted_candidates<<",\"tracks_matched\":"
            <<paced.summary.last_search.incumbent_matched_tracks<<",\"catalogue_records\":"
            <<catalogue.size()<<",\"history_seconds\":600,\"orbit_knot_step_seconds\":10,"
            "\"orbit_knot_count\":96,\"pace_scale\":"<<std::setprecision(17)<<pace
            <<",\"unpaced_wall_seconds\":"<<unpaced.wall_s<<",\"paced_wall_seconds\":"
            <<paced.wall_s<<",\"source_span_seconds\":"<<paced.source_span_s
            <<",\"planned_producer_wall_seconds\":"<<paced.source_span_s*pace
            <<",\"producer_wall_seconds\":"<<paced.producer_wall_s
            <<",\"producer_finish_tail_seconds\":"<<paced.finish_tail_s
            <<",\"maximum_schedule_lateness_ns\":"<<paced.maximum_schedule_lateness_ns
            <<",\"paced_callback_max_ns\":"<<paced.maximum_callback_ns
            <<",\"queue_high_water\":"<<paced.summary.session.high_water
            <<",\"queue_dropped\":"<<paced.summary.session.queue_dropped
            <<",\"history_capacity_evictions\":"
            <<paced.summary.session.history_capacity_evictions
            <<",\"publications\":"<<paced.summary.publications
            <<",\"publication_failures\":"<<paced.summary.publication_failures
            <<",\"publication_cadence_requests\":"
            <<paced.summary.publication_cadence_requests
            <<",\"publication_cadence_serviced\":"
            <<paced.summary.publication_cadence_serviced
            <<",\"publication_cadence_misses\":"
            <<paced.summary.publication_cadence_misses
            <<",\"publication_cadence_pending\":"
            <<(paced.summary.publication_cadence_pending?"true":"false")
            <<",\"publication_compute_count\":"<<paced.summary.publication_compute_count
            <<",\"publication_compute_total_ns\":"
            <<paced.summary.publication_compute_total_ns
            <<",\"publication_compute_max_ns\":"<<paced.summary.publication_compute_max_ns
            <<",\"publication_lag_current_ns\":"<<paced.summary.publication_lag_current_ns
            <<",\"publication_lag_max_ns\":"<<paced.summary.publication_lag_max_ns
            <<",\"snapshot_source_age_upper_max_ns\":"
            <<paced.summary.snapshot_source_age_upper_max_ns
            <<",\"result_source_age_upper_max_ns\":"
            <<paced.summary.result_source_age_upper_max_ns
            <<",\"snapshot_result_duration_max_ns\":"
            <<paced.summary.snapshot_result_duration_max_ns
            <<",\"latest_measured_source_progress_utc_before_ns\":"
            <<paced.summary.latest_measured_source_progress_utc_before_ns
            <<",\"latest_causal_frontier_utc_ns\":"
            <<paced.summary.latest_causal_frontier_utc_ns
            <<",\"last_snapshot_watermark_utc_ns\":"
            <<paced.summary.last_snapshot_watermark_utc_ns
            <<",\"last_result_snapshot_watermark_utc_ns\":"
            <<paced.summary.last_result_snapshot_watermark_utc_ns
            <<",\"searches_started\":"<<paced.summary.searches_started
            <<",\"searches_complete\":"<<paced.summary.searches_complete
            <<",\"searches_stale\":"<<paced.summary.searches_stale
            <<",\"search_pending\":"<<(paced.summary.search_pending?"true":"false")
            <<",\"search_failures\":"<<paced.summary.search_failures
            <<",\"reference_evaluated_in_process\":false"
            <<",\"reference_tracks\":64,\"reference_weighted_mse_hz2\":"
            <<full_reference_mse_hz2
            <<",\"reference_rmse_tolerance_hz\":"<<full_reference_rmse_tolerance_hz
            <<",\"frozen_reference_shape_exact\":"<<(reference_exact?"true":"false")
            <<",\"weighted_mse_hz2\":"<<paced.summary.last_search.incumbent.weighted_mse_hz2
            <<",\"getrusage_maxrss_kib\":"<<usage.ru_maxrss
            <<",\"process_vm_hwm_kib\":"<<process_hwm
            <<",\"process_vm_rss_kib\":"<<process_rss
            <<",\"paired_unpaced_comparison_performed\":"<<(full?"false":"true")
            <<",\"paced_unpaced_science_exact\":"<<(full?"null":"true")<<','
            <<"\"available_evidence_span_seconds\":299.8017789333333,"
            "\"lossless\":"<<(lossless?"true":"false")
            <<",\"search_complete\":"<<(search_complete?"true":"false")
            <<",\"searches_settled\":"<<(searches_settled?"true":"false")
            <<",\"freshness_budget_ns\":"<<freshness_budget_ns
            <<",\"freshness_qualified\":"<<(freshness_qualified?"true":"false")
            <<",\"cache_telemetry_valid\":"<<(cache_telemetry_valid?"true":"false")
            <<",\"cache_reuse_exercised\":"<<(cache_reuse_exercised?"true":"false")
            <<",\"cache_reuse_qualified\":"<<(cache_reuse_qualified?"true":"false")
            <<",\"qualified\":"<<(qualified_run?"true":"false")
            <<",\"continuous_qualification_claimed\":"
            <<(mode=="full-continuous" && qualified_run ? "true":"false")
            <<",\"coalesced_boundary_only\":"
            <<((mode=="full-coalesced" || mode=="full-pinned-coalesced")?"true":"false")
            <<",\"full_600s_evidence_span_exercised\":false}\n";
        return qualified_run ? 0 : 4;
    } catch (const std::exception& error) {
        std::cerr<<error.what()<<'\n'; return 1;
    }
}
