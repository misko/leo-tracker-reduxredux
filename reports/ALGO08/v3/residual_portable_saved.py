"""Run one authenticated saved history-risk publication with conservative rendering."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

from history_risk_residual_layout_0402 import ORBIT_SHEETS, SCENE, render_pair, require_active, source_digest, worker


BASES = {"0169": (Path("/dev/shm/leo-v3-history-risk-0169-01"), {
    "binding.json": "94dea3f943c40c9a924cc760024fb2ca81b7634c4ec8ad935af6e21593bd08f4",
    "route-binding.json": "7c27efffd191045e4e6563f3b0733bae228bfccf7a620e34da2a17cbbe6c4ba0",
    "clock.json": "ead5c7644d3181f283ff2b9676868841bce1f7a91b822cdaeab9b543a5ca3825",
    "result.json": "ceac57a6be8d37df09c7ddab72ff326f4dd3f6fdc5ff00878d560674c453851b",
    "candidate/ports.json": "00adc5fdc09a60e0bebcc18cc0676b83cf5ddef43c51562e1e9c46c03ae272d2",
    "candidate/worker.json": "718e96b5d3d584941c83643138a88eac77e37ea6a1b8cdd7de8d54475a226de6",
    "candidate/joint-research-receipt.json": "2975d3ffd8f057d131795201339255378a01ede4fb21db8bf77306fbfa0a07b4",
})}
PRODUCER_CLOCK_PIN = "ea78ecc07d20b61b5f3473d08f849efe178df093c53c095fa9a7a0d6152993f2"


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def source_pins(case):
    from exact_named_route import SOURCES
    from history_cairo_render import RESIDUAL_SOURCES
    from history_risk_route_trial import sources

    names = ("history_risk_residual_layout_0402.py", "residual-portable-saved-0169-protocol.md", Path(__file__).name)
    return (sources(case) | {path.name: digest(path) for path in SOURCES}
            | {name: digest(HERE/name) for name in (*names, *RESIDUAL_SOURCES)})


def controls(case):
    from history_risk_route_trial import pinned

    root, inventory = BASES[case]
    data = {name: pinned(root/name, pin) for name, pin in inventory.items()}
    prior = data["result.json"]
    if (prior["case"] != "DS30-"+case or prior["clock"] != data["clock.json"] or prior["clock"]["exit_code"]
            or not all(prior["named_parity"].values()) or not prior["named_parity"]
            or data["candidate/worker.json"]["receipt"]["decision"] != "complete"):
        raise ValueError("The complete routed ordinary-renderer historical control must be verified")
    return root, data


def launch(case, root):
    from aperture_trial import write
    from combined_raw_trial import PRODUCER, checked_producer
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE, clock, now
    from history_risk_route_trial import launch as original, pinned
    from portable_orbit_index_trial import local_launcher_tools
    from visit_frame_raw_0016 import resident

    started = now()
    _, previous = controls(case)
    bound = previous["binding.json"]["input"]
    cutoff = previous["route-binding.json"]["cutoff_utc_ns"]
    if host() != previous["binding.json"]["machine"] or bound["portable"] != [str(PRODUCER.file), PRODUCER.sha256, PRODUCER.producer_sha256]:
        raise ValueError("The current host and intended index must match the same prior routed control")
    pins = source_pins(case)
    source = PRODUCER.file.parent/"artifact-bind.json"
    previous_build = pinned(PRODUCER.file.parent/"dense-export-clock.json", PRODUCER_CLOCK_PIN)
    proven = checked_producer(cutoff)
    cached = resident([PRODUCER.file, source])
    prior_transfer, = previous["candidate/ports.json"]["portable"]["transfers"]
    if (previous_build["exit_code"] or not prior_transfer["counts"]["sidecar_hit_bodies"]
            or prior_transfer["producer_cutoff_utc_ns"] != proven["producer_cutoff_utc_ns"]):
        raise ValueError("Earlier producer cutoff and genuine prior reuse must match")
    local_launcher_tools()
    preflight = clock(started)
    admission = root.with_name(root.name+"-preflight.json")
    write(admission, dict(case=case, pins=pins, control_pins=BASES[case][1], producer=proven, producer_clock=previous_build,
                          index_cache=cached, scope=bound, checks=preflight, no_waveform=True, one_worker=True))
    original(case, root, stock_command=[RELEASE/"venv/bin/python", "-IB", __file__, "worker", case,
                                        "--expected", source_digest(pins)])
    write(root/"outer-admission.json", read(admission))
    write(root/"prediction-seal.json", seal(root))


def seal(root):
    return {str(p.relative_to(root)): digest(p) for p in root.rglob("*") if p.is_file()
            and p.relative_to(root).parts[0] not in ("fonts", "tmp")
            and p.name not in ("prediction-seal.json", "replay.json", "result.json")}


def replay(case, root):
    from aperture_trial import write

    report = read(root/"render.json")
    if read(root/"prediction-seal.json") != seal(root) or report["sources"] != source_pins(case):
        raise ValueError("Renderer replay requires the sealed publication and pinned render source")
    write(root/"replay.json", render_pair(root/SCENE, report["scene_sha256"]))


def committed_orbits(historical, active, replayed):
    old, new = [{name: row["sha256"] for name, row in images.items()} for images in (historical, active)]
    if replayed["ordinary"] != old or replayed["residual_layout"] != new:
        raise ValueError("The complete rendered scene must match both official eight-PNG sets")
    if any(old[name] != new[name] for name in ORBIT_SHEETS):
        raise ValueError("All four original orbit sheets must remain byte-identical")
    return {name: old[name] == new[name] for name in old}


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker", "replay"))
    parser.add_argument("case", choices=BASES)
    parser.add_argument("root", type=Path)
    parser.add_argument("--expected")
    options = parser.parse_args()
    if options.action == "worker":
        worker(options.root, options.expected, case=options.case, pins=lambda: source_pins(options.case))
    else:
        {"launch": launch, "replay": replay}[options.action](options.case, options.root)
