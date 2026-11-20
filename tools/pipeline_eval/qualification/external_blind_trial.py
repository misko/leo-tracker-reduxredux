"""Seal and score anonymous carrier measurements from one measured VHF installation."""

import argparse
import csv
import gzip
import json
import subprocess
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import numpy as np
from sgp4.api import Satrec

from .. import figure_books
from ..__main__ import ROOT, encoded, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants import external_blind_doppler as solver
from . import external_orbcomm_trial as source_contract
from .armijo_finish_results import pack
from .external_orbcomm_trial import DAY_NS, authenticate, check, date_ns, digest, ns, read
from .prefix_figures import csv_file

REPORT = ROOT / "reports/2026_11_19_receiver_screening/receiver-choice/external-blind"
PRIMARY_SOURCE = "https://doi.org/10.34810/DATA3383"
MEMBERSHIP_SOURCE = "https://celestrak.org/norad/elements/table.php?FORMAT=json&GROUP=orbcomm"
HISTORY_SOURCE = "https://satchecker.cps.iau.org/tools/get-tle-data/"
DATES = ("2026-03-31", "2026-04-06")
MEMBERS = tuple(range(40086, 40092)) + tuple(range(41179, 41190))
BOARDS = (
    ((41.56, 2.02), (41.41, 2.43), (41.80, 2.14)),
    ((41.23, 1.97), (41.41, 2.43), (41.80, 2.14)),
)
CORES = (10, 11)
SAMPLES_PER_TRACK = 32
MAX_TRACKS = 64
TRACK_GAP_S = 18
MIN_TRACK_SPAN_S = 75
ARTIFACT = "positions.jsonl.gz"


def day_start(day):
    return ns(datetime.fromisoformat(day).replace(tzinfo=UTC))


def random_key(kind, *items):
    return digest(encoded(("bellaterra-anonymous-20261119-v1", kind, items)))[:24]


def anonymous_chains(records):
    """Associate within a single RF channel using only time and measured frequency."""
    complete, active = [], []
    for stamp, freq in sorted(set(records)):
        still_active = []
        for chain in active:
            if stamp - chain[-1][0] <= TRACK_GAP_S * 10**9:
                still_active.append(chain)
            else:
                complete.append(chain)
        active = still_active
        nearest = None
        for i, chain in enumerate(active):
            end, previous = chain[-1]
            dt = (stamp - end) / 1e9
            if dt <= 0:
                continue
            drift = 0.0
            if len(chain) >= 3:
                beginning, before = chain[max(0, len(chain) - 5)]
                drift = np.clip((previous - before) / ((end - beginning) / 1e9), -45, 45)
            delta = abs(freq - previous - dt * drift)
            if delta <= 60 + dt * (15 if len(chain) >= 3 else 45):
                nearest = min(nearest, (delta, i)) if nearest is not None else (delta, i)
        if nearest is None:
            active.append([(stamp, freq)])
        else:
            active[nearest[1]].append((stamp, freq))
    return complete + active


def carrier_groups(source, *, backed_labels=False):
    groups, labels = defaultdict(list), defaultdict(set)
    selected = {day_start(day) // DAY_NS: day for day in DATES}
    with (source / "measurements.csv").open(newline="") as handle:
        rows = csv.reader(handle)
        if tuple(next(rows)) != source_contract.PREDECLARED_COLUMNS:
            raise ValueError("unexpected receiver-only archive schema")
        for row in rows:
            t, rf, y = date_ns(row[0]), float(row[1]), float(row[2])
            day = selected.get(t // DAY_NS)
            if day is None:
                continue
            if not np.isfinite(y) or not 137.2e6 <= rf <= 137.8e6:
                raise ValueError("invalid measured nominal RF or CFO")
            groups[day, rf].append((t, y))
            if backed_labels:
                labels[t, rf, y].add(row[3])
    return groups, labels


def tracks_for_day(day, groups):
    rows, candidates = 0, []
    for (date, rf), records in sorted(groups.items()):
        if date != day:
            continue
        rows += len(records)
        for chain in anonymous_chains(records):
            if (
                len(chain) < SAMPLES_PER_TRACK
                or chain[-1][0] - chain[0][0] < MIN_TRACK_SPAN_S * 1e9
            ):
                continue
            chosen = np.linspace(0, len(chain) - 1, SAMPLES_PER_TRACK, dtype=int)
            samples = [chain[i] for i in chosen]
            ident = random_key("track", (rf, samples))
            candidates.append(
                dict(
                    id=ident,
                    rf_hz=rf,
                    times_ns=[a for a, _ in samples],
                    cfo_hz=[b for _, b in samples],
                )
            )
    capped = sorted(candidates, key=lambda row: row["id"])[:MAX_TRACKS]
    return capped, dict(
        publisher_rows=rows, eligible_chains=len(candidates), used_chains=len(capped)
    )


def historical_ns(value):
    return ns(datetime.fromisoformat(value.removesuffix(" UTC")).replace(tzinfo=UTC))


def orbit_candidates(raw, day):
    cutoff = day_start(day)
    selected = []
    for norad in MEMBERS:
        doc = json.loads(raw[norad])
        records = doc["data"]
        if doc["count"] != len(records):
            raise ValueError("incomplete official orbit snapshot body")
        rows = []
        for row in records:
            if row["data_source"] != "celestrak":
                continue
            if row["satellite_id"] != norad or not row["satellite_name"].startswith("ORBCOMM "):
                raise ValueError("candidate catalogue membership mismatch")
            epoch, collected = (historical_ns(row[k]) for k in ("epoch", "date_collected"))
            tle = [row["tle_line1"], row["tle_line2"]]
            sat = Satrec.twoline2rv(*tle)
            launch = "14040" if norad < 41000 else "15081"
            from_lines = round((sat.jdsatepoch - 2440587.5 + sat.jdsatepochF) * DAY_NS)
            if sat.satnum != norad or not sat.intldesg.startswith(launch):
                raise ValueError("official snapshot does not bind to the expected OG2 launch")
            if abs(epoch - from_lines) > 10**9:
                raise ValueError("historical epoch field differs from TLE elements")
            if collected < cutoff and cutoff - 3 * DAY_NS <= epoch <= collected:
                rows.append(dict(norad=norad, epoch_ns=epoch, collected_ns=collected, tle=tle))
        if rows:
            selected.append(max(rows, key=lambda row: (row["epoch_ns"], row["collected_ns"])))
    if len(selected) < 8:
        raise ValueError("historical full membership has inadequate pre-day support")
    return selected


def prepare(source, work, out):
    public = work / "public"
    public.mkdir(parents=True, mode=0o700)
    files = [
        Path(__file__),
        Path(solver.__file__),
        Path(source_contract.__file__),
        ROOT / "src/leo/sky/frames.py",
    ]
    save_json(
        out / "source-lock.json",
        dict(files={str(f.relative_to(ROOT)): digest(f.read_bytes()) for f in files}),
    )
    authority = authenticate(source)
    raw = {sat: (source / "anonymous-catalogue" / f"{sat}.json").read_bytes() for sat in MEMBERS}
    historical = {
        str(sat): dict(
            url=HISTORY_SOURCE + f"?id={sat}&id_type=catalog"
            "&start_date_jd=2461125.5&end_date_jd=2461139.5",
            sha256=digest(raw[sat]),
            size=len(raw[sat]),
        )
        for sat in MEMBERS
    }
    save_json(
        out / "publisher-and-catalogue.json",
        dict(
            measurements=authority,
            membership=dict(url=MEMBERSHIP_SOURCE, ids=MEMBERS, launches=["2014-040", "2015-081"]),
            bodies=historical,
        ),
    )
    pack(out, "catalogue-bodies.jsonl.gz", [dict(norad=sat, body=raw[sat].decode()) for sat in raw])
    observed, unexpected_labels = carrier_groups(source)
    if unexpected_labels:
        raise ValueError("publisher identities leaked into anonymous preparation")
    rows, truth, packets, supports = [], {}, [], {}
    for day in DATES:
        tracks, support = tracks_for_day(day, observed)
        catalogue = orbit_candidates(raw, day)
        supports[day] = dict(
            support,
            causal_orbits=[r["norad"] for r in catalogue],
            missing_orbits=sorted(set(MEMBERS) - {r["norad"] for r in catalogue}),
        )
        for kind, centers in zip(("containing", "omitted"), BOARDS, strict=True):
            ident = random_key("request", day, centers)
            tiles = {random_key("tile", point): point for point in centers}
            packet = dict(tracks=tracks, catalogue=catalogue, cutoff_ns=day_start(day), tiles=tiles)
            buffer = encoded(packet)
            write(public / f"{ident}.json", buffer)
            rows.append(
                dict(
                    id=ident,
                    block=day,
                    input_sha256=digest(buffer),
                    native_sha256=digest(encoded(tracks)),
                    catalogue_sha256=digest(encoded(catalogue)),
                )
            )
            packets.append(dict(id=ident, packet=buffer.decode()))
            truth[ident] = dict(
                condition=kind,
                site=list(source_contract.SITE),
                reference_height_m=source_contract.SITE_HEIGHT_M,
            )
    rows.sort(key=lambda row: row["id"])
    save_json(out / "requests.json", rows)
    pack(out, "public-packets.jsonl.gz", packets)
    save_json(out / "support.json", supports)
    save_json(work / "labels.json", truth)
    names = (
        "PROTOCOL.md",
        "source-lock.json",
        "publisher-and-catalogue.json",
        "catalogue-bodies.jsonl.gz",
        "requests.json",
        "public-packets.jsonl.gz",
        "support.json",
    )
    seal(
        out,
        "input-lock.json",
        rows,
        names,
        labels_sha256=digest((work / "labels.json").read_bytes()),
    )


def seal(out, filename, roster, names, **other):
    save_json(
        out / filename,
        dict(
            cases=[row["id"] for row in roster],
            files={name: digest((out / name).read_bytes()) for name in names},
            **other,
        ),
    )


def solve(work, out):
    expected = check(out, "input-lock.json")
    for path, frozen in read(out / "source-lock.json")["files"].items():
        if digest((ROOT / path).read_bytes()) != frozen:
            raise ValueError("frozen anonymous Doppler implementation changed")
    cases = read(out / "requests.json")
    if [r["id"] for r in cases] != expected["cases"]:
        raise ValueError("frozen blind roster changed")

    def execute(bucket, cpu):
        rows = []
        for case in bucket:
            cmd = source_contract.invocation(cpu)
            cmd[cmd.index(str(source_contract.solver.__file__))] = str(solver.__file__)
            raw = (work / "public" / f"{case['id']}.json").read_bytes()
            if digest(raw) != case["input_sha256"]:
                raise ValueError("opaque receiver input changed")
            start = perf_counter()
            try:
                call = subprocess.run(cmd, input=raw, capture_output=True, timeout=60, check=True)
                payload = json.loads(call.stdout)
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
                status = "timed_out" if isinstance(exc, subprocess.TimeoutExpired) else "failed"
                rows.extend(
                    dict(
                        case,
                        method=m,
                        worker_wall_s=perf_counter() - start,
                        result=dict(
                            status=status,
                            reason=str(exc),
                            metrics={},
                            boundary="Anonymous VHF board",
                        ),
                    )
                    for m in solver.METHODS
                )
                continue
            wall = perf_counter() - start
            print(case["id"], wall, [r["status"] for r in payload["results"].values()], flush=True)
            rows.extend(
                dict(
                    case,
                    method=m,
                    result=r,
                    worker_wall_s=wall,
                    worker_cpu_s=payload["cpu_s"],
                    runtime_scope="one optical-free anonymous job with all three methods",
                )
                for m, r in payload["results"].items()
            )
        return rows

    with ThreadPoolExecutor(max_workers=2) as workers:
        outputs = [workers.submit(execute, cases[i::2], cpu) for i, cpu in enumerate(CORES)]
        rows = [row for future in outputs for row in future.result()]
    for row in rows:
        validate_result(row["result"])
    pack(out, ARTIFACT, sorted(rows, key=lambda row: (row["id"], row["method"])))
    seal(out, "prediction-lock.json", cases, (ARTIFACT, "input-lock.json"))


def score(source, work, out):
    predicted = check(out, "prediction-lock.json")
    bound = check(out, "input-lock.json")
    cases = read(out / "requests.json")
    private = (work / "labels.json").read_bytes()
    if digest(private) != bound["labels_sha256"]:
        raise ValueError("labels changed after input lock")
    label = json.loads(private)
    deposits = source_contract.parse_tracks(source)[1]
    deposit_labels = {row["norad"] for row in deposits.values()}
    with (source / "tles.csv").open(newline="") as handle:
        names = {
            row["satellite_name"]: deposits[row["tle_id"]]["norad"]
            for row in csv.DictReader(handle)
        }
    _, labels = carrier_groups(source, backed_labels=True)
    with gzip.open(out / ARTIFACT, "rt") as handle:
        rows = [json.loads(line) for line in handle]
    expected = {(r["id"], m) for r in cases for m in solver.METHODS}
    if len(rows) != len(expected) or {(r["id"], r["method"]) for r in rows} != expected:
        raise ValueError("terminal blind comparison is incomplete")
    queries, stats = {}, []
    for row in rows:
        ident, result = row["id"], row["result"]
        condition, site = (label[ident][x] for x in ("condition", "site"))
        metrics, arm = result["metrics"], result.get("arms", {}).get("c0", {})
        packet = read(work / "public" / f"{ident}.json")
        attribution = []
        for chain in packet["tracks"]:
            source_names = [
                name
                for t, y in zip(chain["times_ns"], chain["cfo_hz"], strict=True)
                for name in labels[t, chain["rf_hz"], y]
            ]
            most = Counter(source_names).most_common(1)
            attribution.append(
                names[most[0][0]] if most and most[0][1] >= 0.9 * SAMPLES_PER_TRACK else None
            )
        accepted = metrics.get("accepted_chain_norad", [None] * len(attribution))
        verifiable = [
            (a, b)
            for a, b in zip(attribution, accepted, strict=True)
            if a is not None and b is not None
        ]
        truth_tile = [key for key, center in packet["tiles"].items() if inside(center, site)]
        if len(truth_tile) != int(condition == "containing"):
            raise ValueError("offered board does not match frozen containing/omitted condition")
        query = dict(
            id=ident,
            condition=condition,
            truth=site,
            recording=row["block"],
            bindings={k: row[k] for k in ("input_sha256", "native_sha256", "catalogue_sha256")},
        )
        queries[ident] = query
        stats.append(
            dict(
                id=ident,
                day=row["block"],
                condition=condition,
                method=row["method"],
                status=result["status"],
                reason=result["reason"],
                published=arm.get("latlon") is not None,
                false_fix=condition == "omitted" and arm.get("latlon") is not None,
                error_km=distance_km(site, arm.get("latlon")),
                forced_error_km=distance_km(site, arm.get("forced_latlon")),
                truth_tile_selected=metrics.get("tile") in truth_tile,
                held_robust_rms_hz=arm.get("rf_rms_hz"),
                held_tracks=metrics.get("held_tracks"),
                held_orbits=metrics.get("held_orbit_count"),
                face_km=metrics.get("face_km"),
                rival_hz=metrics.get("held_nearest_rival_gain_hz"),
                genuine_alternative_tracks=metrics.get("tracks_with_genuine_alternative"),
                candidate_norads=len(packet["catalogue"]),
                documented_decoys=len({o["norad"] for o in packet["catalogue"]} - deposit_labels),
                checked_identities=len(verifiable),
                agreeing_identities=sum(a == b for a, b in verifiable),
                wall_s=row["worker_wall_s"],
                cpu_s=row.get("worker_cpu_s"),
            )
        )
    csv_file(out / "scores.csv", stats)
    write(out / "truth-after-lock.json", private)
    save_json(out / "figure-queries.json", dict(queries=[queries[i] for i in predicted["cases"]]))
    seal(
        out,
        "score-lock.json",
        cases,
        (
            ARTIFACT,
            "prediction-lock.json",
            "scores.csv",
            "truth-after-lock.json",
            "figure-queries.json",
        ),
    )
    chart(out)


def inside(center, point):
    latitude, longitude = center
    east = 111.32 * np.cos(np.deg2rad(latitude)) * (point[1] - longitude)
    north = 111 * (point[0] - latitude)
    return max(abs(east), abs(north)) <= solver.WIDTH


def chart(out):
    alternatives = (
        ("candidate", "Anonymous held gate", solver.METHODS[0]),
        ("stock", "Same solver, no gate", solver.METHODS[1]),
        ("one", "Time-reversed CFO", solver.METHODS[2]),
    )
    series = [
        dict(key=key, label=label, value=value, file=ARTIFACT) for key, label, value in alternatives
    ]
    series[0]["forced_label"] = "Held gate · forced"
    series[2]["forced_label"] = "Time-reversed CFO · forced"
    for row in series[1:]:
        row["match"] = ["input_sha256", "native_sha256", "catalogue_sha256"]
    chart_id = "external-blind-orbcomm-tile-board"
    save_json(
        out / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id=chart_id,
                    title="Measured anonymous VHF across mixed geographic offers",
                    method=solver.METHODS[0],
                    scope="transfer",
                    cases="sealed",
                    seal="score-lock.json",
                    queries="figure-queries.json",
                    provenance=["prediction-lock.json", "scores.csv"],
                    caption="Two days from one Bellaterra station. Three tiles per offer and no "
                    "supplied identities. Upstream retention used surveyed geometry. "
                    "Fitted c is unidentifiable.",
                    condition_labels=dict(
                        containing="3 tiles incl. survey", omitted="3 tiles omit survey"
                    ),
                    series=series,
                )
            ],
        ),
    )
    figure_books.generate(out / "charts", ARMS, methods=[chart_id], panel="screening", evidence=out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "solve", "score", "chart"))
    parser.add_argument("work", type=Path)
    parser.add_argument(
        "--source", type=Path, default=Path.home() / ".cache/external-position-20261119"
    )
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args()
    if args.action == "solve":
        solve(args.work, args.out)
    elif args.action == "chart":
        chart(args.out)
    else:
        {"prepare": prepare, "score": score}[args.action](args.source, args.work, args.out)


if __name__ == "__main__":
    main()
