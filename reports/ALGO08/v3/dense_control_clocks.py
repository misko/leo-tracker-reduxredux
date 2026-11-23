"""Bind two historical full-recording v3 clocks to the same dense scientific result."""

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ARCHIVE = Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac")


def identity(qualification, named):
    warm = qualification["runs"]["candidate"]
    control = named["runs"]["baseline"]
    if (qualification["candidate_specification_digest"] != control["build"]["frozen_specification"]
            or control["build"]["version"] != "ALGO08v3"
            or qualification["archive"] != named["archive"] or qualification["recording"] != named["recording"]):
        raise ValueError("The v3 build, recording or archive differs")
    fields = ("raw_authority", "arms", "owners", "artifacts", "scientific_digests")
    receipt_fields = ("region", "session_id", "terminal_sha256", "decision", "window_count", "counts")
    if (warm["receipt"]["decision"] != "complete" or len(warm["artifacts"]) != 8
            or any(warm[k] != control[k] for k in fields)
            or any(warm["receipt"][k] != control["receipt"][k] for k in receipt_fields)):
        raise ValueError("Historical controls disagree on the scientific publication")
    return {k: warm["receipt"][k] for k in receipt_fields} | dict(spec=control["build"]["frozen_specification"],
            raw_authority=control["raw_authority"], science=control["scientific_digests"], archive=named["archive"])


def collect():
    paths = (ARCHIVE / "publications/DS30-0008/pair.json", ARCHIVE / "v3-bounds-DS30-0008-pair/pair.json")
    documents = [p.read_bytes() for p in paths]
    qualification, named = [json.loads(b) for b in documents]
    common = identity(qualification, named)
    with (HERE / "first-55/stage-clocks.csv").open() as stream:
        row, = [r for r in csv.DictReader(stream) if r["recording"] == "DS30-0008"]
    earlier = [float(row[k]) for k in ("launch_to_detections_s","detections_to_terminal_s","terminal_to_exit_s")]
    later = named["runs"]["baseline"]
    # The paired driver timestamps detections and terminal relative to process launch.
    stages = [earlier, [later[k] for k in ("detection_file_s","detection_to_terminal_s","terminal_to_exit_s")]]
    controls = {}
    for (case, source, arm, cache), costs, evidence in zip((
        ("qualification", qualification, "candidate", "cache_observation"),
        ("named_launcher", named, "baseline", "cache"),
    ), stages, documents, strict=True):
        run = source["runs"][arm]
        resident = source[cache]["arms"][arm]
        if abs(sum(costs) - run["elapsed_s"]) > 1e-5 or resident["members"] != resident["observed_members"]:
            raise ValueError("Incomplete recording stage clocks or cache census")
        controls[case] = dict(elapsed_s=run["elapsed_s"], cpu_s=run["cpu_s"], half_elapsed_s=run["elapsed_s"]/2,
                              stage_elapsed_s=costs, resident_fraction=resident["cached_pages"]/resident["observed_file_pages"],
                              input_blocks=run["input_blocks"], launcher=run["launcher"], receipt_sha256=sha256(evidence).hexdigest())
    return dict(common=common, controls=controls)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    output = collect()
    with args.output.open("x") as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
        stream.write("\n")
