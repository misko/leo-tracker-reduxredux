#pragma once

#include "location.h"
#include <cstddef>
#include <vector>

namespace leo::adaptive::location::doppler_match {

// Circular receiver prior: geodetic degrees, radius in km, altitude fixed at 0.
struct Region { double latitude=0, longitude=0, radius=250; };

// Seconds relative to Options::epoch_utc_ns; frequencies in Hz. The caller
// supplies samples of a spline fitted using ONLY the training observations.
// Each training mask byte is 0 (held out) or 1 (training).
struct Track {
    std::vector<double> times, measured, nodes, values;
    std::vector<unsigned char> training;
};

struct Options {
    int64_t epoch_utc_ns=0;
    double carrier_hz=0;
    Region region;
    double time_bound_s=60, fine_step_s=5, coarse_step_s=30, time_step_s=20;
    size_t keep_per_track=8;
    bool audit_gate=false, disable_gate=false;
    // Research comparison only; full spline proposals are the default.
    bool endpoint_proposals=false;
};

// Each successful call copies the next TLE into record. Records must have
// distinct satellite IDs. Called exactly count times, synchronously, on the
// calling thread. False before count records is a source error; exceptions
// propagate. The caller owns storage, eligibility filtering and I/O.
struct Catalogue {
    size_t count=0;
    bool (*read_next)(void* user, leo_tle_record& record)=nullptr;
    void* user=nullptr;
};

struct Candidate {
    int32_t satellite_id=0;
    double east_km=0, north_km=0, latitude_deg=0, longitude_deg=0;
    // UTC of an observation = epoch_utc_ns + (observation_s + offset_s)*1e9.
    double time_offset_s=0, frequency_offset_hz=0;
    double training_rms_hz=0, validation_rms_hz=0;
};

struct Statistics {
    size_t catalogue_records=0, observation_count=0, retained_catalogue_count=0;
    size_t gate_fine_envelope_misses=0, refined_hypotheses=0;
    size_t orbit_state_capacity_bytes=0, hypothesis_capacity_bytes=0;
    uint64_t propagated_states=0, seed_evaluations=0;
    double cache_begin_s=0, cache_end_s=0;
    // Propagation includes refinement propagation, so stage times overlap.
    double propagation_s=0, proposal_s=0, refinement_s=0, total_s=0;
    std::vector<int32_t> invalid_catalogue_ids, retained_catalogue_ids;
};

struct Result {
    // Input track order; ascending training RMS, then satellite ID. An empty
    // list means no fitted candidate. Held-out data never select a candidate.
    std::vector<std::vector<Candidate>> tracks;
    Statistics statistics;
};

// Experimental candidate retrieval, not a shared position/clock fix and not
// an exhaustive search. Borrows immutable tracks until return; returns owned
// results. No files, threads, globals, storage adapters or persistent cache.
// Streams through two single-satellite orbit contexts and bounded shortlists.
// Throws invalid_argument for invalid inputs, runtime_error for source/orbit
// failure, and bad_alloc on allocation failure. No partial result is returned.
Result match(const std::vector<Track>& tracks, const Options& options, Catalogue catalogue);

} // namespace leo::adaptive::location::doppler_match
