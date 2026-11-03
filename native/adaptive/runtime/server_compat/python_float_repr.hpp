#pragma once

#include <string>

namespace leo::adaptive::server_compat::detail {

// Profile-private spelling for finite binary64 values using the conventions of
// Python float repr: shortest round-trip digits, fixed notation for decimal
// exponents -4 through 15, and an explicit fractional part for integral fixed
// values. This is not a standalone public or persisted contract.
std::string python_float_repr(double value);

}  // namespace leo::adaptive::server_compat::detail
