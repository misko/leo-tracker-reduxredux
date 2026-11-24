"""Observe the exact first required file of the bounded alternative shortlist."""

import argparse
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]


def run(output):
    from next_complete_original import DATASET, DATASET_SHA, checked, enrollment
    from next_complete_original_stage import cache_sample, emit, row, scoped_rows

    study = enrollment()
    names = {e["case"] for e in study["plausible_by_size"]}
    if study["smallest_release"]:
        names.add(study["smallest_release"][0]["case"])
    results = []
    for member in checked(DATASET, DATASET_SHA)["members"]:
        case = member["dataset_label"]
        if case not in names:
            continue
        raw = member["raw_recording"]
        original = Path(raw["root"])
        entry = raw["chunks"][0]
        path = Path(entry["payload_path"])
        if path.parent != Path(raw["segments"][0]["path"]).parent or entry["first_sequence"] != 0:
            raise ValueError("The first required source does not match the original chronology")
        first = cache_sample([row(path, entry["compressed_sha256"], "payload", entry["compressed_bytes"])])
        roots = (Path("/tmp"), Path("/dev/shm"), Path("/srv/postgres-nvme/fast-scan-recordings"))
        named_aliases = {str(r/original.name): str((r/original.name).resolve(strict=True)) for r in roots if (r/original.name).exists()}
        result = dict(case=case, first=first, first_path=str(path), first_bytes=entry["compressed_bytes"], aliases=named_aliases)
        if first["cached_pages"] == first["observed_file_pages"]:
            _, files = scoped_rows(member)
            result["whole"] = cache_sample(files)
        results.append(result)
    emit(output, dict(members=sorted(results, key=lambda r: r["case"]), original_bodies_read=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
