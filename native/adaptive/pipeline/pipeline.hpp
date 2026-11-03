#pragma once

#include "location.h"
#include "tracking.hpp"

#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

namespace leo::adaptive::pipeline {

struct SupportAuthority {
    std::int64_t support_start_utc_ns{};
    std::int64_t support_center_utc_ns{};
    std::int64_t support_end_utc_ns{};
    std::string moment0;
    std::string moment1;
    std::string moment2;
    std::string moment3;
};

struct GraphAuthority {
    std::string session_id;
    std::string input_manifest_digest;
    std::int64_t session_start_utc_ns{};
    std::unordered_map<std::string, SupportAuthority> candidates;
};

struct OwnedLocationTrack {
    std::string tracklet_id;
    std::string support_digest;
    std::string partition_seed;
    std::vector<std::string> observation_ids;
    std::vector<double> times_s;
    std::vector<double> measured_hz;
    std::vector<std::uint8_t> training_mask;
};

struct LocationTrackBatch {
    std::vector<OwnedLocationTrack> owned;
    std::vector<leo_location_track> records;
    LocationTrackBatch() = default;
    LocationTrackBatch(const LocationTrackBatch&) = delete;
    LocationTrackBatch& operator=(const LocationTrackBatch&) = delete;
    LocationTrackBatch(LocationTrackBatch&&) = default;
    LocationTrackBatch& operator=(LocationTrackBatch&&) = default;
};

LocationTrackBatch make_location_tracks(
    const tracking::Result& result,
    const GraphAuthority& authority);

void write_loc1(
    const std::string& authority_fixture,
    const std::string& output_path,
    const LocationTrackBatch& tracks);

}  // namespace leo::adaptive::pipeline
