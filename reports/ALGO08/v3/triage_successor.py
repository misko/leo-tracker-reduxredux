"""Time one DS30-0374 pair against installed ALGO08v3 in the Gauss slot."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

from leo.contracts.digests import canonical_digest
from leo.storage.fast_scan import FastScanStore, immutable_json
from tools.pipeline_eval.qualification import cache_residency, paired_publication


HERE = Path(__file__).resolve().parent
ASSIGNMENT = HERE.parent / "single-core-2x/measurements/DS30-0374-exact-curved-lookahead.json"
ASSIGNMENT_SHA256 = "4e86b8d310d00d263bf39082bd621d102c03188320cbcbdcd099316a8c3410a8"
SMOKE_SHA256 = "5b363d78e8ce37e2425880b347c962018dcf59248e2f3d55b672961572e7fd6e"
CACHE = paired_publication.LOCK.parent / "ds30-cache-residency.so"
CACHE_SHA256 = "4f10e0a2e23121e184ee7d37767f55c29fefc158f4182a2dd99c4268ff2ce6ab"
BASELINE = Path("/opt/leo-algo08/algo08v3/run")
SUCCESSOR = HERE / "run-successor"
NUMERICAL_THREADS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                     "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def read(path):
    return json.loads(path.read_bytes())


def checked(path, digest):
    data = path.read_bytes()
    if sha256(data).hexdigest() != digest:
        raise ValueError(f"Benchmark input pin changed: {path}")
    return data


def publication(root, run):
    receipt = run["receipt"]
    terminal = read(FastScanStore(root).automatic_workspace(receipt["run_id"], create=False) / "terminal.json")
    native_path, = (root / "fast-scan-automatic-work").glob("*/detections.json")
    native = read(native_path)
    source = native["source"]
    if (canonical_digest(native) != terminal["native_sha256"]
            or source["raw_recording_authority_digest"] != run["raw_authority"]
            or source["session_id"] != receipt["session_id"]
            or native["provenance"]["detector_sha256"] != "sha256:" + run["build"]["detector_sha256"]):
        raise ValueError("Native detections do not bind to the terminal and measured build")
    return native, terminal


def witnesses(run, native):
    source = native["source"]
    probes = source["probes"]
    return dict(
        session_id=source["session_id"], raw_authority=run["raw_authority"],
        input_manifest_sha256=source["input_manifest_sha256"],
        analysis_manifest_sha256=source["analysis_manifest_sha256"],
        probe_count=len(probes), probe_sha256=canonical_digest(probes),
        selections=sum(len(row["candidates"]) for row in probes),
        detection_sha256=canonical_digest(native), terminal_sha256=run["receipt"]["terminal_sha256"],
        decision=run["receipt"]["decision"], region=run["receipt"]["region"], arms=run["arms"],
        owners=run["owners"], scientific_digests=run["scientific_digests"],
        pngs={figure["name"]: figure["sha256"] for figure in run["artifacts"]},
    )


def comparison(baseline, successor, native, terminals, smoke):
    """Compare direct documents as well as the digests retained in the receipt."""
    same = {key: value == successor[key] for key, value in baseline.items() if key != "pngs"}
    names = baseline["pngs"].keys() | successor["pngs"].keys()
    same["pngs"] = {name: baseline["pngs"].get(name) == successor["pngs"].get(name) for name in sorted(names)}
    same["ordered_probes"] = native[0]["source"]["probes"] == native[1]["source"]["probes"]
    same["detection_document"] = native[0] == native[1]
    same["terminal_document"] = terminals[0] == terminals[1]
    same["production_witness"] = {
        key: baseline[key] == smoke[key]
        for key in ("session_id", "decision", "raw_authority", "probe_sha256", "owners", "scientific_digests", "pngs")
    } | dict(probes=baseline["probe_count"] == smoke["probes"], positions={
        arm: data["latlon"] for arm, data in baseline["arms"].items()
    } == smoke["positions"])
    return same


def exact(fields):
    return all(exact(value) if isinstance(value, dict) else value is True for value in fields.values())


def measure_pair(output, first):
    assignment = json.loads(checked(ASSIGNMENT, ASSIGNMENT_SHA256))
    smoke = json.loads(checked(HERE / "gauss-smoke.json", SMOKE_SHA256))
    checked(CACHE, CACHE_SHA256)
    archive = Path(assignment["archive"]["root"])
    args = SimpleNamespace(recording=Path(assignment["recording"]), region=Path(assignment["region"]),
                           archive=archive, timeout=240)
    manifests = tuple((Path(row["path"]), row["sha256"]) for row in assignment["cache_observation"]["manifests"])
    region_sha256 = sha256(args.region.read_bytes()).hexdigest()
    if paired_publication.archive_identity(archive) != assignment["archive"]:
        raise ValueError("The causal archive differs from the frozen DS30-0374 assignment")

    output.mkdir()
    os.environ.update({key: "1" for key in NUMERICAL_THREADS})
    os.environ["MPLCONFIGDIR"] = str(output / "mplconfig")
    query = cache_residency.load_query(CACHE)
    page_size = os.sysconf("SC_PAGE_SIZE")
    store = FastScanStore(output)
    launchers = dict(baseline=BASELINE, successor=SUCCESSOR)
    order = [first, "successor" if first == "baseline" else "baseline"]
    result = dict(case="DS30-0374", recording=str(args.recording), archive=assignment["archive"],
                  region_file=str(args.region), region_file_sha256=region_sha256, order=order,
                  assignment_sha256=ASSIGNMENT_SHA256, production_witness_sha256=SMOKE_SHA256,
                  driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                  cpu=sorted(os.sched_getaffinity(0)), nice=os.getpriority(os.PRIO_PROCESS, 0),
                  ionice=subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip(),
                  numerical_threads={key: os.environ[key] for key in NUMERICAL_THREADS},
                  cache=dict(method="linux-cachestat", library_sha256=CACHE_SHA256, page_size_bytes=page_size,
                             managed_cache=False, arms={}), runs={})
    natives, terminals, observed = {}, {}, {}
    try:
        builds = {name: json.loads(subprocess.check_output([str(path), "--verify"], text=True, timeout=30))
                  for name, path in launchers.items()}
        for name in launchers:
            for key in ("frozen_specification", "detector_sha256"):
                if builds[name][key] != smoke[key]:
                    raise ValueError("The measured build differs from the installed ALGO08v3 receiver or spec")

        for name in order:
            def observe_cache():
                result["cache"]["arms"][name] = cache_residency.bound_snapshot(
                    store, args.recording, manifests, page_size, query,
                )

            print(f"Measuring {name} for DS30-0374", flush=True)
            root = output / name
            run = paired_publication.measure(launchers[name], root, args, before_launch=observe_cache)
            result["runs"][name] = run
            run["build"] = builds[name]
            release_marker = "algo08v3-release.json" if name == "baseline" else "algo08v3-successor.json"
            marker = read(root / release_marker)
            expected = builds[name] | {k: run["receipt"][k] for k in ("session_id", "decision")}
            if marker != expected or run["receipt"]["region"] != assignment["runs"]["candidate"]["receipt"]["region"]:
                raise ValueError("Measured build marker or region differs from the intended run")
            natives[name], terminals[name] = publication(root, run)
            observed[name] = witnesses(run, natives[name])
            run["witnesses"] = observed[name]

        if (paired_publication.archive_identity(archive) != assignment["archive"]
                or sha256(args.region.read_bytes()).hexdigest() != region_sha256):
            raise ValueError("Causal archive or region changed during the pair")
        baseline, successor = (result["runs"][name] for name in ("baseline", "successor"))
        result["speedup"] = {key: baseline[key] / successor[key] for key in ("elapsed_s", "cpu_s")}
        names = ("baseline", "successor")
        result["equality"] = comparison(*(observed[name] for name in names),
                                        [natives[name] for name in names], [terminals[name] for name in names], smoke)
        if not exact(result["equality"]):
            raise ValueError("The direct pair or the archived production witness differs")
    except Exception as error:
        result["failure"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        immutable_json(output / "pair.json", result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new directory for the pair and its receipt")
    parser.add_argument("--first", choices=("baseline", "successor"), required=True)
    args = parser.parse_args()
    print(f"Waiting for {paired_publication.LOCK}", flush=True)
    with paired_publication.single_core_slot(2):
        measure_pair(args.output.resolve(), args.first)
    print(args.output / "pair.json", flush=True)


if __name__ == "__main__":
    main()
