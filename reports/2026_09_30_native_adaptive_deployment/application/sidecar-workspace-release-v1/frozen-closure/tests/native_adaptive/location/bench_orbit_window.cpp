#include "location.h"
#include "tle_id.hpp"
#include <chrono>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

// CPU-only full-catalogue cache benchmark. No radio, stored winner or shortlist.
// This measures two builds, not a global interpolation accuracy guarantee.
int main(int argc,char** argv) {
    try {
        if(argc!=3) throw std::runtime_error("usage: bench-orbit-window TLES START_UTC_NS");
        std::size_t parsed=0;
        const auto epoch=std::stoll(argv[2],&parsed);
        if(parsed!=std::strlen(argv[2]) || epoch<=0)
            throw std::runtime_error("invalid UTC epoch");
        std::ifstream input(argv[1]);std::size_t count=0;
        if(!(input>>count) || !count || count>20000)
            throw std::runtime_error("invalid catalogue count");
        std::string line;std::getline(input,line);
        std::vector<leo_tle_record> records(count);std::set<int> identities;
        for(auto& record:records) {
            std::string first,second;
            if(!std::getline(input,first) || !std::getline(input,second) ||
               first.size()!=69 || second.size()!=69 || first[0]!='1' || second[0]!='2' ||
               first.substr(2,5)!=second.substr(2,5))
                throw std::runtime_error("invalid TLE pair");
            if(!leo::adaptive::location::parse_tle_catalogue_id(
                    std::string_view(first).substr(2,5),record.satellite_id))
                throw std::runtime_error("invalid satellite identity");
            if(!identities.insert(record.satellite_id).second)
                throw std::runtime_error("duplicate or malformed identity");
            std::memcpy(record.line1,first.data(),69);
            std::memcpy(record.line2,second.data(),69);
        }
        input>>std::ws;
        if(!input.eof())throw std::runtime_error("trailing catalogue records");
        constexpr std::uint32_t knots=96;
        constexpr double step=10;
        using Clock=std::chrono::steady_clock;
        const auto before=Clock::now();
        std::unique_ptr<leo_orbit_context,decltype(&leo_orbit_context_destroy)> context(
            leo_orbit_context_create(static_cast<std::uint32_t>(count),knots),
            &leo_orbit_context_destroy);
        if(!context)throw std::runtime_error("orbit arena allocation failed");
        const auto allocated=Clock::now();
        double build_ms[2]{};
        for(std::uint64_t generation=1;generation<=2;++generation) {
            const double start=-20+320*static_cast<double>(generation-1);
            leo_orbit_snapshot snapshot{};
            const auto start_build=Clock::now();
            if(leo_orbit_build_tle(context.get(),generation,epoch,start,step,knots,
                    records.data(),static_cast<std::uint32_t>(count),&snapshot)!=LEO_LOCATION_OK)
                throw std::runtime_error("full catalogue orbit build failed");
            build_ms[generation-1]=std::chrono::duration<double,std::milli>(
                Clock::now()-start_build).count();
            if(snapshot.generation!=generation || snapshot.satellite_count!=count ||
               snapshot.knot_count!=knots || snapshot.knot_step_s!=step)
                throw std::runtime_error("orbit metadata differs");
            // Exercise every catalogue member at both boundaries and a midpoint.
            for(std::uint32_t satellite=0;satellite<count;++satellite) {
                if(snapshot.satellite_ids[satellite]!=records[satellite].satellite_id)
                    throw std::runtime_error("catalogue identity changed");
                for(double time:{start,start+475,start+950}) {
                    leo_orbit_state state{};
                    if(leo_orbit_interpolate(&snapshot,satellite,time,&state)!=LEO_LOCATION_OK)
                        throw std::runtime_error("orbit coverage failed");
                }
            }
        }
        std::cout<<std::setprecision(17)
            <<"{\"schema\":\"leo-orbit-window-benchmark/v1\",\"catalogue_records\":"<<count
            <<",\"knots\":96,\"step_seconds\":10,\"coverage_seconds\":950"
            <<",\"state_bank_bytes\":"<<count*knots*sizeof(leo_orbit_state)*2U
            <<",\"allocation_ms\":"<<std::chrono::duration<double,std::milli>(allocated-before).count()
            <<",\"first_build_ms\":"<<build_ms[0]<<",\"shifted_build_ms\":"<<build_ms[1]
            <<",\"generations\":2,\"catalogue_coverage_checks\":"<<count*6U
            <<",\"global_interpolation_accuracy_claimed\":false}\n";
        return 0;
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
