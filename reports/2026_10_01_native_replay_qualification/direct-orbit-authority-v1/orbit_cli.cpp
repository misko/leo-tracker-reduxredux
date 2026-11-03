/* Explicit replay port for the public native TLE -> ECEF snapshot API.
 * Output is little-endian satellite-major float64 [position km, velocity km/s].
 * Metadata and catalogue identity are carried in stdout, never inferred by time.
 */
#include "location.h"
#include "tle_id.hpp"
#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
long long integer(const char* text) {
    char* end=nullptr;errno=0;auto value=std::strtoll(text,&end,10);
    if(errno || !*text || *end)throw std::invalid_argument("invalid integer argument");
    return value;
}
double real(const char* text) {
    char* end=nullptr;errno=0;double value=std::strtod(text,&end);
    if(errno || !*text || *end || !std::isfinite(value))throw std::invalid_argument("invalid numeric argument");
    return value;
}
}

int main(int argc,char** argv) {
    if(argc!=7 && !(argc==14 && std::strcmp(argv[7],"--loc1-site")==0)) {
        std::cerr<<"usage: leo-orbit TLES.txt START_UTC_NS KNOT_START_S KNOT_STEP_S KNOT_COUNT OUTPUT [--loc1-site ECEF_X_KM ECEF_Y_KM ECEF_Z_KM UP_X UP_Y UP_Z]\n";
        return 2;
    }
    try {
        double site[6]{};
        if(argc==14) {
            for(unsigned i=0;i<6;++i)site[i]=real(argv[8+i]);
            const double up2=site[3]*site[3]+site[4]*site[4]+site[5]*site[5];
            if(!std::isfinite(up2) || std::abs(up2-1)>1e-6)
                throw std::invalid_argument("LOC1 site up vector must be unit length");
        }
        const auto origin=integer(argv[2]);const auto start=real(argv[3]),step=real(argv[4]);
        const auto knots=integer(argv[5]);
        if(origin<=0 || step<=0 || knots<2 || knots>2000)throw std::invalid_argument("invalid snapshot geometry");
        const unsigned short endian=1;
        if(*reinterpret_cast<const unsigned char*>(&endian)!=1)throw std::runtime_error("requires little endian target");
        std::ifstream input(argv[1]);std::string line;
        if(!std::getline(input,line))throw std::invalid_argument("missing TLE count");
        const auto count=integer(line.c_str());
        if(count<1 || count>20000)throw std::invalid_argument("invalid TLE count");
        std::vector<leo_tle_record> records(static_cast<std::size_t>(count));std::set<int> ids;
        for(auto& record:records) {
            std::string a,b;
            if(!std::getline(input,a) || !std::getline(input,b) || a.size()!=69 || b.size()!=69)
                throw std::invalid_argument("invalid TLE line length");
            std::int32_t first=0,second=0;
            if(!leo::adaptive::location::parse_tle_catalogue_id(std::string_view(a).substr(2,5),first) ||
               !leo::adaptive::location::parse_tle_catalogue_id(std::string_view(b).substr(2,5),second) ||
               first!=second || !ids.insert(first).second)throw std::invalid_argument("invalid or duplicate TLE identity");
            record.satellite_id=first;
            std::memcpy(record.line1,a.c_str(),70);std::memcpy(record.line2,b.c_str(),70);
        }
        if(std::getline(input,line))throw std::invalid_argument("trailing TLE rows");
        std::unique_ptr<leo_orbit_context,decltype(&leo_orbit_context_destroy)> context(
            leo_orbit_context_create(static_cast<uint32_t>(count),static_cast<uint32_t>(knots)),leo_orbit_context_destroy);
        if(!context)throw std::runtime_error("orbit context capacity allocation failed");
        leo_orbit_snapshot snapshot{};
        const auto status=leo_orbit_build_tle(context.get(),1,origin,start,step,static_cast<uint32_t>(knots),
                                             records.data(),static_cast<uint32_t>(count),&snapshot);
        if(status!=LEO_LOCATION_OK)throw std::runtime_error("native orbit build failed: "+std::to_string(status));
        std::ofstream output(argv[6],std::ios::binary|std::ios::trunc);
        if(argc==14) {
            // Existing LOC1 layout, zero tracks. The pipeline supplies measured
            // tracks later; catalogue order comes directly from this snapshot.
            const uint32_t header[5]={0x31434f4cU,static_cast<uint32_t>(count),
                                      static_cast<uint32_t>(knots),0,1};
            output.write(reinterpret_cast<const char*>(header),sizeof(header));
            output.write(reinterpret_cast<const char*>(&start),sizeof(start));
            output.write(reinterpret_cast<const char*>(&step),sizeof(step));
            output.write(reinterpret_cast<const char*>(site),sizeof(site));
            output.write(reinterpret_cast<const char*>(snapshot.satellite_ids),count*sizeof(int32_t));
        }
        output.write(reinterpret_cast<const char*>(snapshot.states),count*knots*sizeof(leo_orbit_state));
        output.close();if(!output)throw std::runtime_error("orbit state output failed");
        std::cout<<std::setprecision(17)<<"{\"schema\":\"leo-native-orbit-replay/v1\",\"start_utc_ns\":"<<origin
                 <<",\"knot_start_s\":"<<start<<",\"knot_step_s\":"<<step<<",\"knot_count\":"<<knots
                 <<",\"satellite_count\":"<<count<<",\"satellite_ids\":[";
        for(std::size_t i=0;i<records.size();++i)std::cout<<(i?",":"")<<records[i].satellite_id;
        std::cout<<"]}\n";return 0;
    } catch(const std::exception& error) {std::cerr<<"orbit: "<<error.what()<<'\n';return 1;}
}
