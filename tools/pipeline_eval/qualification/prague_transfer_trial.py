"""Authenticate the CTU deposit and replay its tied Doppler/orbit observations."""

import argparse
import re
import time
from collections import Counter
from datetime import UTC, datetime
from hashlib import md5, sha256
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

import numpy as np
from scipy.io import loadmat

from ..__main__ import ROOT, local_output, save_json
from ..scoring import validate_result
from ..variants import prague_transfer as model
from .full_v5_check import _sha

OUT = ROOT / "reports/2026_11_19_receiver_screening/original-schedule/prague-transfer"
PUBLICATION = "https://hdl.handle.net/10467/184304"
API = "https://dspace.cvut.cz/server/api/core/bitstreams"
SOURCES = {
    "outputs.zip": (
        "0ec1e6ed-5f42-48c0-b529-496337ec91ca",
        4640111,
        "dd4f2da6b28ae597dfb33e1a26ab6ed1",
        "c41ae39f242ddb042c31831e07f7b7a93b2596fa2cc5fabd71be695e220a1068",
    ),
    "scripts.zip": (
        "2ca21ff7-7884-47df-a888-2376570c016e",
        58041,
        "39b8b180d027701dc9da0a225b2c150b",
        "91338ae39af96185ae478a743b81087b9df8ecb6e1cf6accd0009519ab3a836f",
    ),
    "thesis-author.pdf": (
        "3b689666-e28a-4874-8f6d-fcd2fe7f8785",
        40690642,
        "0f79f2513d3cf8732bb42a73f828e437",
        "6c342685f8472c40626fed35c70acada3bd2a2c0364aea3750c1489a74951836",
    ),
}
FILE_STAMP = re.compile(r"(\d{2}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{4})")
SUFFIX_PRIORITY = {"fusion": 0, "multisat files": 1, "single sat": 2}
PLAN = "study-plan.json"
PREDICTIONS = "predictions.json"
AUDIT = "source-audit.json"
LOCK = "prediction-lock.json"


def source_receipts(folder, names=SOURCES):
    receipts = {}
    for name in names:
        uuid, size, checksum, digest = SOURCES[name]
        body = (folder / name).read_bytes()
        if (
            len(body) != size
            or md5(body).hexdigest() != checksum
            or sha256(body).hexdigest() != digest
        ):
            raise ValueError(f"external source bytes changed for {name}")
        receipts[name] = dict(
            url=f"{API}/{uuid}/content", bytes=size, dspace_md5=checksum, sha256=digest
        )
    return receipts


def members(archive):
    return [
        path
        for name in archive.namelist()
        if not name.endswith("/")
        and (path := PurePosixPath(name)).parts[0] != "__MACOSX"
        and not path.name.startswith("._")
    ]


def read_mat(archive, path):
    body = archive.read(str(path))
    return loadmat(BytesIO(body), simplify_cells=True)["results"], sha256(body).hexdigest()


def timestamp(name):
    match = FILE_STAMP.search(name)
    if match is None:
        raise ValueError("no explicit acquisition start in deposit filename")
    return datetime.strptime(match[0], "%H-%M-%S_%d-%m-%Y").replace(tzinfo=UTC)


def observations(data):
    if (
        data["f_carrier"] != model.RF_HZ
        or data["apply_mf_time_offset"]
        or data["subtract_per_sat_biases"]
    ):
        raise ValueError(
            "the export does not carry the expected raw Doppler and unshifted orbit mode"
        )
    f = data["fusion"]
    arcs = []
    for ordinal, source_track in enumerate(np.atleast_1d(data["meas"]), 1):
        chosen = f["sat_id_all"] == ordinal
        times, frequency = f["t_all"][chosen], f["f_meas_all_raw"][chosen]
        pos = f["r_sat_all"][:, chosen].T / 1000
        vel = f["v_sat_all"][:, chosen].T / 1000
        source_time, source_hz = source_track["t_sec"], source_track["f_khz_meas"] * 1000
        idx = np.searchsorted(source_time, times)
        radius, speed = np.linalg.norm(pos, axis=1), np.linalg.norm(vel, axis=1)
        if (
            len(times) < 16
            or np.any(np.diff(times) <= 0)
            or np.any(idx == len(source_time))
            or not np.array_equal(source_time[idx], times)
            or not np.allclose(frequency, source_hz[idx], rtol=0, atol=1e-6)
            or not np.isfinite(np.column_stack((times, frequency, pos, vel))).all()
            or not np.all((radius > 6800) & (radius < 8000))
            or not np.all((speed > 6) & (speed < 9))
        ):
            raise ValueError("invalid ECEF geometry, time, or measured Doppler selection")
        arcs.append(model.Arc(times, frequency, pos, vel))
    if len(arcs) != data["n_satellites"] or sum(len(a.times_s) for a in arcs) != len(f["t_all"]):
        raise ValueError("Orbit and observation layers disagree")
    return tuple(arcs)


def recordings(archive, paths):
    included = {}
    for path in paths:
        if not path.name.startswith("position_") or path.suffix != ".mat":
            continue
        data, digest = read_mat(archive, path)
        stamp = timestamp(path.name)
        if timestamp(data["file"]) != stamp:
            raise ValueError("chosen export and nested recording timestamps disagree")
        arcs = observations(data)
        rank = (-len(arcs), SUFFIX_PRIORITY[path.parent.name], str(path))
        if stamp not in included or rank < included[stamp][0]:
            included[stamp] = (rank, path, digest, arcs)
    return sorted(included.items())


def trial(source, out):
    if (out / LOCK).exists():
        raise FileExistsError("preserve the first prediction lock")
    receipts = source_receipts(source)
    with ZipFile(source / "scripts.zip") as archive:
        scripts = members(archive)
    with ZipFile(source / "outputs.zip") as archive:
        files = members(archive)
        selected = recordings(archive, files)
    save_json(
        out / AUDIT,
        dict(
            publication=PUBLICATION,
            sources=receipts,
            outputs_by_extension=dict(Counter(p.suffix for p in files)),
            scripts_by_extension=dict(Counter(p.suffix for p in scripts)),
            position_exports=sum(p.name.startswith("position_") for p in files),
            inventory=[str(p) for p in files + scripts],
            iq_released=False,
            causal_tle_released=False,
            capture_utc_authority="Deposit script treats filenames as UTC, unverified externally",
            tracking_boundary="Spectral peak selection in truth-assisted satellite windows",
            orbit_boundary="Author-bundled unshifted ECEF without orbit epochs or collection times",
        ),
    )
    plan = dict(
        policy="One export per timestamp. Rank by track count, then fusion, multisat, single.",
        rf_hz=model.RF_HZ,
        nominal_height_m=model.HEIGHT_M,
        c="With one nominal RF the calibration column lies in the span of track intercepts",
        holdout="Last 40% by chronology per track, untouched by the grid search or intercept fit",
        cfo_bin_hz=model.IMPROVEMENT_HZ,
        offers={key: model.offered_tile(offset) for key, offset in model.OFFSETS.items()},
        captures=[
            dict(
                id=stamp.strftime("%Y%m%dT%H%M%SZ"),
                start_utc=stamp.isoformat(),
                member=str(path),
                sha256=digest,
                tracks=len(arcs),
                samples=sum(len(a.times_s) for a in arcs),
                first_sample_s=min(float(a.times_s[0]) for a in arcs),
                last_sample_s=max(float(a.times_s[-1]) for a in arcs),
            )
            for stamp, (_, path, digest, arcs) in selected
        ],
    )
    save_json(out / PLAN, plan)
    predictions = []
    for capture, (stamp, (_, _, _, arcs)) in zip(plan["captures"], selected, strict=True):
        for key, offset in model.OFFSETS.items():
            for method in model.METHODS:
                start_wall, start_cpu = time.perf_counter(), time.process_time()
                result = model.fit(arcs, offset, method, int(stamp.timestamp()))
                wall_s, cpu_s = time.perf_counter() - start_wall, time.process_time() - start_cpu
                validate_result(result)
                predictions.append(
                    dict(
                        id=f"{capture['id']}-{key}",
                        recording=capture["id"],
                        offer=key,
                        method=method,
                        result=result,
                        cpu_s=cpu_s,
                        wall_s=wall_s,
                        tile=plan["offers"][key],
                        input_sha256=capture["sha256"],
                        tracks=capture["tracks"],
                    )
                )
    save_json(out / PREDICTIONS, predictions)
    execution_sources = (Path(__file__), Path(model.__file__))
    save_json(
        out / LOCK,
        dict(
            files={file: _sha(out / file) for file in (AUDIT, PLAN, PREDICTIONS)},
            source_files={str(path.relative_to(ROOT)): _sha(path) for path in execution_sources},
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=local_output)
    parser.add_argument("--out", type=local_output, default=OUT)
    args = parser.parse_args()
    trial(args.source, args.out)


if __name__ == "__main__":
    main()
