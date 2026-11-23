"""Run one authentic refined-CFO receiver and original solver on signed DS30-0016."""

import argparse
from pathlib import Path
import subprocess

from empty_bootstrap import checked
from raw_0016_best_trial import HERE, ORIGINAL, command, condition, configuration, measure_mode, seal, sha
from short_cfo_raw import EXTENSION_SHA256, FREEZE_SHA256, LIBRARY_SHA256, POLICY_SHA256, STEP


ORDER = ("candidate",)
PROTOCOL_SHA = "2d252f55c330e4cb2e239c7c603cf6be102d33a9ee7dd16bdda284b1b4c57ada"
LIBRARY = Path("/dev/shm/leo-v3-short-cfo-held01/build/tail.so")
FREEZE = Path("/dev/shm/leo-v3-short-cfo-dev02/freeze.json")
HISTORICAL = Path("/dev/shm/leo-v3-raw-0016-best-results-01")
HISTORICAL_SEAL = "e011f66be6db6f04473cc7be701ca30979c5af358e54f71cba9daf9b18783b6f"
HISTORICAL_SCORE = "be25b54299e9d7923b4119ce9112b78456c4ecedb35661fc0d83294c5ffa38f6"
WRAPPER = HERE/"short_cfo_raw.py"
FAILED = Path("/dev/shm/leo-v3-raw-cfo-0016-result02")
FAILED_CLOCK_SHA = "867d83b642e25ff17a234970eed7268e0eb85eac04104e20be7b5c96a308cbf4"
FIRST_CONDITIONING_SHA = "8639fa68cc0dd0f0f3ee0afcfc4feb971d599bb32c02e159bab872e01861b89c"


def receiver_preflight(root, argv, env, *, capabilities=("--exact-graph-reuse",)):
    library_flag = "--cfo-refinement-library"
    library = argv[argv.index(library_flag)+1]
    help_check = subprocess.run([*argv[:3], library_flag, library, "--help"],
                                env=env, capture_output=True, text=True, timeout=15)
    if help_check.returncode or any(flag not in help_check.stdout for flag in capabilities):
        raise ValueError("Refined receiver did not reach the original bootstrap CLI: "+help_check.stderr)
    dummy = argv.copy()
    dummy_recording, dummy_output = root/"nonexistent-recording", root/"preflight-only"
    dummy[dummy.index("--recording")+1] = dummy_recording
    dummy[dummy.index("--output")+1] = dummy_output
    check = subprocess.run(dummy, env=env, capture_output=True, text=True, timeout=15)
    if check.returncode != 1 or "FileNotFoundError" not in check.stderr or str(dummy_recording) not in check.stderr or dummy_output.exists():
        raise ValueError("Expected the original inventory boundary to reject a nonexistent recording: "+check.stderr)
    return dict(help=True, expected_failure_exit=check.returncode, stderr=check.stderr)


def launch(root, *, resident_recovery=False):
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
    if resident_recovery:
        checked(FAILED/"candidate-clock.json", FAILED_CLOCK_SHA)
        checked(FAILED/"conditioning.json", FIRST_CONDITIONING_SHA)
        document.update(failed_startup_clock_sha256=FAILED_CLOCK_SHA, first_conditioning_sha256=FIRST_CONDITIONING_SHA)
    recording, manifests, total, libraries, residency, env = configuration(
        root, ORIGINAL, selection=document, launch_order=ORDER)
    library = root/"cfo-refinement.so"
    library.write_bytes(checked(LIBRARY, LIBRARY_SHA256))
    argv = command("candidate", root, recording, libraries, pairs.NAMED_V3)
    argv[2] = WRAPPER
    argv.extend(("--cfo-refinement-library", library))
    write(root/"preflight.json", receiver_preflight(root, argv, env))
    condition(root, manifests, total, residency, ORIGINAL, allow_read=not resident_recovery)
    measure_mode(root, "candidate", argv, env, residency)
    write(root/"prediction-seal.json", seal(root, ORDER) | {"preflight.json": sha((root/"preflight.json").read_bytes())})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--resident-recovery", action="store_true")
    args = parser.parse_args()
    launch(args.root, resident_recovery=args.resident_recovery)
