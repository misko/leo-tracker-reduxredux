#pragma once
#include "location.h"
#include <cstring>
#include <vector>
#ifdef LEO_RESEARCH_VECTOR_PAIR_BOUND
#include "doppler_interval4.hpp"
#endif

namespace leo::location::research {
// Dense pair index, lazily populated endpoint blocks. Only interpolated states
// are reused: site-dependent Doppler, bounds and final scores are recomputed.
class EndpointStateBank {
public:
    // The qualified default grid has eleven offsets. Wider grids retain the
    // original uncached scorer instead of reserving unused slots in every block.
    static constexpr unsigned maximum_taus=11;
    struct Block {
        uint32_t valid=0;leo_orbit_state states[2*maximum_taus]{};
#ifdef LEO_RESEARCH_VECTOR_PAIR_BOUND
        PackedOrbit4 packed[2][3]{};
#endif
    };
private:
    size_t capacity_;
    std::vector<Block> blocks_;
    std::vector<uint32_t> index_;
    std::vector<leo_orbit_state> authority_;
    std::vector<double> endpoints_;
    unsigned begin_=0,end_=0,knots_=0,tracks_=0;
    uint64_t generation_=0;
    double start_=0,step_=0;
    int32_t first_=0,last_=0,tau_step_=0;
    const leo_orbit_state* snapshot_states_=nullptr;
    bool immutable_=false;
public:
    explicit EndpointStateBank(size_t bytes=
#ifdef LEO_RESEARCH_ENDPOINT_BANK_BYTES
        LEO_RESEARCH_ENDPOINT_BANK_BYTES
#elif defined(LEO_RESEARCH_VECTOR_PAIR_BOUND)
        64u*1024*1024
#else
        32u*1024*1024
#endif
        ):capacity_(bytes/sizeof(Block)) {}
    void invalidate() {
        tracks_=0;blocks_.clear();index_.clear();authority_.clear();endpoints_.clear();
        snapshot_states_=nullptr;immutable_=false;
    }
    bool prepare(const leo_orbit_snapshot& s,const leo_location_track* tracks,
                 unsigned count,const leo_score_config& c,unsigned begin,unsigned end,
                 bool immutable=false) {
        const int64_t span=static_cast<int64_t>(c.tau_last_s)-c.tau_first_s;
        if(!capacity_ || !tracks || !s.states || begin>=end || end>s.satellite_count ||
           !count || count>256 || end-begin>20000 || s.knot_count<2 ||
           static_cast<size_t>(end-begin)*s.knot_count>600000 ||
           c.tau_step_s<=0 || span<0 || span%c.tau_step_s ||
           span/c.tau_step_s>=maximum_taus) return false;
        try {
            std::vector<double> endpoints;
            endpoints.reserve(2*count);
            for(unsigned t=0;t<count;++t) {
                const auto& track=tracks[t];
                unsigned first=0,last=track.observation_count;
                if(!track.times_s || !track.training_mask) return false;
                while(first<last && track.training_mask[first])++first;
                while(last>first && track.training_mask[last-1])--last;
                if(last-first<2)return false;
                endpoints.push_back(track.times_s[first]);endpoints.push_back(track.times_s[last-1]);
            }
            const size_t n=static_cast<size_t>(end-begin)*s.knot_count;
            const auto* states=s.states+static_cast<size_t>(begin)*s.knot_count;
            const bool changed=begin!=begin_ || end!=end_ || count!=tracks_ ||
                immutable!=immutable_ || (immutable && s.states!=snapshot_states_) ||
                s.generation!=generation_ || s.knot_count!=knots_ ||
                s.knot_start_s!=start_ || s.knot_step_s!=step_ ||
                c.tau_first_s!=first_ || c.tau_last_s!=last_ || c.tau_step_s!=tau_step_ ||
                endpoints.size()!=endpoints_.size() ||
                std::memcmp(endpoints.data(),endpoints_.data(),endpoints.size()*sizeof(double)) ||
                (!immutable && (authority_.size()!=n || std::memcmp(states,authority_.data(),n*sizeof(*states))));
            if(changed) {
                // Mark unusable before allocations: a failed preparation must
                // never expose old entries under new authority.
                tracks_=0;blocks_.clear();index_.clear();
                if(immutable)authority_.clear();else authority_.assign(states,states+n);
                endpoints_=std::move(endpoints);
                index_.assign(static_cast<size_t>(count)*(end-begin),UINT32_MAX);
                blocks_.reserve(capacity_);
                begin_=begin;end_=end;knots_=s.knot_count;generation_=s.generation;
                start_=s.knot_start_s;step_=s.knot_step_s;
                first_=c.tau_first_s;last_=c.tau_last_s;tau_step_=c.tau_step_s;tracks_=count;
                snapshot_states_=s.states;immutable_=immutable;
            }
            return true;
        } catch(...) {tracks_=0;return false;}
    }
    Block* block(unsigned track,unsigned satellite) {
        if(track>=tracks_ || satellite<begin_ || satellite>=end_)return nullptr;
        auto& index=index_[static_cast<size_t>(track)*(end_-begin_)+satellite-begin_];
        if(index==UINT32_MAX) {
            if(blocks_.size()>=capacity_)return nullptr;
            index=static_cast<uint32_t>(blocks_.size());blocks_.emplace_back();
        }
        return &blocks_[index];
    }
};
}
