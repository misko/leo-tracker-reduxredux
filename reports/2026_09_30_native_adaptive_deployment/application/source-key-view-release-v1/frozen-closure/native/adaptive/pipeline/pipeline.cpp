#include "pipeline.hpp"

#include "sha256.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <limits>
#include <set>
#include <stdexcept>

namespace leo::adaptive::pipeline {
namespace {

constexpr const char* kTrajectoryAlgorithm =
    "persistent-hop-normalized-hough-episode-graph-v1";
constexpr const char* kPartitionPolicy = "deterministic-randomized-observation-v1";

std::string digest(const std::string& value) {
    return "sha256:" + leo::adaptive::sha256(value);
}

bool tagged_digest(const std::string& value) {
    return value.size() == 71 && value.compare(0, 7, "sha256:") == 0 &&
        value.find_first_not_of("0123456789abcdef", 7) == std::string::npos;
}

std::string observation_identity(
    const std::string& candidate_id,
    const std::string& tracklet_id,
    int alias) {
    return digest(
        "{\"algorithm_version\":\"" + std::string(kTrajectoryAlgorithm) +
        "\",\"candidate_id\":\"" + candidate_id +
        "\",\"canonical_rf_hz\":11200000000.0,\"relative_alias_index\":" +
        std::to_string(alias) + ",\"tracklet_id\":\"" + tracklet_id + "\"}");
}

std::string support_digest(
    const std::string& episode_id,
    const std::vector<std::string>& observation_ids,
    const std::vector<const SupportAuthority*>& support) {
    std::string material =
        "{\"algorithm_version\":\"catalogue-prediction-support-v1\",\"episode_ids\":[\"" +
        episode_id + "\"],\"observations\":[";
    for (std::size_t index = 0; index < observation_ids.size(); ++index) {
        if (index) material += ',';
        const auto& row = *support[index];
        material +=
            "{\"episode_id\":\"" + episode_id +
            "\",\"factorial_support_moments_s\":[" + row.moment0 + ',' + row.moment1 + ',' +
            row.moment2 + ',' + row.moment3 + "],\"observation_id\":\"" +
            observation_ids[index] + "\",\"schema_version\":1,\"support_center_utc_ns\":" +
            std::to_string(row.support_center_utc_ns) + ",\"support_end_utc_ns\":" +
            std::to_string(row.support_end_utc_ns) + ",\"support_start_utc_ns\":" +
            std::to_string(row.support_start_utc_ns) + '}';
    }
    material += "],\"response_fields_excluded\":true,\"schema_version\":1}";
    return digest(material);
}

std::string selection_protocol(const std::string& trajectory_digest) {
    return digest(
        "{\"algorithm\":\"scanner-shared-tracking-v12\","
        "\"catalogue\":\"exclude-labelled-debris-and-sgp4-failures-before-response-v1\","
        "\"group_limit\":4,\"observer\":{\"mode\":\"fixed\","
        "\"salt\":\"cf510316-fixed-partition-v1\"},"
        "\"selection\":\"eligible-first-longest-support-v1\",\"trajectory\":\"" +
        trajectory_digest + "\",\"utc_qualification_limit_ns\":2000000000}");
}

std::string partition_seed(const std::string& support, const std::string& protocol) {
    return digest(
        "{\"policy\":\"persistent-hop-fixed-orbit-randomized-residual-v1\","
        "\"response_free_support_digest\":\"" + support +
        "\",\"selection_protocol_digest\":\"" + protocol + "\"}");
}

std::vector<std::uint8_t> partition(
    const std::vector<std::string>& observation_ids,
    const std::string& seed) {
    if (observation_ids.size() < 3) throw std::invalid_argument("track needs three observations");
    std::vector<std::pair<std::string,std::size_t>> ranking;
    ranking.reserve(observation_ids.size());
    for (std::size_t index = 0; index < observation_ids.size(); ++index) {
        const std::string material =
            "{\"observation_id\":\"" + observation_ids[index] +
            "\",\"partition_policy\":\"" + kPartitionPolicy +
            "\",\"split_seed\":\"" + seed + "\"}";
        ranking.emplace_back(digest(material), index);
    }
    std::sort(ranking.begin(), ranking.end());
    const std::size_t training = std::min(
        std::max<std::size_t>(2, static_cast<std::size_t>(std::floor(observation_ids.size()*0.6))),
        observation_ids.size()-1);
    std::vector<std::uint8_t> mask(observation_ids.size());
    for (std::size_t index = 0; index < training; ++index) mask[ranking[index].second] = 1;
    return mask;
}

template <typename T>
T read_value(const std::vector<unsigned char>& input, std::size_t& offset) {
    if (offset > input.size() || input.size()-offset < sizeof(T))
        throw std::runtime_error("truncated LOC1 authority fixture");
    T value{};
    std::memcpy(&value,input.data()+offset,sizeof(T));
    offset+=sizeof(T);
    return value;
}

template <typename T>
void write_value(std::ofstream& output, const T& value) {
    output.write(reinterpret_cast<const char*>(&value),sizeof(T));
    if (!output) throw std::runtime_error("LOC1 output failed");
}

void write_bytes(std::ofstream& output,const void* data,std::size_t size) {
    output.write(reinterpret_cast<const char*>(data),static_cast<std::streamsize>(size));
    if (!output) throw std::runtime_error("LOC1 output failed");
}

}  // namespace

LocationTrackBatch make_location_tracks(
    const tracking::Result& result,
    const GraphAuthority& authority) {
    if (!tagged_digest(result.config_digest) || !tagged_digest(authority.input_manifest_digest) ||
        authority.session_id.empty() || authority.session_start_utc_ns<=0 ||
        authority.candidates.empty() || authority.candidates.size()>40'000)
        throw std::invalid_argument("graph authority is incomplete");
    const std::string dwell = digest(
        "{\"algorithm_version\":\"" + std::string(kTrajectoryAlgorithm) +
        "\",\"input_manifest_digest\":\"" + authority.input_manifest_digest +
        "\",\"session_id\":\"" + authority.session_id + "\"}");
    const std::string protocol = selection_protocol(result.config_digest);
    LocationTrackBatch output;
    output.owned.reserve(result.tracks.size());
    for (const auto& track:result.tracks) {
        if (!tagged_digest(track.tracklet_id))
            throw std::invalid_argument("track lacks deployment-profile identity");
        OwnedLocationTrack owned;
        owned.tracklet_id=track.tracklet_id;
        const std::string episode=digest(
            "{\"dwell_id\":\""+dwell+"\",\"tracklet_id\":\""+track.tracklet_id+"\"}");
        std::vector<const SupportAuthority*> support;
        support.reserve(track.points.size());
        for (const auto& point:track.points) {
            const auto found=authority.candidates.find(point.candidate_id);
            if (found==authority.candidates.end())
                throw std::invalid_argument("track candidate lacks graph support authority");
            if (found->second.support_start_utc_ns<=0 ||
                found->second.support_start_utc_ns>found->second.support_center_utc_ns ||
                found->second.support_center_utc_ns>=found->second.support_end_utc_ns ||
                found->second.support_center_utc_ns<authority.session_start_utc_ns)
                throw std::invalid_argument("candidate graph support geometry is invalid");
            support.push_back(&found->second);
            owned.observation_ids.push_back(
                observation_identity(point.candidate_id,track.tracklet_id,point.relative_alias_index));
            owned.times_s.push_back(
                (found->second.support_center_utc_ns-authority.session_start_utc_ns)/1e9);
            owned.measured_hz.push_back(point.normalized_dealiased_cfo_hz);
        }
        owned.support_digest=support_digest(episode,owned.observation_ids,support);
        owned.partition_seed=partition_seed(owned.support_digest,protocol);
        owned.training_mask=partition(owned.observation_ids,owned.partition_seed);
        output.owned.push_back(std::move(owned));
    }
    output.records.reserve(output.owned.size());
    for (auto& owned:output.owned) {
        std::set<std::int64_t> bins;
        for (double time:owned.times_s) bins.insert(static_cast<std::int64_t>(std::floor(time)));
        const std::string hex=owned.tracklet_id.substr(7,16);
        const std::uint64_t key=std::stoull(hex,nullptr,16);
        output.records.push_back(leo_location_track{
            key,static_cast<std::uint32_t>(owned.times_s.size()),static_cast<std::uint32_t>(bins.size()),
            owned.times_s.data(),owned.measured_hz.data(),owned.training_mask.data()});
    }
    return output;
}

void write_loc1(const std::string& authority_fixture,const std::string& output_path,
                const LocationTrackBatch& tracks) {
    std::ifstream input(authority_fixture,std::ios::binary);
    if (!input) throw std::runtime_error("cannot open LOC1 authority fixture");
    const std::vector<unsigned char> bytes(
        (std::istreambuf_iterator<char>(input)),std::istreambuf_iterator<char>());
    std::size_t offset=0;
    const auto magic=read_value<std::uint32_t>(bytes,offset);
    const auto satellites=read_value<std::uint32_t>(bytes,offset);
    const auto knots=read_value<std::uint32_t>(bytes,offset);
    const auto old_tracks=read_value<std::uint32_t>(bytes,offset);
    const auto sites=read_value<std::uint32_t>(bytes,offset);
    const auto knot_start=read_value<double>(bytes,offset);
    const auto knot_step=read_value<double>(bytes,offset);
    if (magic!=0x31434f4cU || !satellites || satellites>20'000 || knots<2 || knots>2'000 ||
        !sites || sites>128 || old_tracks>128 || tracks.records.empty() || tracks.records.size()>128)
        throw std::runtime_error("invalid LOC1 authority header");
    const std::size_t site_start=offset;
    const std::size_t site_bytes=static_cast<std::size_t>(sites)*6*sizeof(double);
    if (site_bytes>bytes.size()-offset) throw std::runtime_error("truncated LOC1 sites");
    offset+=site_bytes;
    for (std::uint32_t index=0;index<old_tracks;++index) {
        const auto observations=read_value<std::uint32_t>(bytes,offset);
        (void)read_value<std::uint32_t>(bytes,offset);
        const std::size_t payload=static_cast<std::size_t>(observations)*(2*sizeof(double)+1);
        if (payload>bytes.size()-offset) throw std::runtime_error("truncated LOC1 old tracks");
        offset+=payload;
    }
    const std::size_t expected_tail=static_cast<std::size_t>(satellites)*sizeof(std::int32_t)+
        static_cast<std::size_t>(satellites)*knots*6*sizeof(double);
    if (bytes.size()-offset!=expected_tail) throw std::runtime_error("invalid LOC1 authority tail");
    std::ofstream output(output_path,std::ios::binary|std::ios::trunc);
    if (!output) throw std::runtime_error("cannot open LOC1 output");
    write_value(output,magic);write_value(output,satellites);write_value(output,knots);
    const auto track_count=static_cast<std::uint32_t>(tracks.records.size());
    write_value(output,track_count);write_value(output,sites);write_value(output,knot_start);
    write_value(output,knot_step);write_bytes(output,bytes.data()+site_start,site_bytes);
    for (const auto& track:tracks.records) {
        write_value(output,track.observation_count);write_value(output,track.weight_s);
        write_bytes(output,track.times_s,track.observation_count*sizeof(double));
        write_bytes(output,track.measured_hz,track.observation_count*sizeof(double));
        write_bytes(output,track.training_mask,track.observation_count);
    }
    write_bytes(output,bytes.data()+offset,expected_tail);
}

}  // namespace leo::adaptive::pipeline
