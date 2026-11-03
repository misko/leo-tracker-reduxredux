#include "runtime.hpp"
#include <iostream>
#include <iomanip>
#include <stdexcept>
#include <string>
int main(int argc,char** argv) {
    try {
        if(argc!=5) throw std::invalid_argument("rate probe_samples integer_epoch fractional_offset");
        auto s=leo::adaptive::fractional_support(std::stoul(argv[1]),std::stoul(argv[2]),
                                                std::stoll(argv[3]),std::stod(argv[4]));
        std::cout<<std::setprecision(17)<<"{\"first\":"<<s.first<<",\"end\":"<<s.end
                 <<",\"center\":"<<s.center<<",\"moment2\":"<<s.moment2
                 <<",\"moment3\":"<<s.moment3<<",\"symbols\":"<<s.symbols<<"}\n";
        return 0;
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 2;}
}
