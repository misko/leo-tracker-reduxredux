"""Run the saved weak positive worker with the existing detector deferral."""

import argparse
import importlib._bootstrap as imports
import json
from pathlib import Path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from saved_overhead import now
import weak_all8_combined as weak
import weak_publisher_attribution as attribution


PROTOCOL = HERE/"weak-positive-import-protocol.md"
SCANNER, POSITION = "tools.algo08_scan", "tools.algo08_position"
UNUSED = ("tools.pipeline_eval.qualification.blind_compact_run",
          "tools.pipeline_eval.variants.differential_pilot", "scipy.signal")
LIVE = ("scipy.stats", "matplotlib", "tools.pipeline_eval.variants.v5_core")
LAZY_PIN = "12762d04578335a8befb40eca46862701efd1991d01268dba6748925a4c8612f"
PROFILE_ROOT = Path("/dev/shm/leo-v3-weak-publisher-attribution-result01")
PROFILE_PIN = "0e1c708d40945d57fe53496abcd06684277b870da1398140e28ccefbfac3cd2d"


def worker(root):
    import raw_cfo_north_trial as trial

    weak.staged.checked(HERE/"lazy_scanner_detector.py", LAZY_PIN)
    original, original_import = trial.publish_saved, imports._find_and_load
    active, import_times = {}, {}

    def timed(name, mechanism):
        if name not in (SCANNER, POSITION) or name in sys.modules:
            return original_import(name, mechanism)
        start = now()
        answer = original_import(name, mechanism)
        finish = now()
        import_times[name] = {"cpu_ns": finish[0]-start[0], "elapsed_ns": finish[1]-start[1]}
        return answer

    def launch_saved(*args, flags, **kwargs):
        import unified_short_bootstrap as unified

        publish = unified.publish_active

        def publish_with_audit(*values, **options):
            return publish(*values, **options, detector_import_audit=active)

        with patch.object(unified, "publish_active", publish_with_audit):
            return original(*args, flags=(*flags, "--lazy-scanner-detector"), **kwargs)

    with (patch.object(trial, "publish_saved", launch_saved),
          patch.object(imports, "_find_and_load", timed)):
        weak.worker(root)
    watched = (*UNUSED, *LIVE, SCANNER, POSITION,
               "tools.pipeline_eval.qualification.compact_history_replay",
               "tools.pipeline_eval.variants.v5_orbit_domain")
    weak.write(root/"imports.json", dict(detector_import=active, first_load=import_times,
               loaded={name: name in sys.modules for name in watched},
               opt_in="--lazy-scanner-detector", loader_sha256=LAZY_PIN))


def seal(root):
    control = json.loads(weak.staged.checked(attribution.REFERENCE/"seal.json", attribution.REFERENCE_SEAL))
    profile = json.loads(weak.staged.checked(PROFILE_ROOT/"attributed.json", PROFILE_PIN))
    weak.seal(root)
    published, audit = (weak.read(root/f"{name}.json") for name in ("seal", "imports"))
    attribution.require_parity(published, control)
    if (audit["detector_import"] != {"deferred": True, "original_calls": 0}
            or any(audit["loaded"][name] for name in UNUSED)
            or any(not audit["loaded"][name] for name in (*LIVE, SCANNER, POSITION))
            or set(audit["first_load"]) != {SCANNER, POSITION}
            or published["published"]["solve"]["orbit_policy"] != "stock"):
        raise ValueError("Real legacy receiver isolation or unchanged ordinary solve was not observed")
    old = profile["profile"]["detail"]["import_cpu_ns"]
    weak.write(root/"import-transfer.json", dict(audit=audit, proof=published["regional"], parity=True,
               candidate=published["clock"], candidate_scopes=published["disjoint_saved_costs"],
               uninstrumented_control=control["clock"], profiled_control=profile["through_exit"],
               control_first_load_cpu_ns={name: old[name] for name in (POSITION, SCANNER)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker", "seal"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    if args.action == "launch":
        attribution.launch(args.root, driver=Path(__file__),
                           sources=(PROTOCOL, HERE/"weak_publisher_attribution.py", HERE/"lazy_scanner_detector.py"))
    else:
        {"worker": worker, "seal": seal}[args.action](args.root)
