"""Replace only the resident signed subtraction in the paired-covariance receiver."""

from .receiver_build import replace


def overlay(source):
    start = source.index("int pilot_cancel_resident(")
    reference, resident = source[:start], source[start:]
    marker = "    const double d = 6.28318530717958647693 * carrier_hz / 3e7;"
    resident = replace(
        resident, marker,
        '    if (__builtin_cpu_supports("avx2") && fegetround() == FE_TONEAREST)\n'
        "        return cancel_packed(iq, pilot, scratch, epoch, carrier_hz);\n" + marker,
    )
    return reference + '#include "receiver_cancel_packed.inc"\n\n' + resident
