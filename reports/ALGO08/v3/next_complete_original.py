"""Choose one small signed original without consulting scientific outcomes."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
DATASET = REPORTS/"2026_11_20_ds30_fast/dataset/manifest.json.gz"
INPUTS = REPORTS/"2026_11_21_ds30_full/input-audit.json"
RELEASE = HERE/"measurements/release-intake-rate.json"
DATASET_SHA = "346331168df1bd9344d02285ff4892cfd567aef329dc8bdda254fdecede2de74"
INPUTS_SHA = "87e6c389cc4dccafb204ada3def360343514d283d65418ee3211817d9a57b5c5"
RELEASE_SHA = "97889f708715be74e1036e2c9e5f30a38800658bfe9ecff2be4aacbdb2b13aed"
TRIED = frozenset(f"DS30-{suffix}" for suffix in ("0008", "0016", "0057", "0102", "0107", "0180", "0227", "0306", "0340", "0402"))
MIN_VISITS = 512
MAX_BYTES = 1200*2*1024**2


def checked(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin:
        raise ValueError(f"Unverified enrollment metadata: {path}")
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def choose(dataset, bindings, release):
    rows = []
    for member in dataset["members"]:
        case = member["dataset_label"]
        raw = member["raw_recording"]
        if (case in TRIED or member["sample_rate_hz"] != 10_000_000 or member["window_count"] < MIN_VISITS
                or case not in bindings or raw["integrity_errors"] or not raw["chunks"]
                or sum(chunk["window_count"] for chunk in raw["chunks"]) != member["window_count"]):
            continue
        size = sum(chunk["compressed_bytes"] for chunk in raw["chunks"])
        if any(chunk["observed_payload_bytes"] != chunk["compressed_bytes"] for chunk in raw["chunks"]):
            raise ValueError("Compressed source size was never settled in the original metadata")
        index = sum(chunk["index_bytes"] for chunk in raw["chunks"])
        rows.append(dict(case=case, original=raw["root"], encoded_bytes=size, index_bytes=index,
                         visits=member["window_count"], admitted=bindings[case]["usable_visits"],
                         capture_state=member["recording_state"], segments=len(raw["segments"]), members=len(raw["chunks"]),
                         release=case in release, binding_sha256=bindings[case]["binding_sha256"]))
    ordered = sorted(rows, key=lambda row: (row["encoded_bytes"], row["case"]))
    fitting = [row for row in ordered if row["encoded_bytes"]+row["index_bytes"] < MAX_BYTES]
    return dict(selected=min(fitting, key=lambda row: (not row["release"], row["encoded_bytes"], row["case"]), default=None),
                metadata_eligible=len(ordered), plausible_by_size=fitting, size_excluded=len(ordered)-len(fitting),
                smallest_release=[row for row in ordered if row["release"]][:4],
                smallest_original_rows=ordered[:8], cap_bytes=MAX_BYTES,
                source_pins=dict(dataset=DATASET_SHA, input_audit=INPUTS_SHA, release_roster=RELEASE_SHA))


def enrollment():
    return choose(checked(DATASET, DATASET_SHA), checked(INPUTS, INPUTS_SHA)["bindings"],
                  {row["case"] for row in checked(RELEASE, RELEASE_SHA)["rows"]})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    with parser.parse_args().output.open("x") as out:
        json.dump(enrollment(), out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")
