"""Cache the original carrier-bin eligibility test by its actual bounds."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from . import receiver_build
from .receiver_build import replace


def timing(source):
    source = replace(source, "struct TimingFirst {",
                     '#include "receiver_carrier_eligibility.inc"\n\nstruct TimingFirst {\n'
                     "    CarrierEligibility carrier_eligibility;")
    source = replace(source, "    return (i < bins / 2 ? i : i - bins) * (double)w->rate / bins;",
                     "    return carrier_bin_at_rate(i, w->rate);")
    reference = """    uint16_t eligible[bins];
    int eligible_count = 0;
    for (int j = 0; j < bins; ++j) {
        double f = bin_hz(w, j) + center;
        if (ceil((lo - f) / w->rate) <= floor((hi - f) / w->rate))
            eligible[eligible_count++] = (uint16_t)j;
    }"""
    cached = """    CarrierEligibility *cache = &w->carrier_eligibility;
    if (experimental_carrier_eligibility_update(cache, w->rate, lo, hi, center) < 0)
        return 0;
    const uint16_t *eligible = cache->eligible;
    const int eligible_count = cache->count;"""
    return replace(source, reference, cached)


def overlay(build):
    def composed(output, **recipe):
        compile_source = receiver_build.subprocess.run

        def compile_cached(command, **kwargs):
            if "-c" in command:
                path = Path(command[command.index("-c") + 1])
                if path.name == "timing_first_receiver.c":
                    path.write_text(timing(path.read_text()))
            return compile_source(command, **kwargs)

        with patch.object(receiver_build, "subprocess", SimpleNamespace(run=compile_cached)):
            return build(output, **recipe)

    return composed
