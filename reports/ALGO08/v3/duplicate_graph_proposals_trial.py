"""Test duplicate-only Graph arbitration on the frozen South and held inputs."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
HELD = {
    "weak": (Path("/dev/shm/leo-cumulative-grid-projection-01/weak-pair/detections.json"),
             "c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589"),
    "north": (Path("/dev/shm/leo-v3-combined-raw-north-result01/containing/fast-scan-automatic-work/algo08-v2-113262a9d6ff6ba8b303ad51dfdf6acf/detections.json"),
              "5f2cc8c112d18a25911f9e47de1d5064ee36ffd0b2b1ac686c5ef6a1d4c1dcaa"),
}
WITNESS_PIN = "1d2d1cd72ea348d53646fdea6045c25d000f6f1f63362f3ee6e0df7bf1828199"


def run(witness, output):
    import empty_bootstrap as staged
    from aperture_trial import write
    from dense_geographic_trial import host
    from duplicate_graph_proposals import stable_finalization
    from short_graph_guard import TRACK_CONFIG
    from south_graph_sensitivity import PINS, graph_run

    machine = host()
    _, spec, _, publication, _ = staged.load_runtime()
    from leo.analysis.localization_v3.tracks import winning_observations
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.contracts.digests import canonical_digest

    expected = json.loads(staged.checked(witness, WITNESS_PIN))
    config = TrackConfig(**json.loads(staged.checked(staged.RELEASE / "assets/tracks.json", TRACK_CONFIG))["config"])
    library = Path(spec["graph_path"]["library"])
    publication._checked_graph_path(spec)
    inputs = dict(HELD)
    for mode, (root, pin, _) in PINS.items():
        (packet,) = (root / "fast-scan-automatic-work").glob("*/detections.json")
        inputs[mode] = packet, pin
    results = {}
    for mode, (packet, pin) in inputs.items():
        native = json.loads(staged.checked(packet, pin))
        rows, _ = winning_observations(native)
        baseline = graph_run(rows, config, library)
        counts = Counter()
        with stable_finalization(counts):
            alternate = graph_run(rows, config, library)
        report = dict(winning_rows=len(rows), duplicate_filter=dict(counts), native_sha256=pin)
        for variant, item in (("original", baseline), ("duplicate_filtered", alternate)):
            report[variant] = {key: item[key] for key in ("points", "tracks", "complete_graph_sha256")}
            report[variant]["support_sha256"] = canonical_digest(item["support"])
        if mode in HELD:
            report["held_exact"] = report["original"] == report["duplicate_filtered"]
        else:
            report["original_reproduces_cross"] = report["original"]["support_sha256"] == expected["cells"][mode]["support_digest"]
            report["duplicate_filtered_recovers_original_support"] = report["duplicate_filtered"]["support_sha256"] == expected["cells"]["old"]["support_digest"]
        results[mode] = report
    write(output, dict(results=results, machine=machine, graph_path=spec["graph_path"], waveform_reads=0, solver_calls=0,
                       witness_sha256=WITNESS_PIN, sources={name: sha256((HERE / name).read_bytes()).hexdigest()
                           for name in ("duplicate-graph-proposals-protocol.md", "duplicate_graph_proposals.py",
                                        "duplicate_graph_proposals_trial.py", "south_graph_sensitivity.py")}))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("witness", type=Path)
    cli.add_argument("output", type=Path)
    run(**vars(cli.parse_args()))
