"""Freeze, blind and measure the owner-released Bellaterra VHF geographic test."""

import argparse
import csv
import gzip
import json
import subprocess
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import md5, sha256
from pathlib import Path
from time import perf_counter

import numpy as np
from sgp4.api import Satrec

from ..__main__ import ROOT, encoded, save_json, write
from ..scoring import distance_km, validate_result
from ..variants import external_orbcomm as solver
from . import screening_figures
from .armijo_finish_results import pack
from .prefix_figures import csv_file

REPORT = ROOT / "reports/2026_11_19_receiver_screening/latency-and-support/external-position"
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
BLOCKS = tuple(datetime(2026, 3, 30, tzinfo=UTC) + timedelta(days=2 * i) for i in range(4))
OLD_NS = 6 * 3600 * 10**9
PASS_GAP_NS = 150 * 10**9
DAY_NS = 86400 * 10**9
MAX_PASS_SAMPLES = 40
SITE = (41.5002, 2.1129)
SITE_HEIGHT_M = 198.5
SEED = 830244
ABLA = ("measurements.csv", "tles.csv")
CORES = (22, 23)
PREDECLARED_COLUMNS = (
    "timestamp_utc",
    "channel_freq_hz",
    "doppler_measured_hz",
    "satellite_name",
    "tle_id",
)


def digest(data):
    return sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def check(out, name):
    lock = read(out / name)
    if any(digest((out / key).read_bytes()) != h for key, h in lock["files"].items()):
        raise ValueError(f"{name} is inconsistent with measured evidence")
    return lock


def ns(dt):
    d = dt - EPOCH
    return (d.days * 86400 + d.seconds) * 10**9 + d.microseconds * 1000


def date_ns(text):
    return ns(datetime.fromisoformat(f"{text[6:10]}-{text[3:5]}-{text[:2]}T{text[11:]}+00:00"))


def authenticate(source):
    version = read(source / "dataverse.json")["data"]["latestVersion"]
    if (version["versionNumber"], version["versionMinorNumber"]) != (2, 0):
        raise ValueError("unexpected Bellaterra data release")
    raw = {}
    for name, expected_id in zip(ABLA, (477221, 477222), strict=True):
        index = next(r["dataFile"] for r in version["files"] if r["dataFile"]["id"] == expected_id)
        body = (source / name).read_bytes()
        if (
            index["originalFileName"] != name
            or index["originalFileSize"] != len(body)
            or md5(body).hexdigest() != index["md5"]
        ):
            raise ValueError("source bytes differ from publisher original file authority")
        raw[name] = dict(
            sha256=digest(body), publisher_md5=index["md5"], size=len(body), id=expected_id
        )
    return dict(
        files=raw,
        dataverse_sha256=digest((source / "dataverse.json").read_bytes()),
        doi="10.34810/DATA3383",
        version="2.0",
    )


def parse_tracks(source):
    orbits, ids = {}, {}
    with (source / "tles.csv").open(newline="") as handle:
        for item in csv.DictReader(handle):
            k, name = item["tle_id"], item["satellite_name"]
            _, first, second = item["tle_3line"].splitlines()
            sat = Satrec.twoline2rv(first, second)
            epoch = round(((sat.jdsatepoch - 2440587.5) + sat.jdsatepochF) * DAY_NS)
            if name in ids and ids[name] != sat.satnum:
                raise ValueError("published satname maps to multiple NORAD identifiers")
            ids[name] = sat.satnum
            orbits[k] = dict(
                norad=sat.satnum, tle=[first, second], epoch_ns=epoch, first_used_ns=None
            )
    groups = defaultdict(list)
    seen, early_bad, all_rows = Counter(), 0, 0
    with (source / "measurements.csv").open(newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames) != PREDECLARED_COLUMNS:
            raise ValueError("unexpected measured-only input schema")
        for row in reader:
            t, rf, measured, name, tid = (row[k] for k in PREDECLARED_COLUMNS)
            stamp, f, y = date_ns(t), float(rf), float(measured)
            orbit = orbits[tid]
            if orbit["norad"] != ids[name] or not np.isfinite(y) or not 137.2e6 <= f <= 137.8e6:
                raise ValueError("invalid labelled carrier observation")
            last = orbit["first_used_ns"]
            orbit["first_used_ns"] = stamp if last is None else min(last, stamp)
            all_rows += 1
            early_bad += stamp < orbit["epoch_ns"]
            day = stamp // DAY_NS
            seen[name] += 1
            groups[day, ids[name], f].append((stamp, y, tid))
    if all_rows != 615738 or len(ids) != 6 or len(orbits) != 123:
        raise ValueError("owner-published roster is incomplete")
    return (
        groups,
        orbits,
        dict(
            author_rows=all_rows,
            original_linked_future_epoch_rows=early_bad,
            historical_id_counts=seen,
        ),
    )


def earlier(orbits, start, norad):
    target = start - OLD_NS
    choices = [
        (r["epoch_ns"], r["first_used_ns"], key)
        for key, r in orbits.items()
        if r["norad"] == norad
        and r["first_used_ns"] is not None
        and r["epoch_ns"] <= target
        and r["first_used_ns"] <= target
    ]
    return max(choices)[2] if choices else None


def passes(records, tid, norad, rf):
    traces = []
    aligned = sorted(records)
    groups = [[]]
    for t, y, source_tle in aligned:
        if groups[-1]:
            gap = t - groups[-1][-1][0]
            if gap == 0:
                raise ValueError("duplicated satellite/carrier observation time")
            if gap > PASS_GAP_NS:
                groups.append([])
        groups[-1].append((t, y, source_tle))
    for samples in groups:
        if len(samples) < 12 or samples[-1][0] - samples[0][0] < 90 * 10**9:
            continue
        pick = np.linspace(0, len(samples) - 1, min(MAX_PASS_SAMPLES, len(samples)), dtype=int)
        used = [samples[i] for i in pick]
        same = sum(tle == tid for _, _, tle in used)
        traces.append(
            (
                dict(
                    norad=norad,
                    rf_hz=rf,
                    tle_id=tid,
                    times_ns=[t for t, _, _ in used],
                    cfo_hz=[y for _, y, _ in used],
                ),
                same,
                len(samples),
            )
        )
    return traces


def make_plan(groups, orbits, out, work):
    public = work / "public"
    public.mkdir(parents=True, mode=0o700)
    rng = np.random.default_rng(SEED)
    truth, offers, receipts = {}, [], []
    for start in BLOCKS:
        beginning = ns(start)
        packet, used, matched_count, coverage = {}, set(), 0, Counter()
        for phase, day in (("training", beginning // DAY_NS), ("held", beginning // DAY_NS + 1)):
            packet[phase] = []
            for (d, sat, rf), rows in groups.items():
                if d != day:
                    continue
                tid = earlier(orbits, beginning, sat)
                if tid is None:
                    coverage[f"{phase}_rows_no_earlier_orbit"] += len(rows)
                    continue
                for trace, same, available in passes(rows, tid, sat, rf):
                    packet[phase].append(trace)
                    matched_count += same
                    coverage[f"{phase}_eligible_rows"] += available
                    coverage[f"{phase}_used"] += len(trace["cfo_hz"])
                    used.add(tid)
        packet["elements"] = {k: orbits[k] for k in sorted(used)}
        positive = int(rng.integers(0, 2))
        sign = int(rng.choice((-1, 1)))
        for kind, km in (("containing", float(rng.uniform(6, 9))), ("omitted", 14.0)):
            shift = [0.0, 0.0]
            shift[positive] = sign * km
            tile = solver.geographic(SITE, shift)
            ident = rng.bytes(12).hex()
            row = dict(packet=packet, tile=tile)
            buffer = encoded(row)
            write(public / f"{ident}.json", buffer)
            offers.append(
                dict(
                    id=ident,
                    input_sha256=digest(buffer),
                    native_sha256=digest(encoded({k: packet[k] for k in ("training", "held")})),
                    catalogue_sha256=digest(encoded(packet["elements"])),
                    block=start.date().isoformat(),
                )
            )
            truth[ident] = dict(
                site=list(SITE), condition=kind, center=tile, reference_height_m=SITE_HEIGHT_M
            )
        receipts.append(
            dict(
                block=start.date().isoformat(),
                cutoff_ns=beginning - OLD_NS,
                total_sampled_rows_linked_to_same_tle=matched_count,
                coverage=dict(coverage),
                selected_tle_ids=sorted(used),
            )
        )
    rng.shuffle(offers)
    save_json(work / "labels.json", truth)
    save_json(out / "support.json", receipts)
    return offers


def prepare(source, work, out):
    if (out / "input-lock.json").exists():
        raise FileExistsError("external receiver study already bound")
    save_json(out / "publisher-receipt.json", authenticate(source))
    sources = (
        Path(__file__),
        Path(solver.__file__),
        ROOT / "src/leo/sky/frames.py",
        out / "PROTOCOL.md",
    )
    save_json(
        out / "source-lock.json",
        dict(
            sha256={str(p): digest(p.read_bytes()) for p in sources},
            samples_per_pass=MAX_PASS_SAMPLES,
            tile_width_km=solver.WIDTH,
            fit_height_m=0,
            c_identifiable=False,
            seed=SEED,
        ),
    )
    groups, orbits, data = parse_tracks(source)
    offers = make_plan(groups, orbits, out, work)
    save_json(out / "requests.json", offers)
    save_json(out / "catalogue-audit.json", dict(data, catalogue=orbits))
    names = (
        "requests.json",
        "catalogue-audit.json",
        "source-lock.json",
        "support.json",
        "publisher-receipt.json",
    )
    save_json(
        out / "input-lock.json",
        dict(
            files={n: digest((out / n).read_bytes()) for n in names},
            labels_sha256=digest((work / "labels.json").read_bytes()),
        ),
    )


def invocation(cpu):
    python = Path(sys.executable)
    prefix, base = Path(sys.prefix), Path(sys.base_prefix)
    paths = ("/usr", "/lib", "/lib64", str(base), str(prefix))
    cmd = [
        "taskset",
        "-c",
        str(cpu),
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--clearenv",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--dir",
        "/solver",
        "--chdir",
        "/solver",
        "--setenv",
        "HOME",
        "/tmp",
    ]
    for a in paths:
        cmd.extend(("--ro-bind", a, a))
    if python.is_symlink():
        alias = (python.parent / python.readlink()).parent.parent
        if alias != base and alias.is_absolute():
            cmd.extend(("--ro-bind", str(base), str(alias)))
    for env in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        cmd.extend(("--setenv", env, "1"))
    cmd.extend(
        (
            "--ro-bind",
            str(solver.__file__),
            "/solver/worker.py",
            "--ro-bind",
            str(ROOT / "src/leo"),
            "/solver/leo",
            str(python),
            "-B",
            "/solver/worker.py",
        )
    )
    return cmd


def solve(work, out):
    check(out, "input-lock.json")
    plan = read(out / "source-lock.json")["sha256"]
    if any(digest(Path(p).read_bytes()) != h for p, h in plan.items()):
        raise ValueError("frozen position code differs from isolated worker")
    cases = read(out / "requests.json")

    def execute(case, cpu):
        path = work / "public" / f"{case['id']}.json"
        raw = path.read_bytes()
        if digest(raw) != case["input_sha256"]:
            raise ValueError("opaque receiver packet changed before solver")
        started = perf_counter()
        call = subprocess.run(invocation(cpu), input=raw, capture_output=True, timeout=30)
        elapsed = perf_counter() - started
        if call.returncode:
            raise RuntimeError(call.stderr.decode(errors="replace"))
        payload = json.loads(call.stdout)
        print(case["id"], [r["status"] for r in payload["results"].values()], flush=True)
        return [
            dict(
                case,
                method=m,
                result=r,
                worker_wall_s=elapsed,
                support=payload["support"],
                runtime_scope="all three numerical arms in one isolated job",
            )
            for m, r in payload["results"].items()
        ]

    with ThreadPoolExecutor(max_workers=2) as pool:
        one = [pool.submit(execute, r, CORES[i % 2]) for i, r in enumerate(cases)]
        rows = [r for f in one for r in f.result()]
    for r in rows:
        validate_result(r["result"])
    pack(out, "positions.jsonl.gz", rows)
    names = ("positions.jsonl.gz", "input-lock.json", "source-lock.json", "support.json")
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=[r["id"] for r in cases], files={n: digest((out / n).read_bytes()) for n in names}
        ),
    )


def score(work, out):
    frozen = check(out, "prediction-lock.json")
    bound = check(out, "input-lock.json")
    private = (work / "labels.json").read_bytes()
    if digest(private) != bound["labels_sha256"]:
        raise ValueError("ground truth mismatches prospective offer lock")
    truth = json.loads(private)
    with gzip.open(out / "positions.jsonl.gz", "rt") as stream:
        rows = list(map(json.loads, stream))
    expected = {(r["id"], m) for r in read(out / "requests.json") for m in solver.METHODS}
    if len(rows) != len(expected) or {(r["id"], r["method"]) for r in rows} != expected:
        raise ValueError("terminal measured comparison is incomplete")
    query, stats = {}, []
    for r in rows:
        ident, method = r["id"], r["method"]
        label, fit = truth[ident], r["result"]
        pos, science = fit["arms"]["c0"], fit["metrics"]
        cond = label["condition"]
        query[ident] = dict(
            id=ident,
            condition=cond,
            truth=label["site"],
            recording=r["block"],
            bindings={k: r[k] for k in ("input_sha256", "native_sha256", "catalogue_sha256")},
        )
        stats.append(
            dict(
                id=ident,
                block=r["block"],
                method=method,
                condition=cond,
                status=fit["status"],
                reason=fit["reason"],
                publication=pos["latlon"] is not None,
                false_fix=cond == "omitted" and pos["latlon"] is not None,
                error_km=distance_km(label["site"], pos["latlon"]),
                forced_error_km=distance_km(label["site"], pos["forced_latlon"]),
                held_rf_rms_hz=pos.get("rf_rms_hz"),
                held_gained_hz=science.get("held_center_gain_hz"),
                held_repeat_km=science.get("held_stability_km"),
                train_face_km=science.get("max_face_km"),
                held_face_km=science.get("held_face_km"),
                wall_s_all_three_methods_same_query=r["worker_wall_s"],
                **r["support"],
            )
        )
    csv_file(out / "scores.csv", stats)
    write(out / "truth-after-lock.json", private)
    save_json(out / "figure-queries.json", dict(queries=[query[i] for i in frozen["cases"]]))
    names = (
        "positions.jsonl.gz",
        "truth-after-lock.json",
        "figure-queries.json",
        "scores.csv",
        "prediction-lock.json",
    )
    save_json(
        out / "score-lock.json",
        dict(cases=frozen["cases"], files={n: digest((out / n).read_bytes()) for n in names}),
    )
    chart(out)


def chart(out):
    labels = ("Held shape", "Unguarded", "Absolute CFO", "Time-reversed", "Offer center")

    def series(key, i):
        row = dict(key=key, label=labels[i], file="positions.jsonl.gz", value=solver.METHODS[i])
        if key != "candidate":
            row["match"] = ["input_sha256", "native_sha256", "catalogue_sha256"]
        return row

    common = dict(
        method=solver.METHODS[0],
        scope="transfer",
        cases="sealed",
        seal="score-lock.json",
        queries="figure-queries.json",
        provenance=["prediction-lock.json", "scores.csv"],
        condition_labels=dict(containing="25 km containing", omitted="25 km near omitted"),
    )
    specs = [
        dict(
            common,
            id=ident,
            title=title,
            caption=(
                "Measured ORBCOMM VHF with deposited site-conditioned identities. "
                "Four disjoint day pairs at one station. Only the fixed zero-slope arm is scored."
            ),
            series=rows,
        )
        for ident, title, rows in (
            (
                "external-orbcomm-held-position",
                "External measured VHF position with a held day",
                [series(key, i) for i, key in enumerate(("candidate", "stock", "one", "four"))],
            ),
            (
                "external-orbcomm-geography-prior",
                "External VHF position against the offered center",
                [series("candidate", 0), series("stock", 4)],
            ),
        )
    ]
    save_json(out / "figures.json", dict(version=1, charts=specs))
    screening_figures.generate(out / "charts", arms=("c0",), evidence=out)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("prepare", "solve", "score"))
    p.add_argument("work", type=Path)
    p.add_argument("--source", type=Path)
    p.add_argument("--out", type=Path, default=REPORT)
    options = p.parse_args()
    if options.action == "prepare":
        prepare(options.source, options.work, options.out)
    elif options.action == "solve":
        solve(options.work, options.out)
    else:
        score(options.work, options.out)


if __name__ == "__main__":
    main()
