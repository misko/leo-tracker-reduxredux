#include "session.hpp"
#include "../location/tle_id.hpp"

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace {
using namespace leo::adaptive;

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
    errno=0; char* end=nullptr;
    const auto value=std::strtoull(text.c_str(),&end,10);
    if (errno || end!=text.c_str()+text.size() || value>std::numeric_limits<T>::max())
        throw std::runtime_error("invalid unsigned integer");
    return static_cast<T>(value);
}

template<class T> T signed_integer(const std::string& text) {
    static_assert(std::numeric_limits<T>::is_integer && std::numeric_limits<T>::is_signed);
    if (text.empty()) throw std::runtime_error("invalid signed integer");
    errno=0; char* end=nullptr;
    const auto value=std::strtoll(text.c_str(),&end,10);
    if (errno || end!=text.c_str()+text.size() || value<std::numeric_limits<T>::min() ||
        value>std::numeric_limits<T>::max())
        throw std::runtime_error("invalid signed integer");
    return static_cast<T>(value);
}

double number(const std::string& text) {
    if (text.empty()) throw std::runtime_error("invalid finite number");
    errno=0; char* end=nullptr; const double value=std::strtod(text.c_str(),&end);
    if (errno || end!=text.c_str()+text.size() || !std::isfinite(value))
        throw std::runtime_error("invalid finite number");
    return value;
}

struct Row {
    ProjectionSource source;
    FractionalCandidate candidate;
};

using SteadyClock=std::chrono::steady_clock;
double milliseconds(SteadyClock::time_point begin,SteadyClock::time_point end) {
    return std::chrono::duration<double,std::milli>(end-begin).count();
}

std::vector<Row> projection_rows(const std::string& path) {
    std::ifstream input(path); if (!input) throw std::runtime_error("cannot open projection input");
    std::vector<Row> result; result.reserve(24681);
    std::string line; std::size_t line_number=0;
    while (std::getline(input,line)) {
        if (line.size()>4096 || result.size()>=25000)
            throw std::runtime_error("oversized projection input");
        ++line_number; const auto f=fields(line);
        if (f.size()!=23) throw std::runtime_error("bad projection row "+std::to_string(line_number));
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
        if (upper>1) throw std::runtime_error("invalid edge boolean");
        row.source.upper_edge=upper!=0;
        row.source.actual_rf_hz=number(f[10]);
        row.source.utc_bracket_width_ns=number(f[11]);
        row.source.input_digest=f[12]; row.source.analysis_digest=f[13];
        const auto qualified=unsigned_integer<unsigned>(f[14]);
        if (qualified!=1) throw std::runtime_error("unqualified historical source");
        row.source.continuity_qualified=true;
        row.candidate.rank=unsigned_integer<std::uint32_t>(f[15]);
        row.candidate.integer_epoch=signed_integer<std::int64_t>(f[16]);
        row.candidate.fractional_offset=number(f[17]);
        row.candidate.tracking_cfo_hz=number(f[18]);
        row.candidate.exact_score=number(f[19]);
        row.candidate.control_score=number(f[20]);
        row.candidate.margin=number(f[21]);
        const auto complete=unsigned_integer<unsigned>(f[22]);
        if (complete>1) throw std::runtime_error("invalid complete boolean");
        row.candidate.complete=complete==1;
        if (!row.source.continuity_qualified || row.source.probe_index!=0)
            throw std::runtime_error("DS9 replay requires qualified one-probe rows");
        if (row.candidate.rank>=LEO_NATIVE_GLRT_MAX_CANDIDATES ||
            row.candidate.integer_epoch<std::numeric_limits<std::int32_t>::min() ||
            row.candidate.integer_epoch>std::numeric_limits<std::int32_t>::max())
            throw std::runtime_error("candidate field exceeds scanner ABI");
        result.push_back(std::move(row));
    }
    if (!input.eof() || result.size()!=24681)
        throw std::runtime_error("unexpected DS9 projection input count");
    return result;
}

struct TargetMetadata {
    std::uint32_t target{},profile{},profile_crc32{},channel{};
    std::uint64_t tuning_frequency_hz{};
    bool upper_edge{};
    double actual_rf_hz{};
};

std::vector<TargetMetadata> targets(const std::string& path) {
    std::ifstream input(path); if (!input) throw std::runtime_error("cannot open target metadata");
    std::string line; if (!std::getline(input,line) || fields(line).size()!=8)
        throw std::runtime_error("bad target header");
    std::vector<TargetMetadata> result;
    while (std::getline(input,line)) {
        if (line.size()>1024 || result.size()>=LEO_SCANNER_MAX_TARGETS)
            throw std::runtime_error("oversized target metadata");
        const auto f=fields(line); if (f.size()!=8) throw std::runtime_error("bad target row");
        TargetMetadata t;
        t.target=unsigned_integer<std::uint32_t>(f[0]);
        t.profile=unsigned_integer<std::uint32_t>(f[1]);
        t.profile_crc32=unsigned_integer<std::uint32_t>(f[2]);
        if (f[3]!="historical-unavailable" || t.profile_crc32!=0)
            throw std::runtime_error("unexpected historical CRC authority");
        t.tuning_frequency_hz=unsigned_integer<std::uint64_t>(f[4]);
        t.channel=unsigned_integer<std::uint32_t>(f[5]);
        if (f[6]=="upper") t.upper_edge=true;
        else if (f[6]!="lower") throw std::runtime_error("invalid target edge");
        t.actual_rf_hz=number(f[7]);
        if (t.target!=result.size() || t.channel<1 || t.channel>4 ||
            t.actual_rf_hz<=0 || !t.tuning_frequency_hz)
            throw std::runtime_error("invalid target metadata");
        result.push_back(t);
    }
    if (!input.eof() || result.size()!=4) throw std::runtime_error("unexpected target metadata count");
    return result;
}

const TargetMetadata& target_for(const std::vector<TargetMetadata>& all,
                                 const ProjectionSource& source) {
    const auto found=std::find_if(all.begin(),all.end(),[&](const auto& target) {
        return target.channel==source.channel && target.upper_edge==source.upper_edge &&
            target.actual_rf_hz==source.actual_rf_hz;
    });
    if (found==all.end()) throw std::runtime_error("projection row has no target authority");
    return *found;
}

leo_scanner_event event(const Row& row,const TargetMetadata& target) {
    leo_scanner_event e{}; e.kind=LEO_SCANNER_CANDIDATE;
    e.visit=row.source.visit; e.valid_start=row.source.window_counter;
    const auto duration=static_cast<std::uint64_t>(row.source.rate)*120/1000;
    if (duration>UINT64_MAX-e.valid_start) throw std::runtime_error("event counter overflow");
    e.valid_end=e.valid_start+duration;
    e.target=target.target; e.profile=target.profile;
    e.attested_profile_crc32=target.profile_crc32;
    e.frequency_hz=target.tuning_frequency_hz;
    e.receiver_id=static_cast<std::int32_t>(row.source.receiver);
    e.probe_index=static_cast<std::int32_t>(row.source.probe_index);
    e.candidate_index=row.candidate.rank;
    e.candidate.epoch=row.candidate.integer_epoch;
    e.candidate.fractional_epoch_status=row.candidate.complete ? 1 : 2;
    e.candidate.fractional_epoch_offset_samples=row.candidate.fractional_offset;
    e.candidate.fractional_tracking_cfo_hz=row.candidate.tracking_cfo_hz;
    e.candidate.fractional_exact_score=row.candidate.exact_score;
    e.candidate.fractional_control_score=row.candidate.control_score;
    e.candidate.fractional_margin=row.candidate.margin;
    return e;
}

std::vector<tracking::Candidate> reference_prefix(const std::string& path,
                                                   std::int64_t cutoff) {
    std::ifstream input(path); if (!input) throw std::runtime_error("cannot open candidate reference");
    std::string line; if (!std::getline(input,line)) throw std::runtime_error("missing candidate header");
    std::vector<tracking::Candidate> result; std::size_t records=0;
    while (std::getline(input,line)) {
        if (line.size()>4096 || ++records>12000)
            throw std::runtime_error("oversized candidate reference");
        const auto f=fields(line); if (f.size()!=13) throw std::runtime_error("bad candidate reference");
        tracking::Candidate c{f[0],f[1],signed_integer<int>(f[2]),signed_integer<int>(f[3]),f[4],
            number(f[5]),signed_integer<std::int64_t>(f[6]),signed_integer<std::int64_t>(f[7]),
            signed_integer<std::int64_t>(f[8]),number(f[9]),number(f[10]),number(f[11]),number(f[12])};
        if (c.support_end_utc_ns<=cutoff) result.push_back(std::move(c));
    }
    if (!input.eof() || records!=11747)
        throw std::runtime_error("unexpected candidate reference count");
    std::sort(result.begin(),result.end(),[](const auto& a,const auto& b) {
        return std::tie(a.support_end_utc_ns,a.candidate_id)<
            std::tie(b.support_end_utc_ns,b.candidate_id);
    });
    return result;
}

std::vector<leo_tle_record> tles(const std::string& path,std::size_t limit) {
    std::ifstream input(path); std::size_t count=0;
    if (!(input>>count)) throw std::runtime_error("cannot read TLE count");
    if (!count || count>limit) throw std::runtime_error("TLE catalogue exceeds bound");
    input.ignore(1024,'\n');
    std::vector<leo_tle_record> result(count);
    std::unordered_set<std::int32_t> identifiers;
    for (std::size_t index=0;index<count;++index) {
        std::string one,two; std::getline(input,one); std::getline(input,two);
        if (one.size()!=69 || two.size()!=69 || one[0]!='1' || two[0]!='2')
            throw std::runtime_error("bad TLE record");
        std::int32_t id=0,second_id=0;
        if (!location::parse_tle_catalogue_id(std::string_view(one).substr(2,5),id) ||
            !location::parse_tle_catalogue_id(std::string_view(two).substr(2,5),second_id) ||
            id!=second_id || !identifiers.insert(id).second)
            throw std::runtime_error("inconsistent TLE satellite id");
        result[index].satellite_id=id;
        std::memcpy(result[index].line1,one.data(),69);
        std::memcpy(result[index].line2,two.data(),69);
        result[index].line1[69]=result[index].line2[69]='\0';
    }
    std::string extra;
    while (std::getline(input,extra))
        if (!extra.empty()) throw std::runtime_error("trailing TLE catalogue data");
    return result;
}

struct SearchMetadata {
    double latitude{},longitude{},radius{},region{},level{};
    std::uint32_t budget{};
};

SearchMetadata search_metadata(const std::string& path) {
    std::ifstream input(path); std::string header,line,extra;
    if (!std::getline(input,header) || fields(header).size()!=6 ||
        !std::getline(input,line) || std::getline(input,extra))
        throw std::runtime_error("invalid search metadata shape");
    const auto f=fields(line); if (f.size()!=6) throw std::runtime_error("invalid search metadata");
    SearchMetadata result{number(f[0]),number(f[1]),number(f[2]),number(f[3]),number(f[4]),
        unsigned_integer<std::uint32_t>(f[5])};
    if (result.latitude<-90 || result.latitude>90 || result.longitude<-180 ||
        result.longitude>180 || result.radius<=0 || result.region<=0 ||
        result.level<=0 || result.budget!=1)
        throw std::runtime_error("search metadata outside bounded replay contract");
    return result;
}

std::string double_bits(double value) {
    std::uint64_t bits=0; static_assert(sizeof(bits)==sizeof(value));
    std::memcpy(&bits,&value,sizeof(bits));
    std::ostringstream output; output<<std::hex<<std::setw(16)<<std::setfill('0')<<bits;
    return output.str();
}

void write_diagnostics(const std::string& path,const online::Snapshot& snapshot,
                       const std::unordered_map<std::string,Observation>& observations) {
    std::ofstream output(path,std::ios::trunc);
    if (!output) throw std::runtime_error("cannot open replay diagnostic");
    output<<"track_index\ttracklet_id\tsupport_digest\tpartition_seed\tpoint_index\t"
        "candidate_id\tobservation_id\tsupport_start_utc_ns\tsupport_center_utc_ns\t"
        "support_end_utc_ns\tmoment2\tmoment2_bits\tmoment3\tmoment3_bits\ttraining\t"
        "time_s\tmeasured_hz\n"<<std::setprecision(std::numeric_limits<double>::max_digits10);
    if (snapshot.tracking_result.tracks.size()!=snapshot.location_tracks.owned.size())
        throw std::runtime_error("diagnostic track ownership mismatch");
    for (std::size_t track_index=0;track_index<snapshot.tracking_result.tracks.size();++track_index) {
        const auto& track=snapshot.tracking_result.tracks[track_index];
        const auto& owned=snapshot.location_tracks.owned[track_index];
        if (track.tracklet_id!=owned.tracklet_id || track.points.size()!=owned.observation_ids.size() ||
            track.points.size()!=owned.training_mask.size() ||
            track.points.size()!=owned.times_s.size() || track.points.size()!=owned.measured_hz.size())
            throw std::runtime_error("diagnostic point ownership mismatch");
        for (std::size_t point=0;point<track.points.size();++point) {
            const auto found=observations.find(track.points[point].candidate_id);
            if (found==observations.end()) throw std::runtime_error("diagnostic observation missing");
            const auto& observation=found->second;
            output<<track_index<<'\t'<<owned.tracklet_id<<'\t'<<owned.support_digest<<'\t'
                <<owned.partition_seed<<'\t'<<point<<'\t'<<observation.candidate_id<<'\t'
                <<owned.observation_ids[point]<<'\t'<<observation.support_start_utc_ns<<'\t'
                <<observation.support_center_utc_ns<<'\t'<<observation.support_end_utc_ns<<'\t'
                <<observation.moment2<<'\t'<<double_bits(observation.moment2)<<'\t'
                <<observation.moment3<<'\t'<<double_bits(observation.moment3)<<'\t'
                <<static_cast<unsigned>(owned.training_mask[point])<<'\t'
                <<owned.times_s[point]<<'\t'<<owned.measured_hz[point]<<'\n';
        }
    }
    if (!output) throw std::runtime_error("replay diagnostic write failed");
}

} // namespace

int main(int argc,char** argv) {
    try {
        const auto total_begin=SteadyClock::now();
        if (argc!=6 && argc!=7) throw std::runtime_error(
            "usage: leo-recorded-replay PROJECTION_INPUTS TARGETS TLES REFERENCE_CANDIDATES SEARCH_METADATA [DIAGNOSTIC_TSV]");
        const auto rows=projection_rows(argv[1]); const auto metadata=targets(argv[2]);
        const auto catalogue=tles(argv[3],20000);
        const auto location=search_metadata(argv[5]);
        const auto& first=rows.front().source;
        for (const auto& row:rows) {
            if (row.source.rate!=first.rate || row.source.anchor_counter!=first.anchor_counter ||
                row.source.anchor_utc_ns!=first.anchor_utc_ns ||
                row.source.utc_bracket_width_ns!=first.utc_bracket_width_ns ||
                row.source.generation!=first.generation ||
                row.source.input_digest!=first.input_digest ||
                row.source.analysis_digest!=first.analysis_digest)
                throw std::runtime_error("mixed projection authority");
            (void)target_for(metadata,row.source);
        }
        const auto load_validate_end=SteadyClock::now();

        struct SelectedRow {
            std::size_t row{};
            bool passing{};
            Observation projected;
        };
        std::int64_t first_end=std::numeric_limits<std::int64_t>::max();
        for (const auto& row:rows) {
            Observation observation;
            if (project(row.source,row.candidate,observation))
                first_end=std::min(first_end,observation.support_end_utc_ns);
        }
        if (first_end==std::numeric_limits<std::int64_t>::max())
            throw std::runtime_error("no projected observations");
        const std::int64_t cutoff=first_end+10'000'000'000LL;
        std::vector<SelectedRow> selected; selected.reserve(846);
        for (std::size_t index=0;index<rows.size();++index) {
            const auto& row=rows[index];
            Observation projected; const bool passing=project(row.source,row.candidate,projected);
            const auto window_end=support_utc_ns(first.anchor_counter,first.anchor_utc_ns,
                row.source.window_counter,static_cast<double>(first.rate/50),first.rate);
            if ((passing && projected.support_end_utc_ns>cutoff) || (!passing && window_end>cutoff))
                continue;
            selected.push_back({index,passing,std::move(projected)});
        }
        const auto prefix_projection_end=SteadyClock::now();

        ingest::Authority authority{first.generation,first.rate,first.input_digest,
            first.analysis_digest,{}};
        for (const auto& target:metadata)
            authority.targets.push_back({target.profile,target.profile_crc32,target.channel,
                target.tuning_frequency_hz,target.actual_rf_hz,target.upper_edge});
        authority.profile_authority=ingest::ProfileAuthority::historical_metadata;
        online::Config online_config;
        online_config.maximum_satellites=static_cast<std::uint32_t>(catalogue.size());
        online_config.maximum_knots=32;
        online_config.maximum_orbit_bytes=catalogue.size()*32U*sizeof(leo_orbit_state)*2U;
        const auto width=static_cast<std::uint64_t>(first.utc_bracket_width_ns);
        if (static_cast<double>(width)!=first.utc_bracket_width_ns || !width || width>1'000'000'000)
            throw std::runtime_error("invalid persisted bracket width");
        application::Session session(authority,
            {first.rate,1'000'000'000,600'000'000'000ULL,0,0,8},online_config,
            {"scan-fw-3cfdaa6d75762cad",first.input_digest,first.anchor_utc_ns},64);
        const auto utc_before=first.anchor_utc_ns-static_cast<std::int64_t>(width/2);
        if (session.observe({1,1+width,first.anchor_counter,utc_before,
                utc_before+static_cast<std::int64_t>(width),true})!=timing::Status::ok)
            throw std::runtime_error("historical bracket rejected");
        std::unordered_map<std::string,Observation> diagnostic_observations;
        diagnostic_observations.reserve(394);
        for (const auto& item:selected) {
            const auto& row=rows[item.row];
            const auto accepted=session.accept(event(row,target_for(metadata,row.source)));
            if (accepted.projection!=(item.passing ? ingest::Status::emitted : ingest::Status::nonpassing) ||
                (item.passing && !accepted.queued))
                throw std::runtime_error("session projection differs at row "+
                    std::to_string(item.row+1)+" status "+
                    std::to_string(static_cast<int>(accepted.projection)));
            if (item.passing && !diagnostic_observations.emplace(
                    item.projected.candidate_id,item.projected).second)
                throw std::runtime_error("duplicate projected diagnostic identity");
            if (session.stats().queued>=64 && session.consume(32)!=32)
                throw std::runtime_error("bounded consume failed");
        }
        while (session.stats().queued) session.consume(64);
        const auto stats=session.stats();
        const auto ingress_drain_end=SteadyClock::now();

        std::shared_ptr<const online::Snapshot> snapshot;
        if (session.publish(&snapshot)!=online::Status::ok || !snapshot)
            throw std::runtime_error("prefix publication failed");
        const auto publish_end=SteadyClock::now();

        /* This saved output is diagnostic only. It never enters Session or
         * native reconstruction; it checks the resulting track memberships. */
        const auto reference=reference_prefix(argv[4],cutoff);
        const auto expected=tracking::reconstruct(reference);
        const auto comparison=online::compare_reference(*snapshot,expected);
        if (reference.size()!=394 || stats.projected!=394 || stats.consumed!=394 ||
            stats.queue_dropped || stats.rejected || stats.invalid || stats.timing_unavailable ||
            snapshot->tracking_result.tracks.size()!=11 || !comparison.exact)
            throw std::runtime_error("DS9 Session prefix differs: reference="+
                std::to_string(reference.size())+" projected="+std::to_string(stats.projected)+
                " consumed="+std::to_string(stats.consumed)+" dropped="+
                std::to_string(stats.queue_dropped)+" rejected="+std::to_string(stats.rejected)+
                " invalid="+std::to_string(stats.invalid)+" timing="+
                std::to_string(stats.timing_unavailable)+" tracks="+
                std::to_string(snapshot->tracking_result.tracks.size())+" exact="+
                std::to_string(comparison.exact)+" mismatched_tracks="+
                std::to_string(comparison.mismatched_tracks)+" mismatched_points="+
                std::to_string(comparison.mismatched_points));
        if (argc==7) write_diagnostics(argv[6],*snapshot,diagnostic_observations);
        const auto reference_diagnostic_end=SteadyClock::now();

        online::OrbitBuild orbit{}; orbit.generation=1;
        orbit.start_utc_ns=first.anchor_utc_ns; orbit.knot_start_s=-10;
        orbit.knot_step_s=1; orbit.knot_count=32; orbit.records=catalogue;
        if (orbit.records.size()!=11129 || session.replace_orbit(orbit)!=online::Status::ok)
            throw std::runtime_error("bounded complete-catalogue orbit failed");
        const auto orbit_build_end=SteadyClock::now();

        online::SearchConfig search{}; search.origin_latitude_deg=location.latitude;
        search.origin_longitude_deg=location.longitude; search.score=leo_score_default_config();
        search.policy.radius_km=location.radius; search.policy.region_size_km=location.region;
        search.policy.level_count=1; search.policy.levels_km[0]=location.level;
        search.policy.budget_points=location.budget;
        online::SearchResult started{};
        if (session.begin_search(snapshot->generation,search,&started)!=online::Status::ok)
            throw std::runtime_error("bounded search did not begin");
        const auto search_begin_end=SteadyClock::now();
        const auto scored=session.resume_search(1);
        if (scored.state!=online::SearchState::complete || scored.evaluated_points!=1 ||
            !scored.has_incumbent || !scored.incumbent_matched_tracks ||
            scored.incumbent_matched_tracks+scored.incumbent_unmatched_tracks!=
                snapshot->location_tracks.records.size())
            throw std::runtime_error("bounded native score failed");
        const auto search_resume_end=SteadyClock::now();
        std::cout<<"{\"schema\":\"leo-recorded-session-replay/v2\",\"source_rows\":"
            <<rows.size()<<",\"selected_rows\":"<<selected.size()
            <<",\"projected\":"<<stats.projected<<",\"nonpassing\":"<<stats.nonpassing
            <<",\"queue_high_water\":"<<stats.high_water<<",\"queue_dropped\":"
            <<stats.queue_dropped<<",\"tracks\":"<<snapshot->tracking_result.tracks.size()
            <<",\"location_tracks\":"<<snapshot->location_tracks.records.size()
            <<",\"reference_membership_exact\":true,\"orbit_records\":"<<orbit.records.size()
            <<",\"scored_points\":"<<scored.evaluated_points
            <<",\"native_weighted_mse_hz2\":"<<std::setprecision(17)
            <<scored.incumbent.weighted_mse_hz2
            <<",\"matched_tracks\":"<<scored.incumbent_matched_tracks
            <<",\"unmatched_tracks\":"<<scored.incumbent_unmatched_tracks
            <<",\"evaluated_satellite_tracks\":"
            <<scored.incumbent_evaluated_satellite_tracks
            <<",\"rejected_satellite_tracks\":"
            <<scored.incumbent_rejected_satellite_tracks
            <<",\"server_score_parity_claimed\":false"
            <<",\"historical_profile_crc_available\":false"
            <<",\"stage_timing_ms\":{\"load_validate\":"
            <<milliseconds(total_begin,load_validate_end)
            <<",\"all_row_prefix_projection\":"
            <<milliseconds(load_validate_end,prefix_projection_end)
            <<",\"selected_ingress_drain\":"
            <<milliseconds(prefix_projection_end,ingress_drain_end)
            <<",\"publish\":"<<milliseconds(ingress_drain_end,publish_end)
            <<",\"reference_diagnostic\":"
            <<milliseconds(publish_end,reference_diagnostic_end)
            <<",\"orbit_build\":"
            <<milliseconds(reference_diagnostic_end,orbit_build_end)
            <<",\"search_begin\":"<<milliseconds(orbit_build_end,search_begin_end)
            <<",\"search_resume\":"<<milliseconds(search_begin_end,search_resume_end)
            <<",\"total\":"<<milliseconds(total_begin,search_resume_end)<<"}}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr<<error.what()<<'\n'; return 1;
    }
}
