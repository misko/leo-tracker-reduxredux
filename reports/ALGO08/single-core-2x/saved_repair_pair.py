"""Compare a frozen repaired solver to the incumbent on one completed pair's detections."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from leo.contracts.algo08_region import Algo08Region
from leo.contracts.digests import canonical_digest
from residual_attribution_trial import ARMS, RELEASE, controls_match, read, saved_native, write
from tools.pipeline_eval.qualification.paired_publication import archive_identity, verify_sources


def normalized(spec):
    direct = {k: v for k, v in spec.items() if k not in {"sources", "solver", "detector"}}
    return {k: v["sha256"] if isinstance(v, dict) and "library" in v else v for k, v in direct.items()}


def freeze_variant(checkout, baseline, output):
    from tools.pipeline_eval.qualification.freeze_publication import freeze
    spec = read(baseline/"spec.json")
    options = {k: v for k, v in spec.items() if k not in ("sources", "solver", "detector", "detector_sha256", "ingress")}
    for name in ("png_filter", "png_deflate", "tle_parser", "paired_sha256"):
        if name in options:
            options[name] = Path(options[name]["library"]), options[name]["sha256"]
    return freeze(checkout, output, Path(spec["detector"]), spec["detector_sha256"],
                  "collapsed-repair", spec["ingress"], **options)


def compare(pair_path, request, control, candidate, out):
    pair = read(pair_path)
    original = pair["runs"]["candidate"]
    offer = Algo08Region.parse(read(Path(pair["region"]))).document()
    archive = request.parent/"tle"
    if (original["receipt"]["region"] != offer or pair["archive"] != archive_identity(archive)
            or canonical_digest(read(request)["causal_snapshots"]) != pair["archive"]["snapshots_sha256"]):
        raise ValueError("Regional frame or causal archive differs from the recorded assignment")
    specs = [read(folder/"spec.json") for folder in (control, candidate)]
    if (specs[0] != pair["candidate_specification"] or canonical_digest(specs[0]) != pair["candidate_specification_digest"]
            or [s["solver"] for s in specs] != ["shared-tables", "collapsed-repair"]
            or normalized(specs[0]) != normalized(specs[1])):
        raise ValueError("Expected the original solver and a matched one-option challenger")
    for folder, spec in zip((control, candidate), specs, strict=True):
        verify_sources(folder/"reports/ALGO08/single-core-2x/run-candidate", spec["sources"])
    native = saved_native(pair_path, "candidate", original)
    out.mkdir(exist_ok=False)
    write(out/"plan.json", dict(case=pair_path.parent.name, order=["repair", "control"], offer=offer,
          raw_authority=original["raw_authority"], native_sha256=canonical_digest(native), archive=pair["archive"],
          pair_sha256=sha256(pair_path.read_bytes()).hexdigest(), specifications=list(map(canonical_digest, specs))))
    env = {k: v for k, v in os.environ.items() if not k.startswith("ALGO08_")}
    with TemporaryDirectory() as scratch:
        saved, region = Path(scratch)/"native.json", Path(scratch)/"offer.json"
        write(saved, native)
        write(region, offer)
        for name, folder in (("repair", candidate), ("control", control)):
            env.update(PYTHONPATH=f"{folder}:{RELEASE/'src'}:{RELEASE}", OMP_NUM_THREADS="1",
                       OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
            subprocess.run([str(RELEASE/"venv/bin/python"), "-BPs", str(Path(__file__).with_name("residual_attribution_trial.py")),
                            "worker", str(saved), str(folder/"spec.json"), str(archive), str(region),
                            str(out/(name+".json")), "--evidence"], env=env, check=True, timeout=240)
    results = {k: read(out/(k+".json")) for k in ("control", "repair")}
    if not controls_match(results["control"], original) or results["control"]["owners"] != original["owners"]:
        raise ValueError("Saved control did not reproduce both published positions and owners")
    if archive_identity(archive) != pair["archive"]:
        raise ValueError("Archive changed during comparison")
    summary = {}
    for name, result in results.items():
        evidence = result.pop("evidence", {})
        digests = {}
        if result["status"] == "ok":
            for key in ("grid", "path"):
                obj = evidence["position_"+key]
                if obj["region_center"] != offer["center"] or obj["box_width_km"] != offer["width_km"]:
                    raise ValueError("Output geometry differs from the assigned offer")
                digests[key] = canonical_digest({k: v for k, v in obj.items() if k not in ("binding", "elapsed_seconds")})
        if name == "control" and digests != original["scientific_digests"]:
            raise ValueError("Control grid or path differs from the verified publication")
        summary[name] = dict(result, scientific_digests=digests,
                             evaluated_points=evidence.get("position_grid", {}).get("evaluated_points"))
    write(out/"locked.json", dict(plan=read(out/"plan.json"), runs=summary))


def score(lock_path, reference_path):
    from residual_attribution_trial import REFERENCE_SHA256
    from tools.pipeline_eval.scoring import distance_km
    locked = read(lock_path)
    if sha256(reference_path.read_bytes()).hexdigest() != REFERENCE_SHA256:
        raise ValueError("Unexpected scoring reference")
    name = locked["plan"]["case"]
    truth, = [c["reference"] for c in read(reference_path)["cases"] if c["authority_eligible"] and c["dataset_label"] == name]
    point = truth["latitude_deg"], truth["longitude_deg"]
    return dict(locked, errors_km={k: {a: distance_km(r["arms"][a]["latlon"], point) for a in ARMS}
                                  for k, r in locked["runs"].items()}, reference_sha256=REFERENCE_SHA256)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    routes = dict(freeze=(freeze_variant, ("checkout", "baseline", "output")),
                  run=(compare, ("pair", "request", "control", "candidate", "out")),
                  score=(score, ("lock", "reference")))
    for action, (_, fields) in routes.items():
        cmd = actions.add_parser(action)
        for field in fields:
            cmd.add_argument(field, type=Path)
    args = parser.parse_args()
    operation, fields = routes[args.action]
    result = operation(*(getattr(args, key) for key in fields))
    if result is not None:
        print(json.dumps(result, indent=2, allow_nan=False))
