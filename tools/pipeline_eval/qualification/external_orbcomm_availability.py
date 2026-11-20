"""Verify exact earlier CelesTrak element bytes against IAU collection history."""

import argparse
import gzip
from datetime import datetime
from hashlib import md5
from pathlib import Path

from ..__main__ import save_json, write
from ..scoring import distance_km
from . import external_orbcomm_trial as trial

API = "https://satchecker.cps.iau.org/tools/get-tle-data/"
JD = (2461125.5, 2461138.5)
DATA = dict(metadata=("metadata.json", 477220), documentation=("publisher-readme.txt", 525332))


def confirmed(rows, orbit, cutoff):
    matching = [
        row
        for row in rows
        if row["data_source"].lower() == "celestrak"
        and int(row["satellite_id"]) == orbit["norad"]
        and [row["tle_line1"], row["tle_line2"]] == orbit["tle"]
    ]
    before = [
        r
        for r in matching
        if trial.ns(datetime.fromisoformat(r["date_collected"].replace(" UTC", "+00:00"))) <= cutoff
    ]
    return dict(exact_records=matching, available_before_cutoff=bool(before))


def independent(source, out):
    trial.check(out, "prediction-lock.json")
    trial.check(out, "input-lock.json")
    historical = trial.read(out / "catalogue-audit.json")["catalogue"]
    authority = trial.read(source / "dataverse.json")["data"]["latestVersion"]
    meta = {}
    for field, (name, number) in DATA.items():
        raw = (source / name).read_bytes()
        published = next(r["dataFile"] for r in authority["files"] if r["dataFile"]["id"] == number)
        if md5(raw).hexdigest() != published["md5"]:
            raise ValueError("station metadata differs from primary deposit")
        meta[field] = dict(file_id=number, provider_md5=published["md5"], sha256=trial.digest(raw))
    survey = trial.read(source / "metadata.json")["location"]
    ids = sorted({r["norad"] for r in historical.values()})
    receipts, archive = {}, {}
    for norad in ids:
        path = source / f"iau-{norad}.json"
        body = path.read_bytes()
        desc = trial.read(path)
        if desc["source"] != "IAU CPS SatChecker" or desc["count"] != len(desc["data"]):
            raise ValueError("independent historical source is incomplete")
        receipts[str(norad)] = dict(
            url=f"{API}?id={norad}&id_type=catalog&start_date_jd={JD[0]}&end_date_jd={JD[1]}",
            sha256=trial.digest(body),
            bytes=len(body),
            records=desc["count"],
        )
        archive[str(norad)] = body.decode()
    result = []
    for study in trial.read(out / "support.json"):
        cutoff = study["cutoff_ns"]
        for tid in study["selected_tle_ids"]:
            r = historical[tid]
            rows = trial.read(source / f"iau-{r['norad']}.json")["data"]
            result.append(
                dict(
                    block=study["block"],
                    author_tle_id=tid,
                    cutoff_ns=cutoff,
                    **r,
                    **confirmed(rows, r, cutoff),
                )
            )
    from ..__main__ import encoded

    write(out / "iau-history-bodies.json.gz", gzip.compress(encoded(archive), mtime=0))
    save_json(
        out / "historical-availability.json",
        dict(
            audit="post-prediction exact short-range historical records, no solver inputs changed",
            author_metadata=meta,
            full_precision_deposit_survey=survey,
            scored_reference_rounding_km=distance_km(survey[:2], trial.SITE),
            independent_sources=receipts,
            rows=result,
            independently_corroborated=sum(r["available_before_cutoff"] for r in result),
            selected_orbits=len(result),
        ),
    )
    names = (
        "historical-availability.json",
        "iau-history-bodies.json.gz",
        "catalogue-audit.json",
        "prediction-lock.json",
        "support.json",
    )
    save_json(
        out / "availability-lock.json",
        dict(
            files={n: trial.digest((out / n).read_bytes()) for n in names},
            source_sha256=trial.digest(Path(__file__).read_bytes()),
        ),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("--out", type=Path, default=trial.REPORT)
    a = p.parse_args()
    independent(a.source, a.out)


if __name__ == "__main__":
    main()
