#include "research/catalogue_index.hpp"
#include <cassert>
#include <random>

int main() {
    std::mt19937 random(91827);
    std::vector<int32_t> ids(11128);
    for(auto& id:ids)id=static_cast<int32_t>(random()%20000)-10000;
    leo::location::research::CatalogueIndex index(ids.data(),static_cast<uint32_t>(ids.size()));
    for(int32_t id=-11000;id<=11000;++id) {
        const auto found=std::find(ids.begin(),ids.end(),id);
        const uint32_t expected=found==ids.end()?UINT32_MAX:static_cast<uint32_t>(found-ids.begin());
        assert(index.find(id)==expected);
    }
    leo::location::research::CatalogueIndex empty(nullptr,0);
    assert(empty.find(0)==UINT32_MAX);
}
