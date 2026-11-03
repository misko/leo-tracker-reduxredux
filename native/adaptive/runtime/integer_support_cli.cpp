// Batch adapter for the existing integer (zero-offset) support derivation.
#include "runtime.hpp"
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
int main(){try{
    std::cout<<std::setprecision(17);std::string line;
    while(std::getline(std::cin,line)){
        std::istringstream in(line);uint32_t rate,samples;int64_t epoch;std::string extra;
        if(!(in>>rate>>samples>>epoch)||(in>>extra))throw std::runtime_error("invalid support input");
        auto s=leo::adaptive::fractional_support(rate,samples,epoch,0.0);
        std::cout<<s.first<<'\t'<<s.end<<'\t'<<s.center<<'\t'<<s.moment2<<'\t'<<s.moment3<<'\n';
    }
    if(!std::cin.eof())throw std::runtime_error("support input failure");
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}}
