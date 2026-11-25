"""Build a source-only overlay for the ordered sparse8 timing-energy prefix."""

import argparse
from hashlib import sha256
from pathlib import Path


TIMING_SHA256 = "10d8ec75ac2d6e820dd9cee184b2825b8d6510a465bbb8bfa38fc782126daea5"
SPECTRAL_SHA256 = "779d863a56ce9cfd1fa0fed80ef31115a9040307ca06df68839c0db7be27eee8"
TIMING_INCLUDE = '#include "receiver_spectral_vectors.inc"'
OVERLAY_INCLUDE = "sparse8_lag_running_prefix.inc"


def replace_one(source, old, new):
    if source.count(old) != 1:
        raise ValueError("Expected one exact location in the pinned lag kernel")
    return source.replace(old, new, 1)


def ordered_prefix(source):
    if sha256(source).hexdigest() != SPECTRAL_SHA256:
        raise ValueError("The archived spectral kernel has changed")
    start = source.decode()
    start = replace_one(start, "    prefix[0] = 0.;\n", "    double energy_sum = 0.;\n    prefix[0] = energy_sum;\n")
    start = replace_one(start, "        for (int k = 0; k < 4; ++k)\n            prefix[i + k + 1] = prefix[i + k] + energies[k];",
                        "        for (int k = 0; k < 4; ++k) {\n"
                        "            energy_sum += energies[k];\n"
                        "            prefix[i + k + 1] = energy_sum;\n"
                        "        }")
    return replace_one(start, "        prefix[i + 1] = prefix[i] + power(out[i]);",
                       "        energy_sum += power(out[i]);\n        prefix[i + 1] = energy_sum;").encode()


def overlay(timing_path, spectral_path, output):
    timing = timing_path.read_bytes()
    if sha256(timing).hexdigest() != TIMING_SHA256:
        raise ValueError("The archived sparse8 timing unit has changed")
    patched = ordered_prefix(spectral_path.read_bytes())
    timing = replace_one(timing.decode(), TIMING_INCLUDE, f'#include "{OVERLAY_INCLUDE}"')
    output.mkdir()
    (output / "timing_first_receiver.c").write_text(timing)
    (output / OVERLAY_INCLUDE).write_bytes(patched)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("timing_source", type=Path)
    parser.add_argument("spectral_include", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    overlay(args.timing_source, args.spectral_include, args.output)
