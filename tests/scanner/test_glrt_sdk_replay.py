"""Real SDK/worker, modeled block timing, numerical binding and hostile receipts."""

import copy
import json
import struct
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tools.native_presence import ROOT, build_dwell_presence, build_worker, write_templates
from tools.presence_dwell import NativeDwell, unpack
from tools.qualify_native_presence import digest
from tools.qualify_presence_dwell_controls import generate
from tools.qualify_presence_dwell_worker import FIELDS
from tools.qualify_scanner_glrt_sdk import build, verify


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory):
    root = tmp_path_factory.mktemp("glrt-sdk-replay")
    config = json.loads(
        (ROOT / "config/analysis/arm-presence-native-tone-ci16-v1.json").read_text()
    )
    flags = (
        tuple(config["common_flags"])
        + tuple(f"-DLEO_PRESENCE_{k}={v}" for k, v in config["variants"][0]["defines"].items())
        + (
            "-DLEO_PRESENCE_DIFFERENTIAL_CI16=1",
            "-DLEO_PRESENCE_RANK_HYBRID_PROJECTION=1",
            "-DLEO_PRESENCE_GLRT_SYMBOL_DIVERSITY=1",
            "-DLEO_PRESENCE_RANK_AMPLITUDE_WEIGHTED=1",
            "-DLEO_PRESENCE_BOUNDED_MAGNITUDE=1",
            "-DLEO_PRESENCE_CONDITIONED_BLOCK_ROTATION=1",
        )
    )
    parent = build(root / "parent")
    worker = build_worker(root / "worker", cflags=flags)
    worker.chmod(0o755)
    library = build_dwell_presence(root / "reference.so", cflags=flags)
    return root, parent, worker, library


@pytest.fixture(scope="module", params=[2500000, 5000000])
def workload(artifacts, request):
    root, parent, worker, library = artifacts
    rate = request.param
    templates, pack = root / f"{rate}.templates", root / f"{rate}.pack"
    write_templates(templates, rate)
    templates.chmod(0o600)
    records = []
    with pack.open("xb") as stream:
        stream.write(struct.pack("<4sII", b"LDP1", rate, 4))
        for i, (edge, kind) in enumerate(
            (
                ("lower", "pilot"),
                ("upper", "pilot_plus_tone"),
                ("upper", "white_noise"),
                ("lower", "two_tones"),
            )
        ):
            iq, _ = generate(rate, edge, 884 + i, kind, i if "pilot" in kind else None)
            assert iq.dtype == np.dtype("int16")
            counter = 2**53 + 987 + i * rate
            with NativeDwell(library, rate, edge, 512) as native:
                result = unpack(native.run(iq, maximum=1, seeded=False))
            confirmation = result["confirmations"][0]
            records.append(
                dict(
                    counter=str(counter),
                    visit=100 + i,
                    channel=i + 1,
                    edge=edge,
                    rx=1,
                    expected=dict(
                        candidates=[
                            {k: c[k] for k in FIELDS}
                            for c in confirmation["candidates"][: confirmation["candidate_count"]]
                        ],
                        rank=result["rank"],
                    ),
                )
            )
            stream.write(struct.pack("<QQII", counter, 100 + i, int(edge == "upper"), i + 1))
            stream.write(iq.astype("<i2", copy=False).tobytes())
    return parent, worker, templates, pack, dict(rate_hz=rate, records=records)


@pytest.fixture(scope="module")
def runs(workload):
    parent, worker, templates, pack, manifest = workload
    before = {p: digest(p) for p in (parent, worker, templates, pack)}
    outputs = {}
    for enabled, delay, jitter in (
        (True, 0, 0),
        (True, 2, 0),
        (True, 0, 40),
        (True, 2, 40),
        (False, 2, 40),
    ):
        process = subprocess.run(
            [
                str(parent),
                str(worker),
                str(templates),
                str(pack),
                "968",
                str(delay),
                str(jitter),
                str(int(enabled)),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert process.returncode == 0, process.stderr
        assert not process.stderr
        outputs[enabled, delay, jitter] = process.stdout
    assert before == {p: digest(p) for p in before}
    return manifest, outputs


@pytest.mark.parametrize(
    "enabled,delay,jitter",
    [(True, 0, 0), (True, 2, 0), (True, 0, 40), (True, 2, 40), (False, 2, 40)],
)
def test_real_sdk_retains_complete_fractional_results_without_changing_iq(
    runs, enabled, delay, jitter
):
    manifest, outputs = runs
    result = verify(
        outputs[enabled, delay, jitter],
        manifest,
        968,
        delay_blocks=delay,
        jitter_ms=jitter,
        enabled=enabled,
    )
    assert result["jobs"] == 8 and result["results"] == (8 if enabled else 0)
    assert result["verified"] and "not original block arrivals" in result["limitations"]
    assert result["callback_wall_ms"]["max"] >= 0


@pytest.mark.parametrize(
    "kind,key,value",
    [
        ("protocol", "original_arrivals", True),
        ("protocol", "live_rf", True),
        ("protocol", "base", "9007199254741210"),
        ("protocol", "jitter_ms", 0),
        ("summary", "jobs", 7),
        ("block", "samples", 100),
        ("block", "arrival_ms", 0),
        ("block", "callback_wall_ms", -1),
        ("visit", "source_counter", "9007199254740992"),
        ("visit", "block", 0),
    ],
)
def test_verifier_rejects_changed_geometry_timing_and_provenance(runs, kind, key, value):
    manifest, outputs = runs
    rows = [json.loads(line) for line in outputs[True, 2, 40].splitlines()]
    next(row for row in rows if row["kind"] == kind)[key] = value
    with pytest.raises(ValueError):
        verify(
            "\n".join(map(json.dumps, rows)),
            manifest,
            968,
            delay_blocks=2,
            jitter_ms=40,
            enabled=True,
        )


def test_verifier_rejects_missing_final_or_changed_candidate(runs):
    manifest, outputs = runs
    rows = [json.loads(line) for line in outputs[True, 0, 0].splitlines()]
    del rows[-2]  # Final metadata envelope, not the terminal execution receipt.
    with pytest.raises(ValueError):
        verify(
            "\n".join(map(json.dumps, rows)),
            manifest,
            968,
            delay_blocks=0,
            jitter_ms=0,
            enabled=True,
        )
    changed = copy.deepcopy(manifest)
    for record in changed["records"]:
        for candidate in record["expected"]["candidates"]:
            if candidate["fractional_complete"]:
                candidate["fractional_offset_samples"] += 0.1
    with pytest.raises(ValueError, match="numerical mismatch"):
        verify(outputs[True, 0, 0], changed, 968, delay_blocks=0, jitter_ms=0, enabled=True)


def test_sdk_and_parent_build_receipts_attest_actual_artifacts(artifacts):
    _, parent, _, _ = artifacts
    receipt = json.loads(parent.with_name(parent.name + ".build.json").read_text())
    assert receipt["binary_sha256"] == digest(parent)
    assert all(digest(ROOT / p) == sha for p, sha in receipt["sources_sha256"].items())
    assert all(digest(Path(p)) == sha for p, sha in receipt["dependencies_sha256"].items())


@pytest.mark.parametrize(
    "duration,delay,jitter,enabled",
    [
        ("241", "0", "0", "1"),
        ("300001", "0", "0", "1"),
        ("968", "3", "0", "1"),
        ("968", "0", "41", "1"),
        ("968", "0", "0", "2"),
    ],
)
def test_unreviewed_cli_rejects_before_loading_any_payload(
    artifacts, duration, delay, jitter, enabled
):
    _, parent, _, _ = artifacts
    result = subprocess.run(
        [
            str(parent),
            "/absent-worker",
            "/absent-templates",
            "/absent-pack",
            duration,
            delay,
            jitter,
            enabled,
        ],
        capture_output=True,
        text=True,
        timeout=2,
    )
    assert result.returncode == 2 and not result.stdout
