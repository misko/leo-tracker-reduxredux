#pragma once
#include "location.h"
#include <cstring>
#include <vector>

namespace leo::location::research {
// Research-only, context-owned memoization. Validate the actual state bytes in
// every requested satellite range, even when the caller reuses a generation.
class BoundStateCache {
    struct Entry { uint64_t time{};uint32_t satellite{},epoch{};leo_orbit_state state{}; };
    std::vector<Entry> entries_;
    std::vector<leo_orbit_state> authority_;
    uint64_t generation_=0;
    uint32_t satellites_=0,knots_=0,epoch_=1;
    double start_=0,step_=0;
    size_t capacity_;
    static uint64_t bits(double value) {uint64_t result;std::memcpy(&result,&value,8);return result;}
    size_t slot(unsigned satellite,uint64_t time) const {
        uint32_t h=static_cast<uint32_t>(time)^static_cast<uint32_t>(time>>32)^(satellite*2654435761u);
        h^=h>>16;h*=2246822519u;h^=h>>13;
        return h&(entries_.size()-1);
    }
public:
    explicit BoundStateCache(size_t capacity=1u<<20):capacity_(capacity) {}
    bool prepare(const leo_orbit_snapshot& s,unsigned begin,unsigned end) {
        if(!capacity_ || (capacity_&(capacity_-1)) || begin>end || end>s.satellite_count ||
           static_cast<size_t>(s.satellite_count)*s.knot_count>600000) return false;
        const bool different=s.generation!=generation_ || s.satellite_count!=satellites_ ||
            s.knot_count!=knots_ || bits(s.knot_start_s)!=bits(start_) || bits(s.knot_step_s)!=bits(step_);
        const size_t offset=static_cast<size_t>(begin)*s.knot_count;
        const size_t count=static_cast<size_t>(end-begin)*s.knot_count;
        bool changed=different;
        if(!changed && count) changed=std::memcmp(authority_.data()+offset,s.states+offset,count*sizeof(leo_orbit_state))!=0;
        try {
            if(entries_.empty()) entries_.resize(capacity_);
            if(different) authority_.assign(s.states,s.states+static_cast<size_t>(s.satellite_count)*s.knot_count);
            else if(changed) std::memcpy(authority_.data()+offset,s.states+offset,count*sizeof(leo_orbit_state));
        } catch(...) {return false;}
        if(changed) {
            if(++epoch_==0) {for(auto& e:entries_)e.epoch=0;epoch_=1;}
            generation_=s.generation;satellites_=s.satellite_count;knots_=s.knot_count;
            start_=s.knot_start_s;step_=s.knot_step_s;
        }
        return true;
    }
    bool lookup(unsigned satellite,double time,leo_orbit_state& state) const {
        if(entries_.empty())return false;
        const auto key=bits(time);const auto& e=entries_[slot(satellite,key)];
        if(e.epoch!=epoch_ || e.satellite!=satellite || e.time!=key)return false;
        state=e.state;return true;
    }
    void store(unsigned satellite,double time,const leo_orbit_state& state) {
        if(entries_.empty())return;
        const auto key=bits(time);entries_[slot(satellite,key)]={key,satellite,epoch_,state};
    }
};
}
