#include "pipeline.hpp"

#include <cerrno>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

std::vector<std::string> fields(const std::string& line) {
    std::vector<std::string> result;
    std::size_t start=0;
    while (true) {
        const auto end=line.find('\t',start);
        result.push_back(line.substr(start,end-start));
        if (end==std::string::npos) return result;
        start=end+1;
    }
}

template <typename T> T integer(const std::string& text) {
    errno=0;char* end=nullptr;const long long value=std::strtoll(text.c_str(),&end,10);
    if (errno || end!=text.c_str()+text.size() ||
        value<static_cast<long long>(std::numeric_limits<T>::min()) ||
        value>static_cast<long long>(std::numeric_limits<T>::max()))
        throw std::runtime_error("invalid integer field");
    return static_cast<T>(value);
}

double real(const std::string& text) {
    errno=0;char* end=nullptr;const double value=std::strtod(text.c_str(),&end);
    if (errno || end!=text.c_str()+text.size()) throw std::runtime_error("invalid real field");
    return value;
}

std::vector<leo::adaptive::tracking::Candidate> candidates(const std::string& path) {
    std::ifstream input(path);if(!input)throw std::runtime_error("cannot open candidates");
    std::string line;if(!std::getline(input,line))throw std::runtime_error("empty candidates");
    std::vector<leo::adaptive::tracking::Candidate> output;
    while(std::getline(input,line)) {
        if(line.empty()) continue;
        const auto f=fields(line);
        if(f.size()!=13)throw std::runtime_error("invalid candidate row");
        output.push_back({f[0],f[1],integer<int>(f[2]),integer<int>(f[3]),f[4],real(f[5]),
            integer<std::int64_t>(f[6]),integer<std::int64_t>(f[7]),integer<std::int64_t>(f[8]),
            real(f[9]),real(f[10]),real(f[11]),real(f[12])});
    }
    return output;
}

leo::adaptive::pipeline::GraphAuthority authority(const std::string& path) {
    std::ifstream input(path);if(!input)throw std::runtime_error("cannot open graph authority");
    std::string line;if(!std::getline(input,line))throw std::runtime_error("empty graph authority");
    const auto meta=fields(line);if(meta.size()!=4 || meta[0]!="META")
        throw std::runtime_error("invalid graph metadata");
    leo::adaptive::pipeline::GraphAuthority output{meta[1],meta[2],integer<std::int64_t>(meta[3]),{}};
    if(!std::getline(input,line))throw std::runtime_error("missing graph header");
    while(std::getline(input,line)) {
        if(line.empty()) continue;
        const auto f=fields(line);
        if(f.size()!=8)throw std::runtime_error("invalid graph authority row");
        const bool inserted=output.candidates.emplace(f[0],leo::adaptive::pipeline::SupportAuthority{
            integer<std::int64_t>(f[1]),integer<std::int64_t>(f[2]),integer<std::int64_t>(f[3]),
            f[4],f[5],f[6],f[7]}).second;
        if(!inserted)throw std::runtime_error("duplicate graph candidate");
    }
    return output;
}

}  // namespace

int main(int argc,char** argv) {
    if(argc!=5) {
        std::cerr<<"usage: "<<argv[0]<<" CANDIDATES.tsv GRAPH.tsv AUTHORITY.loc1 OUTPUT.loc1\n";
        return 2;
    }
    try {
        const auto reconstructed=leo::adaptive::tracking::reconstruct(candidates(argv[1]));
        const auto location=leo::adaptive::pipeline::make_location_tracks(
            reconstructed,authority(argv[2]));
        leo::adaptive::pipeline::write_loc1(argv[3],argv[4],location);
        std::ofstream evidence(std::string(argv[4])+".tracks.tsv");
        if(!evidence) throw std::runtime_error("cannot open pipeline evidence output");
        evidence<<std::setprecision(17);
        for(std::size_t track=0;track<location.owned.size();++track) {
            const auto& item=location.owned[track];
            evidence<<"TRACK\t"<<track<<'\t'<<item.tracklet_id<<'\t'<<item.support_digest
                    <<'\t'<<item.partition_seed<<'\t'<<item.observation_ids.size()<<'\n';
            for(std::size_t point=0;point<item.observation_ids.size();++point)
                evidence<<"POINT\t"<<track<<'\t'<<item.observation_ids[point]<<'\t'
                        <<item.times_s[point]<<'\t'<<item.measured_hz[point]<<'\t'
                        <<static_cast<unsigned>(item.training_mask[point])<<'\n';
        }
        if(!evidence) throw std::runtime_error("pipeline evidence write failed");
        std::size_t observations=0,training=0;
        for(const auto& item:location.owned) {
            observations+=item.observation_ids.size();
            for(auto selected:item.training_mask)training+=selected;
        }
        std::cout<<"tracks="<<location.owned.size()<<" observations="<<observations
                 <<" training="<<training<<" output="<<argv[4]<<'\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<"pipeline: "<<error.what()<<'\n';return 1;
    }
}
