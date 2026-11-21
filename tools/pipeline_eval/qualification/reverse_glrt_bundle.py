"""Package the scored tables and original signed stereo samples for offline receiver comparison."""

import argparse
import json
import zipfile
from pathlib import Path

from .full_v5_check import _load_case, _sha
from .original_kernel_trial import decode
from .reverse_glrt_reference import REPORT, digest, packed
from .reverse_glrt_report import read
from .reverse_glrt_search import WORK, key

PANELS = ("", "heldout", "replication", "quarter-holdout", "recovery")


def add(archive, name, body, level):
    info = zipfile.ZipInfo(name, date_time=(2026, 11, 20, 0, 0, 0))
    info.external_attr = 0o644 << 16
    archive.writestr(info, body, compress_type=zipfile.ZIP_DEFLATED, compresslevel=level)


def samples(report, work):
    work.mkdir(exist_ok=True, parents=True)
    output = work / "ds26-reverse-glrt-iq.zip"
    temp = output.with_suffix(".partial")
    index = []
    with zipfile.ZipFile(temp, "w") as archive:
        for sub in PANELS:
            folder = report / sub
            for row in read(folder / "roster.json"):
                name = key(row)
                m = read(folder / "measurements" / (name + ".json"))
                segment, manifest, w = decode(_load_case(row["case"]), row["visit"])
                data = w.samples.tobytes()
                if not (
                    digest(data) == w.iq_sha256.removeprefix("sha256:")
                    and w.iq_sha256 == m["signed_iq"]
                    and manifest == m["manifest"]
                    and w.acquisition["sample_start"] == row["counter"]
                ):
                    raise ValueError("raw byte payload or clock differs from recorded experiment")
                entry = "iq/" + name + ".ci16"
                add(archive, entry, data, 1)
                index.append(
                    dict(
                        key=name,
                        panel=sub or "initial",
                        case=row["case"],
                        visit=row["visit"],
                        evaluated_antenna=row["rx"],
                        channel=row["channel"],
                        edge=row["edge"],
                        physical_id=row["id"],
                        file=entry,
                        sha256=w.iq_sha256,
                        shape=list(w.samples.shape),
                        dtype="<i2",
                        sample_rate_hz=w.sample_rate_hz,
                        hardware_sample_counter=row["counter"],
                        receiver_ids=w.receiver_ids,
                        segment=segment,
                        manifest_sha256=manifest,
                        window_sequence=w.sequence,
                        target=w.target,
                        acquisition=w.acquisition,
                    )
                )
        descriptor = dict(format="little-endian signed int16 [sample, antenna, I/Q]", visits=index)
        add(archive, "index.json", packed(descriptor) + b"\n", 6)
    with zipfile.ZipFile(temp, "r") as archive:
        listed = json.loads(archive.read("index.json"))
        if (
            len(index) != 229
            or len(archive.namelist()) != 230
            or len({r["key"] for r in index}) != 229
        ):
            raise ValueError("stereo corpus incomplete or duplicated")
        for row in listed["visits"]:
            if digest(archive.read(row["file"])) != row["sha256"].removeprefix("sha256:"):
                raise ValueError("archived signed bytes do not match acquisition")
    temp.replace(output)
    receipt = dict(
        path=str(output.resolve()),
        sha256=_sha(output),
        bytes=output.stat().st_size,
        visits=len(index),
        payload_bytes=sum(2 * r["shape"][0] * r["shape"][1] * r["shape"][2] for r in index),
    )
    (report / "raw-bundle.json").write_bytes(packed(receipt) + b"\n")
    print("verified original stereo I/Q package", receipt, flush=True)


def tables(report):
    data = [
        *report.glob("*.csv*"),
        *report.glob("*.md"),
        report / "manifest.json",
        report / "owner-summary.json",
        report / "opportunities.jsonl.gz",
        report / "summary.json",
        report / "verification.json",
        report / "raw-bundle.json",
        report / "reverse-search.png",
        report / "complete-associations/orbit-source.json",
        report / "census/summary.json",
    ]
    for sub in PANELS:
        folder = report / sub
        data.extend([folder / "roster.json", folder / "search-lock.json", folder / "manifest.json"])
    for name in (
        "recovery/nominations.json",
        "recovery/unseen-frames.json",
        "recovery/wide/roster.json",
        "stock/source-lock.json",
        "recovery/wide/stock/source-lock.json",
    ):
        data.append(report / name)
    dest = report / "reference-dataset.zip"
    tmp = dest.with_suffix(".partial")
    with zipfile.ZipFile(tmp, "w") as archive:
        for path in sorted(set(data)):
            add(archive, str(path.relative_to(report)), path.read_bytes(), 6)
    with zipfile.ZipFile(tmp) as archive:
        if archive.testzip() is not None:
            raise ValueError("reference tables did not round trip")
    tmp.replace(dest)
    print("verified portable reference", dest, dest.stat().st_size, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=Path, default=REPORT)
    p.add_argument("--work", type=Path, default=WORK)
    p.add_argument("--samples", action="store_true")
    p.add_argument("--tables", action="store_true")
    a = p.parse_args()
    if a.samples or not a.tables:
        samples(a.report, a.work)
    if a.tables or not a.samples:
        tables(a.report)
