#include "research/doppler_interval4.hpp"
#include <array>
#include <cstdio>
#include <ctime>

static double cpu() { timespec t{};clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t);return t.tv_sec+t.tv_nsec*1e-9; }
int main() {
    using namespace leo::location::research;
    std::array<PackedOrbit4,128> packed;
    std::array<std::array<leo_orbit_state,4>,128> states{};
    leo_location_site site{{6378.137123,203.78912,-81.12345},{1,0,0}};
    const double scale=-11200000000.0/299792.458;
    auto packed_site=pack_site(site,scale);
    for(unsigned i=0;i<states.size();++i)for(unsigned lane=0;lane<4;++lane) {
        auto& s=states[i][lane];
        for(unsigned c=0;c<3;++c) {
            s.position_km[c]=site.ecef_km[c]+500+17.31*i+1.123*lane+203.1*c;
            s.velocity_km_s[c]=7.33-.032*i-.123*lane-.77*c;
        }
        if(!pack_orbit_lane(packed[i],lane,s))return 2;
    }
    const unsigned order[4]={0,1,1,0},repeats=8192;
    for(unsigned trial=0;trial<4;++trial) {
        double checksum=0,start=cpu();unsigned invalid=0;
        for(unsigned repeat=0;repeat<repeats;++repeat)for(unsigned i=0;i<states.size();++i) {
            if(order[trial]) {
                auto interval=doppler_intervals4(packed[i],packed_site);
                for(unsigned lane=0;lane<4;++lane) {
                    checksum+=interval.value[lane];invalid+=!interval.valid[lane];
                }
            } else for(const auto& s:states[i]) {
                double d[3];for(unsigned c=0;c<3;++c)d[c]=s.position_km[c]-site.ecef_km[c];
                checksum+=scale*(d[0]*s.velocity_km_s[0]+d[1]*s.velocity_km_s[1]+d[2]*s.velocity_km_s[2])/
                    std::sqrt(d[0]*d[0]+d[1]*d[1]+d[2]*d[2]);
            }
        }
        std::printf("{\"vector\":%s,\"cpu_s\":%.17g,\"checksum\":%.17g,\"invalid\":%u}\n",
            order[trial]?"true":"false",cpu()-start,checksum,invalid);
    }
}
