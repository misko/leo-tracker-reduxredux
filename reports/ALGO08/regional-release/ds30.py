"""Authenticate every frozen DS30 result and replay a named recording from its native factors."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from tools.algo08_position import solve

ROOT = Path(__file__).resolve().parents[3]
DATA = Path("/srv/bulk/leo-dev/ds30-full-20261121")
ASSETS = Path(os.environ.get("ALGO08_ASSETS", "/opt/leo-algo08/current/assets"))


def read(path, digest=None):
    data = path.read_bytes()
    if digest and hashlib.sha256(data).hexdigest() != digest.removeprefix("sha256:"):
        raise ValueError(f"Digest mismatch at {path}")
    return json.loads(data)


def run(case):
    offer = Algo08Region.parse(read(ROOT / "deploy/gauss/algo08-region.json"))
    rows = read(ROOT / "reports/2026_11_21_ds30_full/prediction-lock.json")["predictions"]
    counts = {}
    for row in rows:
        if row["method"] != "compact_two_scan" or case and case != row["case"]:
            continue
        name = row["case"]
        folder = DATA / "runs" / name / "compact_two_scan"
        outcome = read(folder / "outcome.json", row["outcome_sha256"])
        old = read(Path(outcome["prediction_path"]), row["prediction_sha256"])
        case_doc = read(DATA / "bindings" / (name + ".json"), row["input_binding_sha256"])
        region, = case_doc["case"]["regions"]
        if region["center"] != list(offer.center) or region.get("width_km", 25.) != offer.width_km:
            raise ValueError(f"Search region differs at {name}")
        # Captures with no probes had an explicit no-measurement decision before orbit preparation.
        binding_path = Path(outcome["prediction_path"]).with_name("binding.json")
        if binding_path.exists():
            job = read(binding_path, outcome["binding_sha256"])["job"]
            if job["search_center"] != list(offer.center) or job["screen_center"] != list(offer.screen_center):
                raise ValueError(f"Scientific inputs differ at {name}")
        counts[old["status"]] = counts.get(old["status"], 0) + 1
        if case:
            acq = read(folder / "acquisition.json")
            native = read(Path(acq["native_path"]), acq["native_sha256"])
            archive = TleArchiveReader(DATA / "snapshot/inputs" / name / "tle")
            try:
                new, packet, policy = solve(native, archive, ASSETS, offer)
            except (ValueError, AssertionError) as exc:
                if old["status"] != "unavailable" or f"{type(exc).__name__}: {exc}" != old["reason"]:
                    raise
                return dict(case=case, status="unavailable", reason=old["reason"], arms=old["arms"],
                            evidence_checked=False)
            if (new["status"], new["arms"]) != (old["status"], old["arms"]):
                raise ValueError(f"{name} scientific outputs differ: {new['arms']} versus {old['arms']}")
            if packet and any(packet[k]["region_center"] != list(offer.center)
                              or packet[k]["box_width_km"] != offer.width_km
                              for k in ("position_grid", "position_path")):
                raise ValueError("Evidence outside the declared frame")
            return dict(case=case, status=new["status"], arms=new["arms"], orbit_policy=policy,
                        evidence_checked=packet is not None)
    if case or sum(counts.values()) != 455:
        raise ValueError("Incomplete cohort")
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", nargs="?")
    print(json.dumps(run(parser.parse_args().case)))
