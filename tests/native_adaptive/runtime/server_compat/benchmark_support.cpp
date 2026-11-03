#include "server_compat.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
std::vector<std::string> fields(const std::string& line) {
    std::vector<std::string> result;
    std::size_t begin=0;
    for (;;) {
        const auto end=line.find('\t',begin);
        result.push_back(line.substr(begin,end-begin));
        if(end==std::string::npos) return result;
        begin=end+1;
    }
}
struct Input {
    std::uint32_t rate;
    std::int64_t epoch;
    double fraction,moment2,moment3;
};
struct Times {
    std::vector<double> values;
    void print() {
        if(values.empty()) { std::cout<<"null";return; }
        std::sort(values.begin(),values.end());
        double sum=0;for(double value:values) sum+=value;
        std::cout<<"{\"count\":"<<values.size()<<",\"mean_us\":"<<sum/values.size()
            <<",\"p50_us\":"<<values[(values.size()-1)/2]
            <<",\"p95_us\":"<<values[static_cast<std::size_t>(std::ceil(values.size()*.95))-1]
            <<",\"maximum_us\":"<<values.back()<<'}';
    }
};
}

int main(int argc,char** argv) {
    try {
        if(argc!=3) throw std::runtime_error("usage: benchmark-support INPUT EXPECTED");
        std::ifstream input(argv[1]),expected(argv[2]);
        if(!input || !expected) throw std::runtime_error("missing fixture");
        std::vector<Input> samples;
        std::string line,oracle;
        while(samples.size()<1024 && std::getline(input,line)) {
            if(!std::getline(expected,oracle)) throw std::runtime_error("truncated fixture");
            if(oracle=="unavailable") continue;
            const auto a=fields(line),b=fields(oracle);
            if(a.size()!=23 || b.size()!=9) throw std::runtime_error("bad fixture shape");
            samples.push_back({static_cast<std::uint32_t>(std::stoul(a[0])),
                std::stoll(a[16]),std::stod(a[17]),std::stod(b[7]),std::stod(b[8])});
        }
        if(samples.size()!=1024) throw std::runtime_error("insufficient retained prefix");
        leo::adaptive::server_compat::SupportDeriver deriver(
            leo::adaptive::server_compat::authority_binding());
        Times hits,misses;
        hits.values.reserve(1024);misses.values.reserve(1024);
        for(const auto& sample:samples) {
            const auto started=std::chrono::steady_clock::now();
            const auto value=deriver.derive(sample.rate,sample.rate/50,sample.epoch,sample.fraction);
            const auto ended=std::chrono::steady_clock::now();
            if(value.numeric.moment2!=sample.moment2 || value.numeric.moment3!=sample.moment3)
                throw std::runtime_error("support differs from oracle");
            (value.cache_hit?hits:misses).values.push_back(
                std::chrono::duration<double,std::micro>(ended-started).count());
        }
        std::cout<<std::setprecision(17)
            <<"{\"schema\":\"leo-server-support-prefix-latency/v1\","
              "\"scope\":\"first-1024-retained-DS9-candidates\","
              "\"timed_scope\":\"derive-including-decimal-formatting\","
              "\"fixture-parsing-and-verification-timed\":false,\"hits\":";
        hits.print();std::cout<<",\"misses\":";misses.print();std::cout<<"}\n";
        return 0;
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
