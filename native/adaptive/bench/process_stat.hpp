#pragma once
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <limits>

namespace leo::adaptive::bench {
// /proc/PID/stat field numbers: state=3, pgrp=5, rss=24. comm may contain
// spaces and parentheses, so only split after its final closing parenthesis.
inline bool process_stat(const char* line,int& group,uint64_t& rss){
    const char* end=std::strrchr(line,')');if(!end)return false;
    const char* field=end+1;int parsed_group=0;uint64_t parsed_rss=0;
    for(int i=0;i<=21;++i){
        while(*field==' '||*field=='\t')++field;
        if(!*field||*field=='\n')return false;
        if(i==2||i==21){
            if(*field<'0'||*field>'9')return false;
            errno=0;char* finish=nullptr;const auto value=std::strtoull(field,&finish,10);
            if(errno||finish==field||(*finish&&*finish!=' '&&*finish!='\t'&&*finish!='\n'))return false;
            if(i==2){if(value>static_cast<unsigned>(std::numeric_limits<int>::max()))return false;parsed_group=static_cast<int>(value);}
            else parsed_rss=value;
        }
        while(*field&&*field!=' '&&*field!='\t'&&*field!='\n')++field;
    }
    group=parsed_group;rss=parsed_rss;return true;
}
}
