"""Bounded complete metadata audit using public input ports."""

import gzip
import hashlib
import inspect
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PILOT = HERE.parent / "2026_09_29_opportunity_coverage"
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"
sys.path.insert(0, str(PILOT))
from audit import summarize  # noqa: E402


def read(p):
    return json.loads(p.read_text())


def save(p, data):
    with p.open("x") as f:
        json.dump(data, f, indent=2, allow_nan=False)


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verify():
    for n, h in read(HERE / "input-seal.json")["sha256"].items():
        assert digest(ROOT / n) == h, n


def prepare():
    bindings = {}

    def bind(p):
        bindings[str(p.relative_to(ROOT))] = digest(p)
        return read(p)

    donors = bind(HERE.parent / "2026_09_29_donor_weights/plan.json")
    targets = set(donors["target_session_ids"])
    donor_ids = {i["session_id"] for u in donors["units"] for i in u["group"]["inputs"]}
    assert len(targets) == 72 and len(donor_ids) == 186 and not targets & donor_ids
    reused = {bind(PILOT / (ds + ".json"))["session_id"]: ds for ds in ("DS7", "DS8", "DS9")}
    records = []
    for ds, folder in (
        ("DS7", "2026_09_27_ds7_post_ds6"),
        ("DS8", "2026_09_28_ds8_post_ds7"),
        ("DS9", "2026_09_28_ds9_post_ds8"),
    ):
        manifest = bind(HERE.parent / folder / "manifest.json")
        for c in sorted(
            manifest["captures"], key=lambda c: (c["capture_start_utc_ns"], c["session_id"])
        ):
            sid = c["session_id"]
            assert sid in targets | donor_ids
            records.append(
                dict(
                    dataset=ds,
                    session_id=sid,
                    manifest_sha256=c["manifest_sha256"],
                    role="target" if sid in targets else "donor",
                    pilot=reused.get(sid),
                )
            )
    assert len(records) == len({r["session_id"] for r in records}) == 258
    fresh = [r for r in records if not r["pilot"]]
    save(
        HERE / "plan.json",
        dict(records=records, batches=[fresh[i : i + 32] for i in range(0, len(fresh), 32)]),
    )
    for name in ("audit.py", "test_audit.py", "scanner_tracking_source.py.txt"):
        p = PILOT / name
        bindings[str(p.relative_to(ROOT))] = digest(p)
    with (HERE / "tests.log").open("x") as f:
        r = subprocess.run(
            [
                str(ROOT / ".venv/bin/python"),
                "-m",
                "unittest",
                "discover",
                "-s",
                str(PILOT),
                "-p",
                "test_audit.py",
                "-v",
            ],
            stdout=f,
            stderr=subprocess.STDOUT,
        )
    assert r.returncode == 0
    (HERE / "records").mkdir()
    for p in HERE.iterdir():
        if p.is_file():
            bindings[str(p.relative_to(ROOT))] = digest(p)
    save(HERE / "input-seal.json", dict(sha256=bindings))


def child(index):
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    verify()
    assert (
        Path(inspect.getfile(ScannerTrackingInputStore)).read_bytes()
        == (PILOT / "scanner_tracking_source.py.txt").read_bytes()
    )
    store = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    capture = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    for row in read(HERE / "plan.json")["batches"][index]:
        raw = store.load(row["session_id"])
        published = capture.inspect(row["session_id"])
        assert raw.input_manifest_sha256 == published.manifest_sha256 == row["manifest_sha256"]
        data = dict(
            **row,
            rate=raw.sample_rate_hz,
            probe_ms=raw.probe_ms,
            qualified=raw.qualified,
            timing_qualified=raw.timing.qualified if raw.timing else False,
            analysis_manifest_sha256=raw.analysis_manifest_sha256,
            visits=[
                dict(
                    visit_index=e.visit_index,
                    start=e.valid_start_counter,
                    end=e.valid_end_counter_exclusive,
                    rf_hz=float(e.target.rf_center_hz - e.actual_if_offset_hz),
                )
                for e in published.manifest.receipt.events
            ],
            probes=[
                dict(
                    visit_index=p.visit_index,
                    receiver=p.receiver_id,
                    probe_index=p.probe_index,
                    start_ms=p.probe_start_ms,
                    valid_start_counter=p.valid_start_counter,
                    rf_hz=p.actual_rf_hz,
                    candidates=len(p.candidates),
                    passing=sum(c.passed_fractional_margin_gate for c in p.candidates),
                )
                for p in raw.probes
            ],
        )
        summary = summarize(data)
        name = HERE / "records" / row["session_id"]
        with name.with_suffix(".json.gz").open("xb") as f:
            f.write(
                gzip.compress(
                    json.dumps(data, separators=(",", ":"), allow_nan=False).encode(), mtime=0
                )
            )
        save(name.with_suffix(".summary.json"), summary)
        print(row["dataset"], row["session_id"], len(data["probes"]), flush=True)


def launch():
    verify()
    started = time.monotonic()
    for i, _ in enumerate(read(HERE / "plan.json")["batches"]):
        assert time.monotonic() - started < 720
        command = [
            "sudo",
            "-n",
            "/usr/bin/time",
            "-v",
            "-o",
            str(HERE / f"batch-{i}-resources.txt"),
            "timeout",
            "--kill-after=5s",
            "180s",
            "prlimit",
            "--as=4294967296",
            "nice",
            "-n",
            "19",
            "env",
            "OPENBLAS_NUM_THREADS=1",
            PYTHON,
            str(HERE / "study.py"),
            "child",
            str(i),
        ]
        save(HERE / f"batch-{i}-launch.json", dict(command=command))
        with (HERE / f"batch-{i}-terminal.log").open("x") as f:
            r = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT)
        save(HERE / f"batch-{i}-exit.json", dict(exit_code=r.returncode))
        print("Batch", i, "exit", r.returncode, flush=True)
        assert r.returncode == 0
    verify()
    save(HERE / "exit.json", dict(exit_code=0, wall_seconds=time.monotonic() - started))


if __name__ == "__main__":
    if sys.argv[1] == "child":
        child(int(sys.argv[2]))
    else:
        {"prepare": prepare, "launch": launch}[sys.argv[1]]()
