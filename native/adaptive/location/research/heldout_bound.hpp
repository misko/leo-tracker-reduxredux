#pragma once
#include "location.h"
#include <cmath>
#include <cstddef>
#include "score_stencil_internal.hpp"
#include "bound_state_cache.hpp"
#include "endpoint_state_bank.hpp"
#ifdef LEO_RESEARCH_FLOAT_PAIR_BOUND
#include "float_pair_bound.hpp"
#endif

namespace leo::location::research {
// The minimum SSE of a subset about its own mean cannot exceed the full
// held-out SSE about the training-fitted offset. Normalize by FULL count.
inline bool subset_cannot_win(const double* residual,unsigned size,unsigned count,double incumbent) {
    if(size<2 || size>count || !std::isfinite(incumbent) || incumbent<0) return false;
    double mean=0,sum=0,scale=0;
    for(unsigned i=0;i<size;++i) {
        if(!std::isfinite(residual[i])) return false;
        mean+=(residual[i]-residual[0])/size;
        scale+=std::abs(residual[i]);
    }
    for(unsigned i=0;i<size;++i) {
        double error=(residual[i]-residual[0])-mean;sum+=error*error;
    }
    double bound=std::sqrt(sum/count);
    return std::isfinite(bound) && bound>incumbent+1e-6*(1+scale+incumbent);
}
// For any fitted constant c, (a-c)^2+(b-c)^2 >= (a-b)^2/2.
// Dividing by the FULL held-out count gives a lower bound for its RMS.
inline bool pair_cannot_win(double a,double b,unsigned count,double incumbent,
                           double denominator=0,double conservative_inverse=0) {
    if(count<2 || !std::isfinite(a) || !std::isfinite(b) ||
       !std::isfinite(incumbent) || incumbent<0) return false;
    const double bound=conservative_inverse>0?std::abs(a-b)*conservative_inverse:
        std::abs(a-b)/(denominator>0?denominator:std::sqrt(2.0*count));
    // Research guard against cancellation and rounding near a winning tie.
    const double guard=1e-6*(1.0+std::abs(a)+std::abs(b)+incumbent);
    return std::isfinite(bound) && bound>incumbent+guard;
}

inline bool bounded_site(const leo_location_site& site,const leo_score_config& config) {
    if(config.carrier_hz>1e12 || config.speed_of_light_km_s<1) return false;
    for(unsigned c=0;c<3;++c)
        if(!std::isfinite(site.ecef_km[c]) || std::abs(site.ecef_km[c])>1e6) return false;
    return true;
}
inline bool bounded_orbit_partition(const leo_orbit_snapshot& snapshot,
                                   unsigned begin=0,unsigned end=UINT32_MAX) {
    if(end==UINT32_MAX) end=snapshot.satellite_count;
    if(begin>end || end>snapshot.satellite_count) return false;
    for(size_t i=static_cast<size_t>(begin)*snapshot.knot_count;
        i<static_cast<size_t>(end)*snapshot.knot_count;++i)
        for(unsigned c=0;c<3;++c)
            if(!std::isfinite(snapshot.states[i].position_km[c]) ||
               !std::isfinite(snapshot.states[i].velocity_km_s[c]) ||
               std::abs(snapshot.states[i].position_km[c])>1e9 ||
               std::abs(snapshot.states[i].velocity_km_s[c])>1e6) return false;
    return true;
}
inline bool bounded_snapshot(const leo_orbit_snapshot& snapshot,
                             const leo_location_site& site,const leo_score_config& config,
                             unsigned begin=0,unsigned end=UINT32_MAX) {
    return bounded_site(site,config) && bounded_orbit_partition(snapshot,begin,end);
}

struct BoundSubset {
    unsigned indexes[8]{}; unsigned size{};
    double pair_denominator=0, pair_inverse=0;
};
inline BoundSubset select_subset(const leo_location_track& track,unsigned heldout_count) {
    BoundSubset result;
    if(heldout_count<2) return result;
    result.pair_denominator=std::sqrt(2.0*heldout_count);
    result.pair_inverse=(1.0/result.pair_denominator)*(1.0-0x1p-48);
    unsigned first=0,last=track.observation_count-1;
    while(track.training_mask[first]) ++first;
    while(track.training_mask[last]) --last;
    result.indexes[0]=first;result.indexes[1]=last;result.size=2;
#ifdef LEO_RESEARCH_SUBSET_BOUND
    const unsigned desired=heldout_count<8?heldout_count:8;
    for(unsigned k=1;k+1<desired;++k) {
        unsigned rank=k*(heldout_count-1)/(desired-1),seen=0;
        for(unsigned i=first;i<=last;++i) if(!track.training_mask[i]) {
            if(seen++==rank) {result.indexes[result.size++]=i;break;}
        }
    }
#endif
    return result;
}
inline bool cannot_win(const leo_orbit_snapshot& snapshot,unsigned satellite,
                       const leo_location_track& track,const leo_location_site& site,
                       const leo_score_config& config,unsigned heldout_count,
                       const leo_track_score& incumbent,const BoundSubset* prepared=nullptr,
                       const internal::InterpolationStencil* stencils=nullptr,
                       BoundStateCache* cache=nullptr,
                       EndpointStateBank::Block* endpoints=nullptr,
                       bool prevalidated_stencils=false
#ifdef LEO_RESEARCH_VECTOR_PAIR_BOUND
                       ,const PackedSite* packed_site=nullptr,
                       const PackedPairThreshold* prepared_threshold=nullptr
#endif
                       ) {
    if(!incumbent.matched || heldout_count<2 || !std::isfinite(incumbent.heldout_rms_hz)) return false;
    const BoundSubset subset=prepared?*prepared:select_subset(track,heldout_count);
    const unsigned size=subset.size;
    if(size<2) return false;
    // Interpolation calls can prevent compiler hoisting through pointer aliases.
    // These values depend only on this invocation, never on satellite time.
    const double doppler_scale=-config.carrier_hz/config.speed_of_light_km_s;
    const double pair_denominator=subset.pair_denominator;
    // Lower the reciprocal by more than division/multiplication roundoff.
    // Only the rejection lower bound uses it; final scores remain unchanged.
    const double pair_inverse=subset.pair_inverse;
    uint32_t vector_rejections=0;
#ifdef LEO_RESEARCH_VECTOR_PAIR_BOUND
    const auto taus=static_cast<unsigned>((static_cast<int64_t>(config.tau_last_s)-config.tau_first_s)/config.tau_step_s+1);
    if(endpoints && packed_site && taus<=EndpointStateBank::maximum_taus &&
       (endpoints->valid&((1u<<(2*taus))-1))==((1u<<(2*taus))-1)) {
        const auto threshold=prepared_threshold?*prepared_threshold:pack_pair_threshold(track.measured_hz[subset.indexes[0]],
            track.measured_hz[subset.indexes[1]],incumbent.heldout_rms_hz,pair_denominator);
        for(unsigned group=0;group<(taus+3)/4;++group)
            vector_rejections|=pair_rejections4(endpoints->packed[0][group],endpoints->packed[1][group],
                *packed_site,threshold)<<(4*group);
    }
#endif
    size_t tau_index=0;
    for(int64_t tau=config.tau_first_s;tau<=config.tau_last_s;tau+=config.tau_step_s,++tau_index) {
        if(tau_index<32 && (vector_rejections&(1u<<tau_index)))continue;
        double residual[8];bool rejected=false;
#ifdef LEO_RESEARCH_FLOAT_PAIR_BOUND
        leo_orbit_state endpoint_states[2];double endpoint_errors[2]{};
#endif
        for(unsigned j=0;j<size;++j) {
            auto index=subset.indexes[j]; leo_orbit_state state{};
            // Each visited tau lies between two int32 endpoints. Keep the
            // loop increment wide to avoid overflow, but avoid ARM software
            // int64-to-double conversion and division for every observation.
            const double time=track.times_s[index]+static_cast<int32_t>(tau);
            const unsigned endpoint_slot=static_cast<unsigned>(tau_index)*2+j;
            const bool bank_slot=endpoints && j<2 && tau_index<EndpointStateBank::maximum_taus;
            const bool bank_hit=bank_slot && (endpoints->valid&(1u<<endpoint_slot));
            if(bank_hit) {
                state=endpoints->states[endpoint_slot];
            } else if(!cache || !cache->lookup(satellite,time,state)) {
            auto status=stencils?(prevalidated_stencils
                ?internal::interpolate_with_prevalidated_stencil:internal::interpolate_with_stencil)(&snapshot,satellite,
                &stencils[tau_index*track.observation_count+index],&state)
                :leo_orbit_interpolate(&snapshot,satellite,time,&state);
            if(status!=LEO_LOCATION_OK) return false;
            if(cache)cache->store(satellite,time,state);
            }
            if(bank_slot && !bank_hit) {
                endpoints->states[endpoint_slot]=state;
                endpoints->valid|=1u<<endpoint_slot;
#ifdef LEO_RESEARCH_VECTOR_PAIR_BOUND
                pack_orbit_lane(endpoints->packed[j][tau_index/4],static_cast<unsigned>(tau_index%4),state);
#endif
            }
#ifdef LEO_RESEARCH_FLOAT_PAIR_BOUND
            if(j<2) {
                endpoint_states[j]=state;
                const auto prediction=float_doppler(state,site,doppler_scale);
                if(prediction.valid) {
                    residual[j]=track.measured_hz[index]-prediction.value;
                    endpoint_errors[j]=prediction.error;
                    if(j==0)continue;
                } else {
                    double d[3];for(unsigned c=0;c<3;++c)d[c]=state.position_km[c]-site.ecef_km[c];
                    const double r2=d[0]*d[0]+d[1]*d[1]+d[2]*d[2];
                    if(!(r2>0) || !std::isfinite(r2))return false;
                    residual[j]=track.measured_hz[index]-doppler_scale*
                        (d[0]*state.velocity_km_s[0]+d[1]*state.velocity_km_s[1]+d[2]*state.velocity_km_s[2])/std::sqrt(r2);
                    if(j==0)continue;
                }
                if(interval_pair_cannot_win(residual[0],endpoint_errors[0],residual[1],endpoint_errors[1],
                                            pair_denominator,incumbent.heldout_rms_hz)) {rejected=true;break;}
                // An uncertain interval cannot alter the existing subset bound:
                // restore both endpoint residuals with the original arithmetic.
                for(unsigned endpoint=0;endpoint<2;++endpoint) {
                    const auto& exact=endpoint_states[endpoint];double d[3];
                    for(unsigned c=0;c<3;++c)d[c]=exact.position_km[c]-site.ecef_km[c];
                    const double r2=d[0]*d[0]+d[1]*d[1]+d[2]*d[2];
                    if(!(r2>0) || !std::isfinite(r2))return false;
                    residual[endpoint]=track.measured_hz[subset.indexes[endpoint]]-doppler_scale*
                        (d[0]*exact.velocity_km_s[0]+d[1]*exact.velocity_km_s[1]+d[2]*exact.velocity_km_s[2])/std::sqrt(r2);
                }
                if(pair_cannot_win(residual[0],residual[1],heldout_count,incumbent.heldout_rms_hz,pair_denominator,pair_inverse)) {
                    rejected=true;break;
                }
                continue;
            }
#endif
            double delta[3];
            for(unsigned c=0;c<3;++c) delta[c]=state.position_km[c]-site.ecef_km[c];
            const double range2=delta[0]*delta[0]+delta[1]*delta[1]+delta[2]*delta[2];
            if(!(range2>0) || !std::isfinite(range2)) return false;
            const double radial=delta[0]*state.velocity_km_s[0]+delta[1]*state.velocity_km_s[1]+delta[2]*state.velocity_km_s[2];
            const double predicted=doppler_scale*radial/std::sqrt(range2);
            residual[j]=track.measured_hz[index]-predicted;
            if(j==1 && pair_cannot_win(residual[0],residual[1],heldout_count,incumbent.heldout_rms_hz,pair_denominator,pair_inverse)) {
                rejected=true;break;
            }
        }
        // Any tau that might win requires the unchanged full scorer.
#ifdef LEO_RESEARCH_SUBSET_BOUND
        if(!rejected && !subset_cannot_win(residual,size,heldout_count,incumbent.heldout_rms_hz)) return false;
#else
        if(!rejected) return false;
#endif
    }
    return true;
}
} // namespace leo::location::research
