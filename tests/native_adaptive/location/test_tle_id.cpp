#include "tle_id.hpp"
#include <cassert>
#include <utility>
using leo::adaptive::location::parse_tle_catalogue_id;
int main() {
    for(const auto& test:{std::pair<const char*,int>{"44714",44714},
            {"    1",1},{"00001",1},{"99999",99999},{"A0001",100001},
            {"H9999",179999},{"J0000",180000},{"N9999",229999},
            {"P0000",230000},{"Z9999",339999}}) {
        std::int32_t value=0;
        assert(parse_tle_catalogue_id(test.first,value) && value==test.second);
    }
    for(const char* text:{"","1","100000","00000","     ","I0000",
            "O0000","a0001","A00+1","+0001","-0001","1    ","  A01"}) {
        std::int32_t value=123;
        assert(!parse_tle_catalogue_id(text,value) && value==123);
    }
}
