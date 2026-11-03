#include "python_float_repr_compat.hpp"

#include <algorithm>
#include <array>
#include <cfenv>
#include <clocale>
#include <cstdint>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <string>

namespace leo::adaptive::research {
namespace {

struct BigUnsigned {
    std::array<std::uint32_t, 80> words{};
    std::size_t used{};

    explicit BigUnsigned(std::uint64_t value = 0) {
        if (value != 0) {
            words[0] = static_cast<std::uint32_t>(value);
            words[1] = static_cast<std::uint32_t>(value >> 32);
            used = words[1] == 0 ? 1 : 2;
        }
    }

    void multiply10() {
        std::uint64_t carry = 0;
        for (std::size_t index = 0; index < used; ++index) {
            const std::uint64_t product = static_cast<std::uint64_t>(words[index]) * 10 + carry;
            words[index] = static_cast<std::uint32_t>(product);
            carry = product >> 32;
        }
        if (carry != 0) {
            if (used == words.size()) throw std::overflow_error("decimal distance overflow");
            words[used++] = static_cast<std::uint32_t>(carry);
        }
    }

    void shift_left(unsigned count) {
        const std::size_t whole = count / 32;
        const unsigned part = count % 32;
        if (used + whole + (part != 0) > words.size()) {
            throw std::overflow_error("binary distance overflow");
        }
        if (used == 0) return;
        for (std::size_t index = used; index-- > 0;) words[index + whole] = words[index];
        std::fill(words.begin(), words.begin() + static_cast<std::ptrdiff_t>(whole), 0);
        used += whole;
        if (part != 0) {
            std::uint64_t carry = 0;
            for (std::size_t index = whole; index < used; ++index) {
                const std::uint64_t shifted =
                    (static_cast<std::uint64_t>(words[index]) << part) | carry;
                words[index] = static_cast<std::uint32_t>(shifted);
                carry = shifted >> 32;
            }
            if (carry != 0) words[used++] = static_cast<std::uint32_t>(carry);
        }
    }
};

int compare(const BigUnsigned& left, const BigUnsigned& right) {
    if (left.used != right.used) return left.used < right.used ? -1 : 1;
    for (std::size_t index = left.used; index-- > 0;) {
        if (left.words[index] != right.words[index]) {
            return left.words[index] < right.words[index] ? -1 : 1;
        }
    }
    return 0;
}

BigUnsigned subtract(const BigUnsigned& larger, const BigUnsigned& smaller) {
    BigUnsigned output = larger;
    std::uint64_t borrow = 0;
    for (std::size_t index = 0; index < output.used; ++index) {
        const std::uint64_t subtrahend =
            (index < smaller.used ? smaller.words[index] : 0) + borrow;
        const std::uint64_t original = output.words[index];
        output.words[index] = static_cast<std::uint32_t>(original - subtrahend);
        borrow = original < subtrahend;
    }
    while (output.used != 0 && output.words[output.used - 1] == 0) --output.used;
    return output;
}

struct Decimal {
    std::uint64_t coefficient{};
    int exponent10{};
    std::string digits;
    BigUnsigned distance;
};

void normalize(Decimal& value) {
    while (value.coefficient % 10 == 0) {
        value.coefficient /= 10;
        ++value.exponent10;
    }
    value.digits = std::to_string(value.coefficient);
}

std::string scientific_text(const Decimal& value, bool negative) {
    const int scientific_exponent =
        value.exponent10 + static_cast<int>(value.digits.size()) - 1;
    std::string output = negative ? "-" : "";
    output += value.digits[0];
    if (value.digits.size() > 1) {
        output += '.';
        output.append(value.digits, 1, std::string::npos);
    }
    output += 'e';
    output += scientific_exponent < 0 ? '-' : '+';
    output += std::to_string(
        scientific_exponent < 0 ? -scientific_exponent : scientific_exponent);
    return output;
}

void exact_distance(
    Decimal& decimal,
    int unnormalized_exponent10,
    std::uint64_t absolute_bits) {
    const unsigned raw_exponent = static_cast<unsigned>((absolute_bits >> 52) & 0x7ff);
    const std::uint64_t fraction = absolute_bits & UINT64_C(0x000fffffffffffff);
    const std::uint64_t mantissa =
        raw_exponent == 0 ? fraction : fraction | UINT64_C(0x0010000000000000);
    const int exponent2 =
        raw_exponent == 0 ? -1074 : static_cast<int>(raw_exponent) - 1023 - 52;

    BigUnsigned decimal_scaled(decimal.coefficient);
    BigUnsigned binary_scaled(mantissa);
    if (unnormalized_exponent10 >= 0) {
        for (int index = 0; index < unnormalized_exponent10; ++index) {
            decimal_scaled.multiply10();
        }
    } else {
        for (int index = 0; index < -unnormalized_exponent10; ++index) {
            binary_scaled.multiply10();
        }
    }
    if (exponent2 >= 0) {
        binary_scaled.shift_left(static_cast<unsigned>(exponent2));
    } else {
        decimal_scaled.shift_left(static_cast<unsigned>(-exponent2));
    }
    const int order = compare(decimal_scaled, binary_scaled);
    decimal.distance = order < 0 ? subtract(binary_scaled, decimal_scaled)
                                 : subtract(decimal_scaled, binary_scaled);
}

bool closer(const Decimal& left, const Decimal& right) {
    const int order = compare(left.distance, right.distance);
    if (order != 0) return order < 0;
    const bool left_even = left.coefficient % 2 == 0;
    const bool right_even = right.coefficient % 2 == 0;
    if (left_even != right_even) return left_even;
    return left.coefficient < right.coefficient;
}

Decimal seed_decimal(const std::string& shortest) {
    std::size_t begin = shortest[0] == '-' ? 1 : 0;
    const std::size_t exponent_mark = shortest.find('e', begin);
    const std::size_t mantissa_end =
        exponent_mark == std::string::npos ? shortest.size() : exponent_mark;
    const std::size_t decimal = shortest.find('.', begin);
    const std::size_t digits_before_decimal =
        decimal == std::string::npos || decimal >= mantissa_end
            ? mantissa_end - begin
            : decimal - begin;
    std::string digits;
    for (std::size_t index = begin; index < mantissa_end; ++index) {
        if (shortest[index] != '.') digits += shortest[index];
    }
    int explicit_exponent = 0;
    if (exponent_mark != std::string::npos) {
        std::size_t index = exponent_mark + 1;
        bool negative = false;
        if (index < shortest.size() && (shortest[index] == '+' || shortest[index] == '-')) {
            negative = shortest[index] == '-';
            ++index;
        }
        if (index == shortest.size()) throw std::runtime_error("shortest exponent is empty");
        for (; index < shortest.size(); ++index) {
            const char digit = shortest[index];
            if (digit < '0' || digit > '9' || explicit_exponent > 1000) {
                throw std::runtime_error("shortest exponent parsing failed");
            }
            explicit_exponent = explicit_exponent * 10 + digit - '0';
        }
        if (negative) explicit_exponent = -explicit_exponent;
    }
    Decimal output;
    output.coefficient = std::stoull(digits);
    output.exponent10 = explicit_exponent + static_cast<int>(digits_before_decimal) -
        static_cast<int>(digits.size());
    normalize(output);
    return output;
}

}  // namespace

std::string server_python_float_repr_compat(double value) {
    if (!std::isfinite(value)) {
        throw std::invalid_argument("Python compatibility value must be finite");
    }
    if (std::fegetround() != FE_TONEAREST) {
        throw std::invalid_argument("Python compatibility requires round-to-nearest");
    }
    const lconv* numeric = std::localeconv();
    if (numeric == nullptr || numeric->decimal_point == nullptr ||
        std::strcmp(numeric->decimal_point, ".") != 0) {
        throw std::invalid_argument("Python compatibility requires C numeric conventions");
    }
    if (value == 0.0) return std::signbit(value) ? "-0.0" : "0.0";

    // The target's Linaro GCC 7.3.1 libstdc++ has no floating-point to_chars.
    // Search the bounded binary64 significant-digit range instead: printf supplies the
    // nearest decimal at each precision, and the first one that round-trips is
    // the shortest-precision representation.  This named research profile
    // requires the C numeric locale, as the canonical server JSON does.
    char buffer[64]{};
    const bool negative = std::signbit(value);
    std::uint64_t raw_bits = 0;
    std::memcpy(&raw_bits, &value, sizeof(raw_bits));
    const std::uint64_t absolute_bits = raw_bits & UINT64_C(0x7fffffffffffffff);
    Decimal selected;
    bool selected_valid = false;
    for (int precision = 1; precision <= std::numeric_limits<double>::max_digits10;
         ++precision) {
        const int length = std::snprintf(buffer, sizeof(buffer), "%.*g", precision, value);
        if (length <= 0 || static_cast<std::size_t>(length) >= sizeof(buffer)) {
            throw std::runtime_error("binary64 formatting failed");
        }
        Decimal seed = seed_decimal(buffer);
        // %g removes trailing zeros. Restore the requested precision's grid
        // before examining adjacent decimals; an adjacent shortest value can
        // require a nonzero digit in a position that %g removed from its own
        // nearest result (the 2^-1017 counterexample exercises this case).
        while (seed.digits.size() < static_cast<std::size_t>(precision)) {
            seed.coefficient *= 10;
            --seed.exponent10;
            seed.digits += '0';
        }
        Decimal precision_selected;
        bool precision_selected_valid = false;
        // Correctly rounded %g identifies the closest point on the decimal
        // grid.  A binary64 round-trip interval is convex and contains the
        // exact value, so only that point and the immediately adjacent point
        // on either side can enter it.  Four neighbors each way intentionally
        // exceed that bound and make the search insensitive to a decimal tie.
        for (int delta = -4; delta <= 4; ++delta) {
            if (delta < 0 && seed.coefficient < static_cast<std::uint64_t>(-delta) + 1) {
                continue;
            }
            Decimal candidate;
            candidate.coefficient = static_cast<std::uint64_t>(
                static_cast<std::int64_t>(seed.coefficient) + delta);
            candidate.exponent10 = seed.exponent10;
            candidate.digits = std::to_string(candidate.coefficient);
            const std::string text = scientific_text(candidate, negative);
            char* end = nullptr;
            const double parsed = std::strtod(text.c_str(), &end);
            // strtod may set ERANGE for a correctly rounded subnormal; bit
            // identity and complete consumption are the round-trip criterion.
            if (end != text.c_str() + text.size() ||
                std::memcmp(&parsed, &value, sizeof(value)) != 0) continue;
            exact_distance(candidate, seed.exponent10, absolute_bits);
            normalize(candidate);
            if (!precision_selected_valid ||
                candidate.digits.size() < precision_selected.digits.size() ||
                (candidate.digits.size() == precision_selected.digits.size() &&
                    closer(candidate, precision_selected))) {
                precision_selected = std::move(candidate);
                precision_selected_valid = true;
            }
        }
        if (precision_selected_valid) {
            selected = std::move(precision_selected);
            selected_valid = true;
            break;
        }
    }
    if (!selected_valid) throw std::runtime_error("no shortest round-trip decimal selected");
    const std::string& digits = selected.digits;
    const int scientific_exponent =
        selected.exponent10 + static_cast<int>(digits.size()) - 1;
    const std::string sign = negative ? "-" : "";

    // CPython's finite-float repr uses fixed notation in this exponent range.
    if (scientific_exponent >= -4 && scientific_exponent < 16) {
        std::string output = sign;
        if (scientific_exponent < 0) {
            output += "0.";
            output.append(static_cast<std::size_t>(-scientific_exponent - 1), '0');
            output += digits;
            return output;
        }
        const std::size_t integer_digits =
            static_cast<std::size_t>(scientific_exponent + 1);
        if (digits.size() <= integer_digits) {
            output += digits;
            output.append(integer_digits - digits.size(), '0');
            output += ".0";
        } else {
            output.append(digits, 0, integer_digits);
            output += '.';
            output.append(digits, integer_digits, std::string::npos);
        }
        return output;
    }

    std::string output = sign;
    output += digits[0];
    if (digits.size() > 1) {
        output += '.';
        output.append(digits, 1, std::string::npos);
    }
    output += 'e';
    output += scientific_exponent < 0 ? '-' : '+';
    const unsigned magnitude = static_cast<unsigned>(
        scientific_exponent < 0 ? -scientific_exponent : scientific_exponent);
    if (magnitude < 10) output += '0';
    output += std::to_string(magnitude);
    return output;
}

}  // namespace leo::adaptive::research
