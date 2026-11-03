#include "process_stat.hpp"
#include <cassert>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <unistd.h>
int main(){
    int group=17;uint64_t rss=19;
    assert(!leo::adaptive::bench::process_stat("invalid",group,rss));
    assert(group==17&&rss==19);
    std::ifstream input("/proc/self/stat");std::string line;std::getline(input,line);
    assert(leo::adaptive::bench::process_stat(line.c_str(),group,rss));
    assert(group==getpgrp());
    const auto end=line.rfind(')');std::istringstream stream(line.substr(end+2));
    std::vector<std::string> fields;std::string field;while(stream>>field)fields.push_back(field);
    assert(rss==std::stoull(fields.at(21)));
    std::string unusual="123 (name with ) nested ( parentheses)";
    for(const auto& f:fields)unusual+=' '+f;
    assert(leo::adaptive::bench::process_stat(unusual.c_str(),group,rss));
    assert(group==getpgrp()&&rss==std::stoull(fields.at(21)));
    for(int bad:{2,21}){
        auto corrupt=fields;corrupt[bad]="-1";std::string text="123 (x)";
        for(const auto& f:corrupt)text+=' '+f;
        assert(!leo::adaptive::bench::process_stat(text.c_str(),group,rss));
    }
    assert(!leo::adaptive::bench::process_stat("123 (x) R 1",group,rss));
}
