"""Run one authentic refined-CFO receiver and original solver on signed DS30-0016."""

import argparse
from pathlib import Path
import subprocess

from empty_bootstrap import RELEASE, checked
from raw_0016_best_trial import HERE, ORIGINAL, command, condition, configuration, measure_mode, seal, sha
from short_cfo_raw import EXTENSION_SHA256, FREEZE_SHA256, LIBRARY_SHA256, POLICY_SHA256, STEP


ORDER = ("candidate",)
PROTOCOL_SHA = "d693f5dc1b893a33a94713e7b6501a4e6902b87bbf7682c97c34d44acf77fb61"
LIBRARY = Path("/dev/shm/leo-v3-short-cfo-held01/build/tail.so")
FREEZE = Path("/dev/shm/leo-v3-short-cfo-dev02/freeze.json")
HISTORICAL = Path("/dev/shm/leo-v3-raw-0016-best-results-01")
HISTORICAL_SEAL = "e011f66be6db6f04473cc7be701ca30979c5af358e54f71cba9daf9b18783b6f"
HISTORICAL_SCORE = "be25b54299e9d7923b4119ce9112b78456c4ecedb35661fc0d83294c5ffa38f6"
WRAPPER = HERE/"short_cfo_raw.py"


def launch(root):
    from aperture_trial import read, write
    from short_raw_diagnostic import pairs

    checked(HERE/"raw-cfo-0016-protocol.md", PROTOCOL_SHA)
    checked(HISTORICAL/"prediction-seal.json", HISTORICAL_SEAL)
    checked(FREEZE, FREEZE_SHA256)
    freeze = read(FREEZE)
    if freeze["step"] != STEP or freeze["driver_sha256"] != POLICY_SHA256 or freeze["extension_sha256"] != EXTENSION_SHA256:
        raise ValueError("Donor freeze differs from the tested held-lane procedure")
    document = dict(protocol_sha256=PROTOCOL_SHA, donor_freeze_sha256=FREEZE_SHA256,
                    implementation_sha256=sha(WRAPPER.read_bytes()), cfo_library_sha256=LIBRARY_SHA256,
                    historical_seal_sha256=HISTORICAL_SEAL)
    recording, manifests, total, libraries, residency, env = configuration(
        root, ORIGINAL, selection=document, launch_order=ORDER)
    library = root/"cfo-refinement.so"
    library.write_bytes(checked(LIBRARY, LIBRARY_SHA256))
    # The dry startup exercises source imports and the verified dynamic symbol, with no recording argument.
    startup = subprocess.run([RELEASE/"venv/bin/python", "-IB", WRAPPER, "--cfo-refinement-library", library, "--help"],
                             env=env, capture_output=True, timeout=15)
    if startup.returncode or b"--exact-graph-reuse" not in startup.stdout:
        raise ValueError("Refined receiver did not reach the original bootstrap CLI: "+startup.stderr.decode(errors="replace"))
    condition(root, manifests, total, residency, ORIGINAL)
    argv = command("candidate", root, recording, libraries, pairs.NAMED_V3)
    argv[2] = WRAPPER
    argv.extend(("--cfo-refinement-library", library))
    measure_mode(root, "candidate", argv, env, residency)
    write(root/"prediction-seal.json", seal(root, ORDER))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    launch(parser.parse_args().root)
