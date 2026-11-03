#include "research/bound_state_cache.hpp"
#include <cassert>

int main() {
    int32_t ids[2]={1,2};leo_orbit_state states[4]{};
    leo_orbit_snapshot snapshot{1,0,0,10,2,2,ids,states};
    leo::location::research::BoundStateCache cache(8);
    assert(cache.prepare(snapshot,0,1));
    leo_orbit_state result{},value{};value.position_km[0]=123;
    assert(!cache.lookup(0,1,result));cache.store(0,1,value);
    assert(cache.lookup(0,1,result) && result.position_km[0]==123);
    assert(cache.prepare(snapshot,0,1) && cache.lookup(0,1,result));
    // A same-generation mutation still invalidates when its range is used.
    states[0].position_km[0]=4;
    assert(cache.prepare(snapshot,0,1) && !cache.lookup(0,1,result));
    cache.store(0,1,value);states[2].position_km[0]=5;
    assert(cache.prepare(snapshot,1,2) && !cache.lookup(0,1,result));
    cache.store(1,1,value);snapshot.generation=2;
    assert(cache.prepare(snapshot,1,2) && !cache.lookup(1,1,result));
    cache.store(1,1,value);snapshot.knot_step_s=20;
    assert(cache.prepare(snapshot,1,2) && !cache.lookup(1,1,result));
    // Collisions evict; a distinct key cannot return another state's value.
    for(unsigned i=0;i<100;++i) {value.position_km[0]=i;cache.store(0,i,value);}
    for(unsigned i=0;i<100;++i) if(cache.lookup(0,i,result)) assert(result.position_km[0]==i);
    assert(!cache.prepare(snapshot,2,1));
    leo::location::research::BoundStateCache disabled(0);
    assert(!disabled.prepare(snapshot,0,2));
}
