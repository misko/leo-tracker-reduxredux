#pragma once

#include <cmath>
#include <cstddef>
#include <cstdint>

namespace leo::adaptive::tracking::detail {

// Internal integer-bin accelerator; no approximate scientific value escapes.
// Geometry is validated by the reconstructor before constructing this object.
class HoughBin {
public:
    HoughBin(double spacing, double width, std::size_t count)
        : spacing_(spacing), width_(width), count_(count),
          fast_(count==512U && std::isfinite(spacing) && spacing>0.0 &&
                std::isnormal(width) && width*512.0==spacing) {}

    bool fast_bin(double value, std::size_t& result) const {
        if (!fast_) return false;
        const double quotient=value/width_;
        // Keep integer conversion exact and quotient rounding error below
        // 2^-32 even with directed rounding. The original remainder/add/divide
        // path contributes much less than 2^-32 in these bin coordinates.
        if (!(std::abs(quotient)<0x1p20)) return false;
        std::int32_t integer=static_cast<std::int32_t>(quotient);
        if (quotient<static_cast<double>(integer)) --integer;
        const double fraction=quotient-static_cast<double>(integer);
        // A deliberately wide exclusion zone also covers subtraction rounding.
        // Near any integer boundary use the original expression unchanged.
        constexpr double guard=0x1p-20;
        if (!(fraction>guard && fraction<1.0-guard)) return false;
        result=static_cast<std::uint32_t>(integer)&511U;
        return true;
    }

    std::size_t operator()(double value) const {
        std::size_t result=0;
        if (fast_bin(value,result)) return result;
        double remainder=std::fmod(value,spacing_);
        if (remainder<0.0) remainder+=spacing_;
        return static_cast<std::size_t>(std::floor(remainder/width_))%count_;
    }

private:
    double spacing_,width_;
    std::size_t count_;
    bool fast_;
};

} // namespace leo::adaptive::tracking::detail
