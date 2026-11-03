#pragma once

#include <string>

namespace leo::adaptive::research {

// Research-only spelling for finite binary64 values using the conventions of
// Python float repr: shortest round-trip digits, fixed notation for decimal
// exponents -4 through 15, and an explicit fractional part for integral fixed
// values.  This is not part of the native runtime or a persisted contract.
std::string server_python_float_repr_compat(double value);

}  // namespace leo::adaptive::research
