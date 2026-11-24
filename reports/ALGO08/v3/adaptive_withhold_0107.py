"""Qualify the frozen adaptive 20/8 ms route on the staged DS30-0107 withhold."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from . import adaptive_raw_trial as adaptive
from . import eight_ms_0107_pair as paired

from empty_bootstrap import checked


NORTH = Path("/dev/shm/leo-v3-north-adaptive-raw-result01")
NORTH_BINDING = "95567204662af5ab6105f36c3d9e70b54b20bd32ef1e862cb354c547b72c141c"
NORTH_RESULT = "042eeccded275c307d5b8c96866a61e939a96d7938e2ba66a5b11b02c1224c30"
ORDINARY = ("eight-ms-0107-pair.json.gz", "2cf87dd38df076e00ac1bc555a38cb4bd57e65f5404800897bbfaddb149a6b3e")
PROTOCOL = Path(__file__).with_name("adaptive-withhold-0107-protocol.md")


def frozen_command(previous, recording, archive, offer, target):
    bound = json.loads(checked(NORTH / "binding.json", NORTH_BINDING))
    verified = json.loads(checked(NORTH / "verified-result.json", NORTH_RESULT))
    ordinary = paired.archived(paired.NORTH)["raw_binding"]
    if (previous != bound["original"] or ordinary["libraries"] != bound["libraries"]
            or verified["binding_sha256"] != NORTH_BINDING or not verified["passed"]):
        raise ValueError("Expected the exact accepted North adaptive receiver and recipe")
    for name in (*adaptive.ADAPTER, "combined_raw_research.py", "unified_short_bootstrap.py"):
        checked(paired.HERE / name, bound["sources"][name])
    command = paired.candidate_command(previous, recording, archive, offer, target)
    command = adaptive.adaptive_command(command, target)
    if command != paired.candidate_command(bound["command"], recording, archive, offer, target):
        raise ValueError("DS30-0107 must use the full frozen North adaptive command")
    return command


def launch(root):
    paired.launch(root, candidate_factory=frozen_command,
                  extra_sources=(Path(__file__).name, PROTOCOL.name, *adaptive.ADAPTER))


def web(root, run_id):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from leo.api.fast_standard_analysis import standard_analysis_router
    from leo.contracts.fast_standard_analysis import PLOTS
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    app = FastAPI()
    app.include_router(standard_analysis_router(FastStandardAnalysisStore(root)))
    uri = f"/api/v2/fast-scans/{run_id}/standard-analysis"
    with TestClient(app) as client:
        details = client.get(uri)
        products = {name: client.get(f"{uri}/{name}").status_code
                    for name in ("position-grid.json", "position-path.json", *(f"{plot}.png" for plot in PLOTS))}
    return dict(status=details.status_code, detail=details.json(), products=products)


def standard_withhold(web_result, row):
    details = web_result["detail"]
    science = row["science"]
    return (web_result["status"] == 200 and len(web_result["products"]) == 10
            and all(value == 404 for value in web_result["products"].values())
            and details.get("state") == "withheld" and details.get("reason") == science["reason"]
            and details.get("arms") == {} and details.get("artifacts") == []
            and details.get("input_sha256") == row["native_sha256"]
            and details.get("raw_authority") == science["raw_authority"]
            and all(details.get(name) == science["receipt"][name]
                    for name in ("region", "session_id", "run_id", "terminal_sha256")))


def score(root, output):
    from aperture_trial import RELEASE, read, write
    from leo.api import fast_standard_analysis as api
    from leo.storage import fast_standard_analysis as store
    from local_future_cli_trial import native_packet
    from reports.ALGO08.v3.live_adaptive_grid_entry import NAMESPACE

    # Audit the released web implementation in-process after both timed children exit.
    for kind, module in (("api", api), ("storage", store)):
        checked(Path(module.__file__), paired.digest(RELEASE / "src/leo" / kind / "fast_standard_analysis.py"))
    expected = paired.archived(ORDINARY)["documents"]["post-verification.json"]
    with TemporaryDirectory(dir="/dev/shm") as work:
        temporary = Path(work) / "pair.json"
        paired.verify(root, temporary)
        paired_result = read(temporary)
    binding = read(root / "binding.json")
    modes = paired_result["modes"]
    web_rows, packets, checks = {}, {}, {}
    for name, row in modes.items():
        target = root / name
        web_rows[name] = web(target, row["science"]["receipt"]["run_id"])
        packets[name] = read(native_packet(target))
        checks[name] = dict(
            ordinary_withhold=paired_result["expected_withholds"][name],
            native_packet=row["native_sha256"] == expected["modes"][name]["native_sha256"],
            terminal=row["science"]["receipt"]["terminal_sha256"]
                     == expected["modes"][name]["science"]["receipt"]["terminal_sha256"],
            standard_routes=standard_withhold(web_rows[name], row),
            no_png_or_position_files=not any(path.suffix == ".png" or path.name in ("position-grid.json", "position-path.json")
                                             for path in target.rglob("*") if path.is_file()),
            no_research_publication=not (target / NAMESPACE).exists(),
        )
    if "candidate" in modes:
        candidate = modes["candidate"]["bootstrap"]
        ordinary = expected["modes"]["candidate"]["bootstrap"]
        checks["candidate"].update(
            adaptive_requested_but_no_fit=candidate.get("research_adaptive_position_map") ==
                dict(namespace=NAMESPACE, published=False) and adaptive.FLAG in binding["commands"]["candidate"],
            original_graph_proof=candidate["graph_proof"] == ordinary["graph_proof"],
            original_selector=adaptive.selection_identity(candidate["held_anchor_route"])
                              == adaptive.selection_identity(ordinary["held_anchor_route"]),
            original_two_scan_schedule=all(candidate["receiver_audit"]["native"][key]
                                           == ordinary["receiver_audit"]["native"][key]
                                           for key in ("native_calls", "factors", "rule", "streams", "installed_sha256",
                                                       "short_primary_sha256")),
            no_solver_imports=not candidate["scientific_imports_after"],
        )
    clocks = paired_result["clocks"]
    same = paired_result["same_opportunities"] and set(modes) == set(paired.ORDER)
    ratio = clocks["stock"]["clock"]["elapsed_s"] / clocks["candidate"]["clock"]["elapsed_s"] if same else None
    write(output, dict(passed=same and all(all(values.values()) for values in checks.values()),
                       checks=checks, web=web_rows, native=packets, pair=paired_result, binding=binding,
                       north=dict(binding_sha256=NORTH_BINDING, result_sha256=NORTH_RESULT), earlier=ORDINARY[1],
                       wall_ratio=ratio))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("launch", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mode == "launch":
        launch(args.root)
    elif args.output is not None and not args.output.resolve().is_relative_to(args.root.resolve()):
        score(args.root, args.output)
    else:
        parser.error("provide a fresh --output outside the frozen pair root")
