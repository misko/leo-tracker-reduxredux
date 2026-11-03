#include "server_compat.hpp"
#include "session.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using namespace leo::adaptive;

struct Row {
    ProjectionSource source;
    FractionalCandidate candidate;
};

std::vector<Row> rows(const std::string& path) {
    std::ifstream input(path);
    if(!input) throw std::runtime_error("cannot open projection input");
    std::vector<Row> result;
    result.reserve(24'681);
    std::string line;
    while(std::getline(input,line)) {
        if(line.size()>4096 || result.size()>=25'000)
            throw std::runtime_error("oversized projection input");
        Row row;
        unsigned upper=0,qualified=0,complete=0;
        std::string extra;
        std::istringstream fields(line);
        if(!(fields>>row.source.rate>>row.source.anchor_counter>>row.source.anchor_utc_ns
             >>row.source.generation>>row.source.visit>>row.source.window_counter
             >>row.source.probe_index>>row.source.receiver>>row.source.channel>>upper
             >>row.source.actual_rf_hz>>row.source.utc_bracket_width_ns
             >>row.source.input_digest>>row.source.analysis_digest>>qualified
             >>row.candidate.rank>>row.candidate.integer_epoch
             >>row.candidate.fractional_offset>>row.candidate.tracking_cfo_hz
             >>row.candidate.exact_score>>row.candidate.control_score
             >>row.candidate.margin>>complete) || (fields>>extra) || upper>1 ||
             qualified!=1 || complete>1)
            throw std::runtime_error("invalid projection input row");
        row.source.upper_edge=upper!=0;
        row.source.continuity_qualified=true;
        row.candidate.complete=complete!=0;
        result.push_back(std::move(row));
    }
    if(!input.eof() || result.size()!=24'681)
        throw std::runtime_error("unexpected projection input cardinality");
    return result;
}

void require_consistent(const Row& first,const Row& row) {
    if(row.source.rate!=first.source.rate ||
       row.source.anchor_counter!=first.source.anchor_counter ||
       row.source.anchor_utc_ns!=first.source.anchor_utc_ns ||
       row.source.generation!=first.source.generation ||
       row.source.utc_bracket_width_ns!=first.source.utc_bracket_width_ns ||
       row.source.input_digest!=first.source.input_digest ||
       row.source.analysis_digest!=first.source.analysis_digest ||
       row.source.probe_index!=0 || row.source.upper_edge ||
       row.source.receiver>1 || row.source.channel<1 || row.source.channel>4)
        throw std::runtime_error("inconsistent DS9 source authority");
}

leo_scanner_event event(const Row& row) {
    leo_scanner_event value{};
    value.kind=LEO_SCANNER_CANDIDATE;
    value.visit=row.source.visit;
    value.valid_start=row.source.window_counter;
    const auto dwell=static_cast<std::uint64_t>(row.source.rate)*120/1000;
    if(value.valid_start>UINT64_MAX-dwell)
        throw std::runtime_error("event counter overflow");
    value.valid_end=value.valid_start+dwell;
    value.target=row.source.channel-1;
    value.profile=row.source.channel;
    value.frequency_hz=1'500'000'000ULL+row.source.channel;
    value.receiver_id=static_cast<std::int32_t>(row.source.receiver);
    value.probe_index=static_cast<std::int32_t>(row.source.probe_index);
    value.candidate_index=row.candidate.rank;
    value.candidate.epoch=row.candidate.integer_epoch;
    value.candidate.fractional_epoch_status=row.candidate.complete?1:2;
    value.candidate.fractional_epoch_offset_samples=row.candidate.fractional_offset;
    value.candidate.fractional_tracking_cfo_hz=row.candidate.tracking_cfo_hz;
    value.candidate.fractional_exact_score=row.candidate.exact_score;
    value.candidate.fractional_control_score=row.candidate.control_score;
    value.candidate.fractional_margin=row.candidate.margin;
    return value;
}

online::Config online_config() {
    online::Config config;
    config.maximum_history_observations=40'000;
    config.maximum_tracks=128;
    config.maximum_satellites=1;
    config.maximum_knots=2;
    config.maximum_search_points=1;
    config.maximum_observations_per_track=100'000;
    return config;
}

void write_tracks(const online::Snapshot& snapshot,const std::string& path) {
    std::ofstream output(path);
    if(!output) throw std::runtime_error("cannot open track output");
    std::size_t points=0;
    for(std::size_t track=0;track<snapshot.location_tracks.owned.size();++track) {
        const auto& value=snapshot.location_tracks.owned[track];
        output<<"TRACK\t"<<track<<'\t'<<value.tracklet_id<<'\t'<<value.support_digest
              <<'\t'<<value.partition_seed<<'\t'<<value.observation_ids.size()<<'\n';
        if(value.observation_ids.size()!=value.training_mask.size())
            throw std::runtime_error("location track vector mismatch");
        for(std::size_t point=0;point<value.observation_ids.size();++point) {
            output<<"POINT\t"<<point<<'\t'<<value.observation_ids[point]
                  <<"\t0\t0\t"<<static_cast<unsigned>(value.training_mask[point])<<'\n';
            ++points;
        }
    }
    if(!output) throw std::runtime_error("cannot write track output");
    if(snapshot.location_tracks.owned.size()!=64 || points!=3372)
        throw std::runtime_error("unexpected DS9 track cardinality");
}
}

int main(int argc,char** argv) {
    try {
        if(argc!=3) throw std::runtime_error("usage: test-ds9-session-compat INPUT.tsv OUTPUT.tsv");
        const auto input=rows(argv[1]);
        const auto& first=input.front();
        ingest::Authority authority{first.source.generation,first.source.rate,
            first.source.input_digest,first.source.analysis_digest,{}};
        authority.profile_authority=ingest::ProfileAuthority::historical_metadata;
        for(std::uint32_t channel=1;channel<=4;++channel) {
            const auto found=std::find_if(input.begin(),input.end(),[&](const auto& row) {
                return row.source.channel==channel;
            });
            if(found==input.end()) throw std::runtime_error("missing DS9 channel");
            authority.targets.push_back({channel,0,channel,1'500'000'000ULL+channel,
                found->source.actual_rf_hz,false});
        }
        server_compat::SupportDeriver deriver(server_compat::authority_binding());
        application::Session session(authority,
            {first.source.rate,1'000'000'000,3'600'000'000'000ULL,0,0,1},
            online_config(),{"scan-fw-3cfdaa6d75762cad",first.source.input_digest,
                first.source.anchor_utc_ns},40'000,server_compat::derivation_port(deriver));
        const auto width=static_cast<std::uint64_t>(first.source.utc_bracket_width_ns);
        if(static_cast<double>(width)!=first.source.utc_bracket_width_ns || width>1'000'000'000)
            throw std::runtime_error("invalid DS9 bracket width");
        const auto before=first.source.anchor_utc_ns-static_cast<std::int64_t>(width/2);
        if(session.observe({1'000'000'000,1'000'000'000+width,
                first.source.anchor_counter,before,before+static_cast<std::int64_t>(width),true})
                !=timing::Status::ok)
            throw std::runtime_error("DS9 bracket rejected");
        for(const auto& row:input) {
            require_consistent(first,row);
            const auto receipt=session.accept(event(row));
            if(receipt.projection!=ingest::Status::emitted &&
               receipt.projection!=ingest::Status::nonpassing)
                throw std::runtime_error("DS9 profile projection rejected");
            if(receipt.projection==ingest::Status::emitted && !receipt.queued)
                throw std::runtime_error("DS9 session queue overflow");
            if(receipt.queued && session.consume(1)!=1)
                throw std::runtime_error("DS9 session consume failed");
        }
        const auto stats=session.stats();
        if(stats.projected!=11'747 || stats.nonpassing!=12'934 || stats.consumed!=11'747 ||
           stats.rejected || stats.queue_dropped || stats.queued ||
           stats.history_capacity_evictions)
            throw std::runtime_error("DS9 session accounting differs");
        std::shared_ptr<const online::Snapshot> snapshot;
        if(session.publish(&snapshot)!=online::Status::ok || !snapshot)
            throw std::runtime_error("DS9 session publish failed");
        write_tracks(*snapshot,argv[2]);
        const auto cache=deriver.cache_stats();
        if(cache.hits!=2'237 || cache.misses!=9'510 || !cache.populated)
            throw std::runtime_error("DS9 support cache accounting differs");
        std::cout<<"{\"rows\":24681,\"projected\":11747,\"tracks\":64,"
                    "\"track_observations\":3372,\"cache_hits\":2237,"
                    "\"cache_misses\":9510}\n";
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<error.what()<<'\n';
        return 1;
    }
}
