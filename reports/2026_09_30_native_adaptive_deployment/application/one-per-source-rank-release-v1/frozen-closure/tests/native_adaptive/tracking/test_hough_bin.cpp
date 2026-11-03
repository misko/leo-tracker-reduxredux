#include "hough_bin.hpp"

#include <cassert>
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>

namespace {
std::size_t reference(double value,double spacing,std::size_t count) {
    double remainder=std::fmod(value,spacing);
    if (remainder<0.0) remainder+=spacing;
    return static_cast<std::size_t>(std::floor(
        remainder/(spacing/static_cast<double>(count))))%count;
}

void check(double value,double spacing,std::size_t count) {
    const leo::adaptive::tracking::detail::HoughBin bin(
        spacing,spacing/static_cast<double>(count),count);
    assert(bin(value)==reference(value,spacing,count));
}
}

int main() {
    std::uint64_t state=0x123456789abcdefULL;
    std::size_t checked=0,fast=0;
    for (const int rounding:{FE_TONEAREST,FE_DOWNWARD,FE_UPWARD,FE_TOWARDZERO}) {
        assert(std::fesetround(rounding)==0);
        for (const double spacing:{1.0/4.4e-6,227272.123456789,0x1p-1013,0x1p-900,0x1p900}) {
            const double width=spacing/512.0;
            const leo::adaptive::tracking::detail::HoughBin bin(spacing,width,512);
            for (int i=0;i<100000;++i) {
                state^=state<<13; state^=state>>7; state^=state<<17;
                const double coordinate=static_cast<double>(state&0xffffffffULL)/
                    2048.0-0x1p20;
                const double value=coordinate*width;
                std::size_t actual=0;
                fast+=bin.fast_bin(value,actual);
                assert(bin(value)==reference(value,spacing,512));
                ++checked;
            }
            for (const int boundary:{-1048576,-65536,-513,-512,-1,0,1,511,512,65536,1048576}) {
                double value=static_cast<double>(boundary)*width;
                for (int i=0;i<8;++i) {
                    check(value,spacing,512); ++checked;
                    value=std::nextafter(value,std::numeric_limits<double>::infinity());
                }
                value=static_cast<double>(boundary)*width;
                for (int i=0;i<8;++i) {
                    check(value,spacing,512); ++checked;
                    value=std::nextafter(value,-std::numeric_limits<double>::infinity());
                }
            }
            for (const double value:{-0.0,0.0,-width*0x1p22,width*0x1p22})
                check(value,spacing,512);
        }
        for (const std::size_t count:{1U,3U,511U,513U,65536U})
            for (const double value:{-1e6,-0.0001,0.0,0.25,1e6})
                check(value,227272.0,count);
    }
    assert(std::fesetround(FE_TONEAREST)==0);
    assert(fast>checked/2);
    std::size_t result=0;
    const double tiny=std::numeric_limits<double>::min();
    const leo::adaptive::tracking::detail::HoughBin fallback(tiny,tiny/512.0,512);
    assert(!fallback.fast_bin(tiny/3.0,result));
    check(tiny/3.0,tiny,512);
    std::cout<<"hough bins exact: "<<checked<<", fast: "<<fast<<'\n';
}
