#include "runtime.hpp"
#include "sha256.hpp"
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>
int main(int argc,char** argv) {
    try {
        if(argc!=8) throw std::invalid_argument("usage: leo-windows FILE RATE RX FIRST END VISIT CHUNK_SAMPLES");
        auto number=[](const char* text) {size_t end=0;const std::string s(text);
            if(s.empty()||s[0]=='-') throw std::invalid_argument("invalid unsigned integer");
            auto value=std::stoull(s,&end);if(end!=s.size()) throw std::invalid_argument("invalid integer");return value;};
        const auto rate=number(argv[2]),rx=number(argv[3]),chunk=number(argv[7]);
        if(rate>10000000||rx>2||!rx||!chunk||chunk>10000000) throw std::invalid_argument("invalid bounds");
        const leo::adaptive::Visit visit{1,number(argv[6]),number(argv[4]),number(argv[5]),
            static_cast<uint32_t>(rate),static_cast<uint32_t>(rx),11200000000.};
        leo::adaptive::WindowAssembler assembler(static_cast<uint32_t>(rate),static_cast<uint32_t>(rx),
            [](const leo::adaptive::Window& w) {
                const std::string bytes(reinterpret_cast<const char*>(w.iq),w.samples*w.visit.receivers*4);
                std::cout<<w.index<<'\t'<<w.first<<'\t'<<w.samples<<'\t'<<leo::adaptive::sha256(bytes)<<'\n';
            });
        std::ifstream input(argv[1],std::ios::binary);if(!input) throw std::runtime_error("cannot open IQ");
        std::vector<int16_t> buffer(chunk*rx*2);assembler.begin(visit);auto position=visit.first;
        while(position<visit.end) {
            const auto count=std::min<uint64_t>(chunk,visit.end-position);
            const auto bytes=count*rx*4;
            if(!input.read(reinterpret_cast<char*>(buffer.data()),static_cast<std::streamsize>(bytes)))
                throw std::runtime_error("truncated IQ");
            assembler.push(position,buffer.data(),count);position+=count;
        }
        if(input.peek()!=std::char_traits<char>::eof()) throw std::runtime_error("extra IQ");
        assembler.finish();if(assembler.stats().missing) throw std::runtime_error("missing window");
        return 0;
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 2;}
}
