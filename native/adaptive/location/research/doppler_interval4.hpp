#pragma once
#include "location.h"
#include <cmath>
#include <cstdint>
#include <limits>
#if defined(__ARM_NEON)
#include <arm_neon.h>
#endif

namespace leo::location::research {
// Private research prefilter. Packed orbit data may be reused across sites;
// these intervals never replace a final double-precision scientific score.
struct PackedOrbit4 {
    float position[3][4]{}, velocity[3][4]{};
    float position_error[4]{}, speed_l1[4]{};
    uint32_t valid[4]{};
};
struct PackedSite {
    float position[3]{}, position_error=0, scale=0, scale_error=0, abs_scale=0;
    bool valid=false;
};
struct DopplerIntervals4 { float value[4]{}, error[4]{}; uint32_t valid[4]{}; };

inline float upward_float(double value) {
    return std::nextafter(static_cast<float>(value),std::numeric_limits<float>::infinity());
}
inline bool pack_orbit_lane(PackedOrbit4& out,unsigned lane,const leo_orbit_state& state) {
    if(lane>=4)return false;
    out.valid[lane]=0;
    for(unsigned c=0;c<3;++c)
        if(!std::isfinite(state.position_km[c]) || std::abs(state.position_km[c])>1e9 ||
           !std::isfinite(state.velocity_km_s[c]) || std::abs(state.velocity_km_s[c])>1e6)
            return false;
    double position_error=0,speed=0;
    for(unsigned c=0;c<3;++c) {
        out.position[c][lane]=static_cast<float>(state.position_km[c]);
        out.velocity[c][lane]=static_cast<float>(state.velocity_km_s[c]);
        position_error+=std::abs(state.position_km[c]-out.position[c][lane]);
        speed+=std::abs(state.velocity_km_s[c]);
    }
    out.position_error[lane]=upward_float(position_error);
    out.speed_l1[lane]=upward_float(speed);
    out.valid[lane]=UINT32_MAX;return true;
}
inline PackedSite pack_site(const leo_location_site& site,double scale) {
    PackedSite out;
    if(!std::isfinite(scale) || std::abs(scale)<1e-12 || std::abs(scale)>1e12)return out;
    double error=0;
    for(unsigned c=0;c<3;++c) {
        if(!std::isfinite(site.ecef_km[c]) || std::abs(site.ecef_km[c])>1e9)return out;
        out.position[c]=static_cast<float>(site.ecef_km[c]);
        error+=std::abs(site.ecef_km[c]-out.position[c]);
    }
    out.position_error=upward_float(error);out.scale=static_cast<float>(scale);
    out.scale_error=upward_float(std::abs(scale-out.scale));out.abs_scale=upward_float(std::abs(scale));
    out.valid=true;return out;
}

namespace interval4_detail {
#if defined(__ARM_NEON)
using V=float32x4_t;
using M=uint32x4_t;
inline M load_mask(const uint32_t *p){return vld1q_u32(p);}
inline M both(M a,M b){return vandq_u32(a,b);}
inline M le(V a,V b){return vcleq_f32(a,b);}
inline M lt(V a,V b){return vcltq_f32(a,b);}
inline M ge(V a,V b){return vcgeq_f32(a,b);}
inline V choose(M mask,V a,V b){return vbslq_f32(mask,a,b);}
inline void save_mask(uint32_t *p,M a){vst1q_u32(p,a);}
inline V load(const float *p){return vld1q_f32(p);}
inline V splat(float x){return vdupq_n_f32(x);}
inline V add(V a,V b){return vaddq_f32(a,b);}
inline V sub(V a,V b){return vsubq_f32(a,b);}
inline V mul(V a,V b){return vmulq_f32(a,b);}
inline V absolute(V a){return vabsq_f32(a);}
inline void save(float *p,V a){vst1q_f32(p,a);}
inline V inverse_sqrt(V x) {
    V y=vrsqrteq_f32(x);
    for(unsigned step=0;step<3;++step)y=vmulq_f32(y,vrsqrtsq_f32(vmulq_f32(x,y),y));
    return y;
}
#else
struct V {float lane[4];};
struct M {uint32_t lane[4];};
inline M load_mask(const uint32_t *p){return {{p[0],p[1],p[2],p[3]}};}
inline M both(M a,M b){for(unsigned i=0;i<4;++i)a.lane[i]&=b.lane[i];return a;}
inline M le(V a,V b){M m{};for(unsigned i=0;i<4;++i)m.lane[i]=a.lane[i]<=b.lane[i]?UINT32_MAX:0;return m;}
inline M lt(V a,V b){M m{};for(unsigned i=0;i<4;++i)m.lane[i]=a.lane[i]<b.lane[i]?UINT32_MAX:0;return m;}
inline M ge(V a,V b){M m{};for(unsigned i=0;i<4;++i)m.lane[i]=a.lane[i]>=b.lane[i]?UINT32_MAX:0;return m;}
inline V choose(M mask,V a,V b){for(unsigned i=0;i<4;++i)if(!mask.lane[i])a.lane[i]=b.lane[i];return a;}
inline void save_mask(uint32_t *p,M a){for(unsigned i=0;i<4;++i)p[i]=a.lane[i];}
inline V load(const float *p){return {{p[0],p[1],p[2],p[3]}};}
inline V splat(float x){return {{x,x,x,x}};}
inline V add(V a,V b){for(unsigned i=0;i<4;++i)a.lane[i]+=b.lane[i];return a;}
inline V sub(V a,V b){for(unsigned i=0;i<4;++i)a.lane[i]-=b.lane[i];return a;}
inline V mul(V a,V b){for(unsigned i=0;i<4;++i)a.lane[i]*=b.lane[i];return a;}
inline V absolute(V a){for(auto& x:a.lane)x=std::abs(x);return a;}
inline void save(float *p,V a){for(unsigned i=0;i<4;++i)p[i]=a.lane[i];}
inline V inverse_sqrt(V a){for(auto& x:a.lane)x=1.0f/std::sqrt(x);return a;}
#endif
}

inline DopplerIntervals4 doppler_intervals4(const PackedOrbit4& states,const PackedSite& site) {
    DopplerIntervals4 out;if(!site.valid)return out;
    using namespace interval4_detail;
    const V dx=sub(load(states.position[0]),splat(site.position[0]));
    const V dy=sub(load(states.position[1]),splat(site.position[1]));
    const V dz=sub(load(states.position[2]),splat(site.position[2]));
    const V r2=add(add(mul(dx,dx),mul(dy,dy)),mul(dz,dz));
    M valid=both(load_mask(states.valid),both(ge(r2,splat(1e-6f)),le(r2,splat(1e20f))));
    const V inverse=inverse_sqrt(choose(valid,r2,splat(1)));
    const V radial=add(add(mul(dx,load(states.velocity[0])),mul(dy,load(states.velocity[1]))),
                       mul(dz,load(states.velocity[2])));
    const V predicted=mul(mul(splat(site.scale),radial),inverse);
    save(out.value,predicted);
    constexpr float epsilon=std::numeric_limits<float>::epsilon();
    const V delta_error=add(add(load(states.position_error),splat(site.position_error)),
        mul(splat(4*epsilon),add(add(absolute(dx),absolute(dy)),absolute(dz))));
    const V relative_position_error=mul(delta_error,inverse);
    // If delta_error/r <= 1/64, the exact range exceeds half the approximate
    // range. Four times that relative error encloses the direction change.
    // 128 eps covers velocity rounding, dot/norm arithmetic and the checked
    // reciprocal error. A factor of two covers bound evaluation rounding;
    // an absolute floor covers flushed tiny intermediates. Uncertain lanes
    // remain invalid and must use the unchanged double scorer.
    const V direction_error=add(mul(splat(4),relative_position_error),splat(128*epsilon));
    const V error=add(splat(1e-6f),mul(splat(2),mul(load(states.speed_l1),
        add(mul(splat(site.abs_scale),direction_error),splat(site.scale_error)))));
    save(out.error,error);
    const V identity=mul(mul(r2,inverse),inverse);
    valid=both(valid,le(relative_position_error,splat(1.0f/64)));
    valid=both(valid,le(absolute(sub(identity,splat(1))),splat(8*epsilon)));
    valid=both(valid,le(absolute(predicted),splat(std::numeric_limits<float>::max())));
    valid=both(valid,both(ge(error,splat(0)),le(error,splat(std::numeric_limits<float>::max()))));
    save_mask(out.valid,valid);
    return out;
}

struct PackedPairThreshold {
    float delta=0,delta_error=0,guard_base=0,incumbent=0,denominator=0;
    bool valid=false;
};
inline PackedPairThreshold pack_pair_threshold(double first,double last,double incumbent,double denominator) {
    PackedPairThreshold out;
    if(!std::isfinite(first)||!std::isfinite(last)||!std::isfinite(incumbent)||
       !std::isfinite(denominator)||std::abs(first)>1e12||std::abs(last)>1e12||
       incumbent<0||incumbent>1e12||denominator<2||denominator>1e6)return out;
    const double delta=first-last;out.delta=static_cast<float>(delta);
    out.delta_error=upward_float(std::abs(delta-out.delta)+1e-12*(1+std::abs(first)+std::abs(last)));
    out.guard_base=upward_float(1+std::abs(first)+std::abs(last)+incumbent);
    out.incumbent=upward_float(incumbent);out.denominator=upward_float(denominator);
    out.valid=true;return out;
}
inline uint32_t pair_rejections4(const PackedOrbit4& first,const PackedOrbit4& last,
                                const PackedSite& site,const PackedPairThreshold& threshold) {
    if(!threshold.valid)return 0;
    using namespace interval4_detail;
    auto a=doppler_intervals4(first,site),b=doppler_intervals4(last,site);
    const V av=load(a.value),bv=load(b.value);
    const V radius=add(load(a.error),load(b.error));
    const V magnitudes=add(absolute(av),absolute(bv));
    constexpr float epsilon=std::numeric_limits<float>::epsilon();
    const V uncertainty=mul(splat(2),add(add(radius,splat(threshold.delta_error)),
        mul(splat(8*epsilon),add(splat(std::abs(threshold.delta)),magnitudes))));
    const V separation=sub(absolute(add(sub(splat(threshold.delta),av),bv)),uncertainty);
    const V guard=mul(splat(1e-6f),add(add(splat(threshold.guard_base),magnitudes),radius));
    const V target=mul(mul(add(splat(threshold.incumbent),guard),splat(threshold.denominator)),
                       splat(1+32*epsilon));
    // Strict rejection, implemented as target < separation; NaN lanes never reject.
    const M pass=both(both(load_mask(a.valid),load_mask(b.valid)),lt(target,separation));
    uint32_t lanes[4];save_mask(lanes,pass);uint32_t result=0;
    for(unsigned i=0;i<4;++i)if(lanes[i])result|=1u<<i;
    return result;
}
}
