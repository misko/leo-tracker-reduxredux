#pragma once
#include "runtime.hpp"
#include "support_derivation.hpp"
#include <array>
#include <string>
namespace leo { namespace adaptive {
struct ProjectionSource {
    std::string input_digest,analysis_digest;
    uint64_t generation,anchor_counter,window_counter,visit;
    int64_t anchor_utc_ns;
    uint32_t rate,probe_index,receiver,channel;
    bool upper_edge;
    double actual_rf_hz,utc_bracket_width_ns;
    bool continuity_qualified;
    // This deployment profile supports 20-ms GLRT evidence only. Callers must
    // carry their actual probe geometry; other lengths are rejected explicitly.
    uint32_t probe_ms=20;
};
struct FractionalCandidate {
    uint32_t rank;
    int64_t integer_epoch;
    double fractional_offset,tracking_cfo_hz,exact_score,control_score,margin;
    bool complete;
};
struct Observation {
    std::string candidate_id,source_group_id;
    uint64_t generation,visit;
    uint32_t receiver,channel,probe_index;
    bool upper_edge;
    double actual_rf_hz,measured_cfo_hz,exact_score,control_score,margin;
    int64_t support_start_utc_ns,support_center_utc_ns,support_end_utc_ns;
    double standard_uncertainty_hz,moment2,moment3;
};
enum class ProjectionInputStatus { passing, nonpassing };
// Validate source, candidate, support-input, and margin fields without deriving
// support. Invalid values throw; incomplete or below-gate values are nonpassing.
ProjectionInputStatus classify_projection_input(
    const ProjectionSource&,const FractionalCandidate&,double margin_gate=0.025);
// Returns false for incomplete/nonpassing evidence; never synthesizes offsets.
bool project(const ProjectionSource&,const FractionalCandidate&,Observation&,
             double margin_gate=0.025);

// Caller-owned, synchronous batch. Only source-independent support geometry
// is memoized; every candidate still validates its source and scores. Separate
// workers own separate batches. No state or identity crosses a dwell boundary.
class ProjectionBatch {
    struct Entry {
        bool valid=false;
        uint32_t rate=0;
        int64_t epoch=0;
        double offset=0;
        Support support{};
    };
    std::array<Entry,16> entries_{};
    size_t next_=0,derivations_=0;
public:
    bool project(const ProjectionSource&,const FractionalCandidate&,Observation&,
                 double margin_gate=0.025);
    size_t support_derivations() const { return derivations_; }
};

enum class SupportProjectionStatus {
    emitted,
    nonpassing,
    invalid_derivation,
    derivation_unavailable,
};

// Explicit support-authority path. The callback is invoked only after source,
// candidate, and margin validation. Output values change only on emission.
SupportProjectionStatus project(
    const ProjectionSource&,
    const FractionalCandidate&,
    const SupportDerivationPort&,
    Observation&,
    SupportDerivation&,
    double margin_gate=0.025);
} }
