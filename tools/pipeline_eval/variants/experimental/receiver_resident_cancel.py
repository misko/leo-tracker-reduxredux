"""Feed the exact signed residual into the existing scout's resident lane buffer."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from . import receiver_build
from .receiver_build import replace


HEADER = '#include "receiver_resident_cancel.h"\n'


def cancel(source):
    begin = source.index("int pilot_cancel(")
    resident = source[begin:]
    resident = replace(resident, """int pilot_cancel(const int16_t *input, int16_t *output, int lane, const float *pilot,
                 float *scratch, double epoch, double carrier_hz) {""",
                       """int pilot_cancel_resident(float *iq, const float *pilot, float *scratch,
                          double epoch, double carrier_hz) {""")
    resident = replace(resident, "    if (!input || !output || input == output || !pilot || !scratch || lane < 0 || lane > 1 ||",
                       "    if (!iq || !pilot || !scratch ||")
    resident = replace(resident, "    memcpy(output, input, 4 * samples * sizeof(*input));\n", "")
    if resident.count("a = 4 * n + 2 * lane") != 2:
        raise ValueError("Unexpected ALGO08v2 cancellation strides")
    resident = resident.replace("a = 4 * n + 2 * lane", "a = 2 * n")
    resident = resident.replace("input[a", "iq[a").replace("output[a", "iq[a")
    return source + "\n" + resident


def timing(source):
    source = replace(source, "int timing_first_detect(TimingFirst *w, const int16_t *iq, int lane, double lo, double hi,\n"
                     "                        TimingFirstResult *out) {",
                     "static int detect_lane(TimingFirst *w, const int16_t *iq, int lane, double lo, double hi,\n"
                     "                       TimingFirstResult *out, int resident) {")
    source = replace(source, "if (!w || !iq || !out", "if (!w || (!iq && !resident) || !out")
    source = replace(source, "    input(w, iq, lane, center);",
                     "    if (!resident) input(w, iq, lane, center);")
    return source + """
int timing_first_detect(TimingFirst *w, const int16_t *iq, int lane, double lo, double hi,
                        TimingFirstResult *out) {
    return detect_lane(w, iq, lane, lo, hi, out, 0);
}

int timing_first_cancel_resident(TimingFirst *w, const float *pilot, float *scratch,
                                 const TimingFirstResult *primary, double lo, double hi,
                                 TimingFirstResult *out) {
    if (!w || !primary || !primary->confirmation || (lo + hi) / 2 != 0.)
        return -1;
    if (pilot_cancel_resident((float *)w->data, pilot, scratch, primary->epoch, primary->hz))
        return -1;
    return detect_lane(w, NULL, 0, lo, hi, out, 1);
}
"""


def measure(source):
    return replace(source, """    if (pilot_cancel(iq, r->residual, lane, r->synthesis, r->rotated, p[0].epoch, p[0].hz) ||
        timing_first_detect(r->timing, r->residual, lane, lo, hi, &p[1]) ||
        portable_verifier_load(r->verify, iq, (unsigned)lane)) return -1;""",
                   """    int status;
    if ((lo + hi) / 2 == 0.) {
        status = timing_first_cancel_resident(r->timing, r->synthesis, r->rotated, &p[0], lo, hi, &p[1]);
    } else {
        status = pilot_cancel(iq, r->residual, lane, r->synthesis, r->rotated, p[0].epoch, p[0].hz) ||
                 timing_first_detect(r->timing, r->residual, lane, lo, hi, &p[1]);
    }
    if (status || portable_verifier_load(r->verify, iq, (unsigned)lane)) return -1;""")


def overlay(build):
    """Apply the overlay to generated translation units before their active compiler runs."""
    transformations = {
        "pilot_cancel.c": cancel,
        "timing_first_receiver.c": timing,
        "two_carrier_receiver.c": measure,
    }

    def composed(output, **recipe):
        if recipe.get("integer_fir") or recipe.get("short_aperture"):
            raise ValueError("Resident cancellation expects the full floating timing scout")
        compile_source = receiver_build.subprocess.run

        def compile_resident(command, **kwargs):
            if "-c" in command:
                path = Path(command[command.index("-c") + 1])
                if transform := transformations.get(path.name):
                    source = transform(path.read_text())
                    if source.startswith("#define _POSIX_C_SOURCE"):
                        # Profiling must set its feature-test macro before any header.
                        first, source = source.split("\n", 1)
                        source = first + "\n" + HEADER + source
                    else:
                        source = HEADER + source
                    path.write_text(source)
            return compile_source(command, **kwargs)

        with patch.object(receiver_build, "subprocess", SimpleNamespace(run=compile_resident)):
            return build(output, **recipe)

    return composed
