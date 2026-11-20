"""Publish measured Linux AArch64 emulation and local board-access evidence."""

import argparse
import datetime as dt
import gzip
import json
import os
import platform
import stat
from hashlib import sha256
from pathlib import Path
from statistics import median

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants.selective_capture import visit_pairs
from . import arm_receiver_eval as evaluation
from .arm_receiver_build import REPORT, SOURCE, WORK, check
from .full_v5_check import _sha
from .prefix_figures import csv_file

ARCHES = ("host", "arm64")
MODES = ("stock", "fifth")
EDGES = ("lower", "upper")


def check_local_access():
    path = ROOT / "reports/2026_11_19_receiver_screening/receiver-core/board-replay/access.json"
    prior = evaluation.read(path)
    tty = Path("/sys/class/tty/ttyACM0/device")
    usb = Path("/sys/bus/usb/devices") / prior["development_usb_parent"]
    nic = Path("/sys/class/net") / prior["routes"]["usb"]["interface"] / "device"
    pin = (
        ROOT
        / "reports/2026_09_30_native_adaptive_deployment/firmware/private"
        / "192.168.1.15-v054.root.known_hosts"
    )
    serial = (usb / "serial").read_text().strip() if usb.is_dir() else None
    save_json(
        REPORT / "board-access.json",
        dict(
            time_utc=dt.datetime.now(dt.UTC).isoformat(),
            local_architecture=platform.machine(),
            usb_ancestry_matches=usb.is_dir()
            and tty.exists()
            and nic.exists()
            and usb.resolve() in tty.resolve().parents
            and usb.resolve() in nic.resolve().parents,
            development_serial_matches=serial == prior["development_usb_serial"],
            development_serial_suffix=serial[-5:] if serial else None,
            usb_vendor_product=(usb / "idVendor").read_text().strip()
            + ":"
            + (usb / "idProduct").read_text().strip()
            if usb.is_dir()
            else None,
            usb_model=(usb / "product").read_text().strip() if usb.is_dir() else None,
            local_remoteproc_entries=sorted(
                p.name for p in Path("/sys/class/remoteproc").glob("*")
            ),
            local_iio_class=Path("/sys/bus/iio/devices").is_dir(),
            previous_route_identity_states={
                k: v["authentication"] for k, v in prior["routes"].items()
            },
            prior_access_sha256=_sha(path),
            project_pin_owner_uid=pin.stat().st_uid,
            project_pin_mode=f"{stat.S_IMODE(pin.stat().st_mode):04o}",
            project_pin_permitted_to_read=os.access(pin, os.R_OK),
            current_external_contact=False,
            current_physical_board_computation=False,
        ),
    )


def oracle_rows(entry, observation):
    if entry["kind"] != "control":
        return None
    target = entry["plant"]
    result = []
    for lane in observation["rows"]:
        gates = [r for r in evaluation.projection(lane) if r["passed_fractional_margin_gate"]]
        match = None
        if target["plant"]:
            match = any(
                abs(row["fractional_tracking_cfo_hz"] - target["cfo_hz"]) <= 1000
                and abs(
                    row["integer_epoch_sample"]
                    + row["fractional_epoch_offset_samples"]
                    - target["epoch"]
                )
                <= 2
                for row in gates
            )
        result.append(dict(gated=len(gates), planted_match=match))
    return result


def compare(work, corpus, host, arm):
    old = evaluation.read(work / "archived-probes.json")
    parent = evaluation.read(
        check(evaluation.PARENT / "prediction-lock.json", evaluation.PARENT_PIN)
    )
    for edge in EDGES:
        ident = corpus["roster"][edge][0]["id"]
        for mode, role in zip(MODES, ("control", "candidate"), strict=True):
            name = f"native/{role}/{ident}.json.gz"
            native = json.loads(
                gzip.decompress(check(evaluation.PARENT / name, parent["files"][name]).read_bytes())
            )
            expected = [tuple(r) for r in old[edge][mode]]
            if [pair for i, pair in visit_pairs(native["source"]["probes"]) if i < 6] != expected:
                raise ValueError(
                    "archived chronological payload differs from the sealed native archive"
                )
    outcomes, timing = [], []
    for edge in EDGES:
        for mode in MODES:
            paired = [data["results"][edge][mode]["visits"] for data in (host, arm)]
            for x, y in zip(*paired, strict=True):
                entry = corpus["roster"][edge][x["index"]]
                if (x["index"], x["repeat"]) != (y["index"], y["repeat"]):
                    raise ValueError("cross-target fixture mismatch")
                if x["repeat"] == 0:
                    past = old[edge][mode][x["index"]] if entry["kind"] == "recorded" else None
                    eq = (
                        [evaluation.projection(lane) for lane in x["rows"]]
                        == [p["candidates"] for p in past]
                        if past
                        else None
                    )
                    outcomes.append(
                        dict(
                            edge=edge,
                            mode=mode,
                            input=entry["file"],
                            kind=entry["kind"],
                            host_matches_published_recorded_probes=eq,
                            host_packet_sha256=sha256(
                                encoded(evaluation.scientific(x))
                            ).hexdigest(),
                            arm64_packet_sha256=sha256(
                                encoded(evaluation.scientific(y))
                            ).hexdigest(),
                            parity=evaluation.parity(x, y),
                            planted_host=oracle_rows(entry, x),
                            planted_arm64=oracle_rows(entry, y),
                        )
                    )
                for arch, row in zip(ARCHES, (x, y), strict=True):
                    columns = {
                        f"{stage}_{clock}_ms": row[stage][clock + "_ns"] / 1e6
                        for stage in ("read", "scout", "detector")
                        for clock in ("cpu", "wall")
                    }
                    timing.append(
                        dict(
                            arch=arch,
                            edge=edge,
                            mode=mode,
                            input=entry["file"],
                            kind=entry["kind"],
                            warm=x["repeat"] > 0 or x["index"] > 0,
                            repeat=x["repeat"],
                            index=x["index"],
                            **columns,
                            combined_cpu_ms=columns["scout_cpu_ms"] + columns["detector_cpu_ms"],
                            combined_wall_ms=columns["scout_wall_ms"] + columns["detector_wall_ms"],
                        )
                    )
    return outcomes, timing


def summarize(outcomes, timing, measurements):
    result = {arch: {mode: rates(timing, mode, arch) for mode in MODES} for arch in ARCHES}
    process = {
        m["arch"]: {
            edge: {
                mode: {
                    k: payload[k]
                    for k in ("process_wall_s", "process_cpu_s", "max_process_rss_kib", "setup")
                }
                for mode, payload in arms.items()
            }
            for edge, arms in m["results"].items()
        }
        for m in measurements
    }
    lanes = [x for record in outcomes for x in record["parity"]["lanes"]]
    return dict(
        stats=result,
        process=process,
        measured_mode_windows=len(outcomes),
        full_scientific_digest_matches=sum(d["parity"]["scientific_bytes_agree"] for d in outcomes),
        recorded_host_exact=sum(
            d["host_matches_published_recorded_probes"] is True for d in outcomes
        ),
        recorded_host_attempts=sum(d["kind"] == "recorded" for d in outcomes),
        full_rank_matches=sum(d["parity"]["full_ranks_agree"] for d in outcomes),
        added_epochs_matches=sum(d["parity"]["added_epochs_agree"] for d in outcomes),
        raw_rank_matches=sum(d["ordered_integer_keys"] for d in lanes),
        gate_matches=sum(d["ordered_fractional_gates"] for d in lanes),
        receiver_lane_compares=len(lanes),
        max_cfo_difference_hz=max(d["max_cfo_difference_hz"] for d in lanes),
        max_epoch_difference_samples=max(d["max_fractional_difference_samples"] for d in lanes),
    )


def rates(timing, mode, arch):
    selected = [
        r for r in timing if (r["arch"], r["mode"]) == (arch, mode) and r["kind"] == "recorded"
    ]
    calls = [r for r in selected if r["warm"]]
    fields = (
        "scout_cpu_ms",
        "detector_cpu_ms",
        "combined_cpu_ms",
        "combined_wall_ms",
        "read_wall_ms",
    )
    return dict(
        all_calls=len(selected),
        warm_calls=len(calls),
        within_20ms=sum(r["combined_wall_ms"] <= 20 for r in selected),
        medians={key: median(v[key] for v in calls) for key in fields},
        first=[
            {k: v[k] for k in ("edge", "combined_cpu_ms", "combined_wall_ms")}
            for v in selected
            if not v["warm"]
        ],
    )


def stage_figure(summary):
    import matplotlib.pyplot as plt

    axis = [0, 1]
    fig, panels = plt.subplots(1, 2, layout="constrained", figsize=(8.6, 3.7), sharex=True)
    for ax, arch, title in zip(panels, ARCHES, ("Native x86 host", "Cortex-A53 QEMU"), strict=True):
        rows = [summary["stats"][arch][m]["medians"] for m in MODES]
        values = [r["combined_cpu_ms"] for r in rows]
        walls = [r["combined_wall_ms"] for r in rows]
        ax.bar(axis, values, color=("#536b83", "#128172"), width=0.58)
        ax.scatter(axis, walls, color="#14202d", marker="_", s=320, label="Median wall")
        ax.axhline(20, color="#a43b40", linestyle="--", label="20 ms visit")
        ax.set(
            title=title,
            ylabel="Warm dual-RX detector time (ms)",
            ylim=(0, max(max(walls), 20) * 1.32),
        )
        ax.set_xticks(axis, ["Stock", "Fifth center"])
        ax.set_axisbelow(True)
        ax.grid(axis="y", alpha=0.22)
        ax.legend(loc="upper left", fontsize=8, frameon=False)
    fig.suptitle("Chronological saved-IQ benchmark · detector stage")
    fig.savefig(REPORT / "stage.png", dpi=180)
    fig.savefig(REPORT / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    save_json(
        REPORT / "stage-figure.json",
        dict(
            version=1,
            id="arm64-detector-saved-iq",
            title="AArch64 warm detector replay",
            boundary="Packed dual CI16 to native GLRT rows on a persistent context",
            sample="Two six-visit recorded sequences, two chronological passes per mode",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
            seal="qualification-lock.json",
            note="Emulated Cortex-A53 clocks are from the x86 host running QEMU.",
        ),
    )


def relocation(work, arm):
    stdout = work / "relocated-command.jsonl"
    stderr = work / "relocated-command.stderr"
    streams = {}
    edge = mode = None
    for row in map(json.loads, stdout.read_bytes().splitlines()):
        if row["kind"] == "stream":
            edge, mode = row["edge"], row["mode"]
            if (edge, mode) in streams:
                raise ValueError("one-command replay duplicated a stream")
            streams[(edge, mode)] = []
        elif row["kind"] == "setup":
            if row["mode"] != mode:
                raise ValueError("one-command replay misbound setup mode")
        elif row["kind"] == "visit":
            streams[(edge, mode)].append(row)
    if set(streams) != {(edge, mode) for edge in EDGES for mode in MODES}:
        raise ValueError("one-command replay omitted an A/B stream")
    for (edge, mode), rows in streams.items():
        actual = arm["results"][edge][mode]["visits"]
        for a, b in zip(rows, actual, strict=True):
            if (a["repeat"], a["index"], evaluation.scientific(a)) != (
                b["repeat"],
                b["index"],
                evaluation.scientific(b),
            ):
                raise ValueError("relocated command produced different scientific packets")
    save_json(
        REPORT / "relocated-command.json",
        dict(
            run="./benchmark qemu",
            launched_from="/var/tmp",
            used_extracted_capsule=True,
            packet_exact=True,
            paired_calls=sum(map(len, streams.values())),
            verified_checksum_lines=stderr.read_text().splitlines(),
            stdout_sha256=_sha(stdout),
            stderr_sha256=_sha(stderr),
        ),
    )
    write(REPORT / "relocated-command.jsonl.gz", gzip.compress(stdout.read_bytes(), mtime=0))


def publish(work):
    check_local_access()
    capsule = work / "relocated-capsule"
    corpus = evaluation.read(capsule / "fixtures.json")
    for table in (corpus, *(evaluation.read(work / f"build-{a}.json") for a in ARCHES)):
        for name, digest in table["sources"].items():
            check(ROOT / name, digest)
    for name, digest in evaluation.read(work / "build-arm64.json")[
        "detector_source_manifest"
    ].items():
        check(SOURCE / name, digest)
    measures = [evaluation.read(work / f"measurement-{a}.json") for a in ARCHES]
    if [m["affinity"] for m in measures] != [[0], [0]]:
        raise ValueError("host comparison and emulator must use the same CPU")
    data, timing = compare(work, corpus, *measures)
    summary = summarize(data, timing, measures)
    relocation(work, measures[1])
    save_json(REPORT / "summary.json", summary)
    save_json(REPORT / "parity.json", data)
    write(REPORT / "native-rows.json.gz", gzip.compress(encoded(measures), mtime=0))
    csv_file(REPORT / "stage.csv", timing)
    stage_figure(summary)
    for p in (capsule / "fixtures.json", *(work / f"build-{a}.json" for a in ARCHES)):
        write(REPORT / p.name, p.read_bytes())
    files = (
        "PROTOCOL.md",
        "arm64-detector-capsule.tar.gz",
        "board-access.json",
        "native-rows.json.gz",
        "fixtures.json",
        "summary.json",
        "parity.json",
        "build-arm64.json",
        "build-host.json",
        "stage.csv",
        "stage.png",
        "stage.pdf",
        "stage-figure.json",
        "relocated-command.json",
        "relocated-command.jsonl.gz",
    )
    save_json(
        REPORT / "qualification-lock.json",
        dict(
            cases=list(evaluation.CASES),
            files={n: _sha(REPORT / n) for n in files},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=local_output, default=WORK)
    publish(parser.parse_args().work)
