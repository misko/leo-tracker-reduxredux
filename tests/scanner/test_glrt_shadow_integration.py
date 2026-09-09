"""Explicit libiio-source integration: real queue/thread, synthetic IQ, no RF."""

import json
import os
import struct
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tests.scanner.test_glrt_sdk_replay import artifacts as artifacts
from tools.native_presence import write_templates
from tools.presence_dwell import NativeDwell, unpack
from tools.qualify_native_presence import digest
from tools.qualify_presence_dwell_controls import generate
from tools.qualify_presence_dwell_worker import FIELDS
from tools.qualify_scanner_glrt_sdk import POSITIVE_PROFILE, _decision, build
from tools.qualify_scanner_glrt_shadow import verify

pytestmark = pytest.mark.libiio_integration


@pytest.fixture(scope="module")
def threaded(artifacts):
    root, _, _, _ = artifacts
    source = os.environ.get("LEO_LIBIIO_SOURCE")
    if not source:
        pytest.fail("libiio_integration requires explicit LEO_LIBIIO_SOURCE; never opens RF")
    return build(root / "threaded", libiio_source=Path(source))


@pytest.fixture(scope="module", params=[2500000, 5000000])
def synthetic_workload(artifacts, request, tmp_path_factory):
    _, _, worker, library = artifacts
    rate = request.param
    root = tmp_path_factory.mktemp(f"shadow-workload-{rate}")
    template, pack = root / f"shadow-{rate}.templates", root / f"shadow-{rate}.pack"
    write_templates(template, rate)
    template.chmod(0o600)
    records = []
    with pack.open("xb") as output:
        output.write(struct.pack("<4sII", b"LDP1", rate, 8))
        for i in range(8):
            edge = "lower" if i < 4 else "upper"
            if 13 & (1 << i):
                iq, _ = generate(rate, edge, 92851 + i, "pilot", i % 6)
            else:
                iq = np.zeros((rate * 120 // 1000, 2), dtype=np.int16)
            with NativeDwell(library, rate, edge, 512) as native:
                result = unpack(native.run(iq, maximum=1, seeded=False))
            confirmation = result["confirmations"][0]
            record = dict(
                counter=str(2**53 + i * rate),
                visit=i,
                channel=i % 4 + 1,
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
            assert _decision(record, True)[3] == (1 if 13 & (1 << i) else 2)
            records.append(record)
            output.write(struct.pack("<QQII", int(record["counter"]), i, i // 4, i % 4 + 1))
            output.write(iq.astype("<i2", copy=False).tobytes())
    return worker, template, pack, dict(rate_hz=rate, records=records)


@pytest.mark.parametrize("jitter", [0, 40])
def test_real_threaded_feedback_produces_weighted_shadow_choices(
    threaded, synthetic_workload, jitter
):
    worker, template, pack, manifest = synthetic_workload
    before = {p: digest(p) for p in (threaded, worker, template, pack)}
    result = subprocess.run(
        [
            str(threaded),
            str(worker),
            str(template),
            str(pack),
            "9680",
            "2",
            str(jitter),
            "1",
            "12" * 32,
            "34" * 32,
            POSITIVE_PROFILE,
        ],
        capture_output=True,
        text=True,
        timeout=35,
    )
    assert result.returncode == 0 and not result.stderr, result.stderr
    checked = verify(result.stdout, manifest, 9680, jitter_ms=jitter)
    assert checked["results"] == checked["observations"] == checked["choices"] == 80
    assert checked["policy_model_matched"] and checked["proposals_differing_from_actual"] > 10
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    settled = [r for r in rows if r["kind"] == "shadow-choice" and r["visit"] >= 40]
    assert all(r["active_mask"] == 13 and r["quiet_mask"] == 242 for r in settled)
    assert before == {p: digest(p) for p in before}


def test_threaded_build_attests_actual_component_sources(threaded):
    receipt = json.loads(threaded.with_name("sdk-replay.build.json").read_text())
    assert receipt["binary_sha256"] == digest(threaded)
    sources = receipt["sources_sha256"]
    assert any(p.endswith("spf-hop-scheduler.c") for p in sources)
    assert any(p.endswith("spf-hop-adaptive-policy.c") for p in sources)
    assert "tools/scanner_glrt_shadow_replay.c" in sources
    assert "-DLEO_REPLAY_THREADED_SHADOW=1" in receipt["command"]
