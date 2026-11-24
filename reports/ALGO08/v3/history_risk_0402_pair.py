"""Run the original installed 0402 command and the frozen router on the same saved input."""

import argparse
from pathlib import Path
import sys
from time import perf_counter_ns, process_time_ns


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

import history_risk_route_trial as route


SOURCE = Path("/dev/shm/leo-v3-rank1-0402/reports/ALGO08/v3")
ARCHIVED_ADMISSION_SHA256 = "fed3760d61bb9cb1d4ee2eb98ee5e36490db6d706451a1eda99220f287be9453"
ARCHIVED_CLOCK_SHA256 = "47f78189857d8d8a0a03a26cd2ef824fa467514d921fd967328fb22223d0ff63"
SOURCES = {
    "prospective_0402_solver.py": "c8cfb7abc492f32a29c33c9a39d3419e110d4e7679c88bf4628344e98287072d",
    "prospective_0155_solver.py": "c6eaaababd835411c79a8ea78936f3255fec29ff576ee86881a30a91d0b1fc31",
    "prospective_0316_solver.py": "73e3fb562115933bd5f6fb28d7a3e281c11c8f11c834a45d4b1c0914c33a280c",
}


def previous_stock_command(stage, release):
    original = route.pinned(stage/"stock-clock.json", ARCHIVED_CLOCK_SHA256)
    admitted = route.pinned(stage/"admission.json", ARCHIVED_ADMISSION_SHA256)
    sources = admitted["source_sha256"] | SOURCES
    for name, pin in sources.items():
        if route.exact.digest(route.exact.resident_path(SOURCE/name)) != pin:
            raise ValueError(f"Original installed saved adapter source changed: {name}")
    expected = [release/"venv/bin/python", "-IB", SOURCE/"prospective_0402_solver.py",
                "worker", stage/"request.json", "stock", stage/"stock"]
    if [str(x) for x in expected] != original["command"] or original["timing"]["exit_code"] != 0:
        raise ValueError("The exact archived installed saved command is unavailable")
    return original["command"][:-1], sources


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from exact_named_0402 import STAGE

    if route.exact.resident_path(root.parent) != Path("/dev/shm") or root.exists():
        raise ValueError("Use a fresh tmpfs pair root")
    started = process_time_ns(), perf_counter_ns()
    command, sources = previous_stock_command(STAGE, RELEASE)
    host()
    baseline_verification = dict(cpu_ns=process_time_ns()-started[0], elapsed_ns=perf_counter_ns()-started[1])
    paths = {name: root.with_name(root.name+"-"+name) for name in ("named", "routed")}
    if any(path.exists() for path in paths.values()):
        raise ValueError("The pair needs two unused worker roots")
    root.mkdir(mode=0o700)
    write(root/"pair-binding.json", dict(source_sha256=sources, archived_command=command,
          launch_order=list(paths), outputs={key: str(path) for key, path in paths.items()},
          baseline_only_source_validation=baseline_verification, driver_sha256=route.exact.digest(Path(__file__)),
          protocol_sha256=route.exact.digest(HERE/"history-risk-0402-pair-protocol.md")))
    for name, path in paths.items():
        route.launch("0402", path, stock_command=command if name == "named" else None)
        if route.exact.read(path/"clock.json")["exit_code"]:
            raise ValueError(f"{name} did not exit successfully; see the sealed worker clock")


def score(root):
    from aperture_trial import write
    from exact_named_route_score import parity
    from held_adaptive_0160_score import verified
    from prospective_0316_solver import owner_delta

    bind = route.exact.read(root/"pair-binding.json")
    names = bind["launch_order"]
    paths = {key: Path(path) for key, path in bind["outputs"].items()}
    inputs = [route.exact.read(paths[name]/"binding.json")["input"] for name in names]
    if len(inputs) != 2 or inputs[0] != inputs[1]:
        raise ValueError("The two fresh processes did not use identical validated inputs")
    req = route.exact.read(Path(inputs[0]["request"]))
    outputs = {}
    for name, filename in zip(names, ("saved-0402-worker.json", "worker.json"), strict=True):
        path = paths[name]
        clock = route.exact.read(path/"clock.json")
        preflight = route.exact.read(path/"route-binding.json")["preflight"]
        if name == "named":
            preflight = {key: preflight[key]+bind["baseline_only_source_validation"][key] for key in preflight}
        products = verified(path/"candidate", clock, filename, req)
        outputs[name] = dict(products, preflight_ns=preflight)
    checked = outputs["named"]
    archived_root, archived_pin = route.EXACT["0402"]
    archived = route.pinned(archived_root/"result.json", archived_pin)
    original = verified(archived_root/"candidate", archived["clocks"]["candidate"], "worker.json", req)
    if not all(parity(original, checked).values()):
        raise ValueError("The rerun changed archived installed science or media")
    route.score("0402", paths["routed"])
    flag = route.exact.read(paths["routed"]/"result.json")
    candidate = outputs["routed"]
    def charge(result, key, unit):
        return result["clock"][key] + result["preflight_ns"][unit]/1e9

    ratios = {key: dict(child=checked["clock"][key]/candidate["clock"][key],
                        admission_charged=charge(checked, key, unit)/charge(candidate, key, unit))
              for key, unit in (("cpu_s", "cpu_ns"), ("elapsed_s", "elapsed_ns"))}
    owners = {arm: owner_delta(checked["rows"][arm], candidate["rows"][arm]) for arm in ("c0", "fitted_c")}
    write(root/"result.json", dict(binding=bind, binding_sha256=route.exact.digest(root/"pair-binding.json"),
          routed=flag, archived_installed_parity=parity(original, checked), fresh_parity=parity(checked, candidate),
          owners=owners, speedup=ratios,
          arms={name: {k: row[k] for k in ("clock", "preflight_ns", "products", "science", "terminal", "worker")}
                for name, row in outputs.items()}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "score"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    {"launch": launch, "score": score}[args.action](args.output)
