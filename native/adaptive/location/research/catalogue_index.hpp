#pragma once
#include <algorithm>
#include <cstdint>
#include <utility>
#include <vector>

namespace leo::location::research {
// Private immutable-catalogue lookup. Duplicate IDs retain the first original
// index, matching std::find; this does not reorder the scientific catalogue.
class CatalogueIndex {
    std::vector<std::pair<int32_t,uint32_t>> values_;
public:
    CatalogueIndex(const int32_t* ids,uint32_t count) {
        values_.reserve(count);
        for(uint32_t i=0;i<count;++i)values_.emplace_back(ids[i],i);
        std::sort(values_.begin(),values_.end());
    }
    uint32_t find(int32_t id)const {
        const auto found=std::lower_bound(values_.begin(),values_.end(),std::make_pair(id,uint32_t{0}));
        return found!=values_.end() && found->first==id?found->second:UINT32_MAX;
    }
};
}
