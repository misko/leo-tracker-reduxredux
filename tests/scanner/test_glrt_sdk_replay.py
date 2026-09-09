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
from tools.qualify_scanner_glrt_sdk import POSITIVE_PROFILE, _decision, build, verify


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
            "-DLEO_PRESENCE_ENERGY_SUPPORT=1",
            "-DLEO_PRESENCE_ENERGY_SYMBOL_SUPPORT=1",
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


@pytest.fixture(scope="module")
def positive_runs(workload):
    parent, worker, templates, pack, manifest = workload
    before = {p: digest(p) for p in (parent, worker, templates, pack)}
    outputs = {}
    for delay, jitter in ((0, 0), (2, 0), (0, 40), (2, 40)):
        process = subprocess.run(
            [
                str(parent),
                str(worker),
                str(templates),
                str(pack),
                "968",
                str(delay),
                str(jitter),
                "1",
                "12" * 32,
                "34" * 32,
                POSITIVE_PROFILE,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert process.returncode == 0, process.stderr
        assert not process.stderr
        outputs[delay, jitter] = process.stdout
    assert before == {p: digest(p) for p in before}
    return manifest, outputs


@pytest.mark.parametrize("delay,jitter", [(0, 0), (2, 0), (0, 40), (2, 40)])
def test_positive_feedback_and_wire_results_have_independent_complete_inventories(
    positive_runs, delay, jitter
):
    manifest, outputs = positive_runs
    checked = verify(
        outputs[delay, jitter],
        manifest,
        968,
        delay_blocks=delay,
        jitter_ms=jitter,
        enabled=True,
        positive_feedback=True,
    )
    assert checked["results"] == checked["observations"] == checked["jobs"] == 8
    assert checked["observation_outcomes"]["detected"] > 0
    assert sum(checked["observation_outcomes"].values()) == 8
    assert checked["observation_outcomes"]["detected"] < 8
    assert checked["ready_callback_to_observation_ms"]["max"] >= 0
    assert "no scheduler thread" in checked["limitations"]
    assert "not original block arrivals" in checked["limitations"]
    with pytest.raises(ValueError, match="protocol differs"):
        verify(
            outputs[delay, jitter],
            manifest,
            968,
            delay_blocks=delay,
            jitter_ms=jitter,
            enabled=True,
        )


@pytest.mark.parametrize(
    "kind,key,value",
    [
        ("protocol", "minimum_exact_score", 0.1),
        ("protocol", "minimum_margin", 0.01),
        ("protocol", "adaptive_scheduling", True),
        ("protocol", "positive_profile", "unreviewed"),
        ("observation", "session", "72"),
        ("observation", "generation", "10"),
        ("observation", "visit", "01"),
        ("observation", "start", "9007199254740992"),
        ("observation", "end", "9007199254740992"),
        ("observation", "rate_hz", 1),
        ("observation", "rx", 0),
        ("observation", "target", 7),
        ("observation", "healthy", False),
        ("observation", "outcome", 3),
        ("observation", "elapsed_ms", 0),
        ("observation", "phase", "scheduler-thread"),
        ("observation", "block", 0),
        ("block", "observation_wall_ms", 1e6),
        ("block", "observation_cpu_ms", -1),
        ("observation-final", "count", 7),
        ("observation-final", "elapsed_ms", 0),
        ("summary", "observations", 7),
    ],
)
def test_feedback_verifier_rejects_changed_identity_policy_and_timing(
    positive_runs, kind, key, value
):
    manifest, outputs = positive_runs
    rows = [json.loads(line) for line in outputs[2, 40].splitlines()]
    next(row for row in rows if row["kind"] == kind)[key] = value
    with pytest.raises(ValueError):
        verify(
            "\n".join(map(json.dumps, rows)),
            manifest,
            968,
            delay_blocks=2,
            jitter_ms=40,
            enabled=True,
            positive_feedback=True,
        )


@pytest.mark.parametrize("mutation", ["drop", "duplicate", "reorder", "no-final", "wrong-outcome"])
def test_feedback_verifier_requires_exactly_once_ordered_observations(positive_runs, mutation):
    manifest, outputs = positive_runs
    rows = [json.loads(line) for line in outputs[2, 40].splitlines()]
    indices = [i for i, r in enumerate(rows) if r["kind"] == "observation"]
    first, second = indices[:2]
    if mutation == "drop":
        del rows[first]
    elif mutation == "duplicate":
        rows.insert(first, rows[first])
    elif mutation == "reorder":
        rows[first], rows[second] = rows[second], rows[first]
    elif mutation == "no-final":
        rows = [r for r in rows if r["kind"] != "observation-final"]
    else:
        rows[first]["outcome"] = (rows[first]["outcome"] + 1) % 3
    with pytest.raises(ValueError):
        verify(
            "\n".join(map(json.dumps, rows)),
            manifest,
            968,
            delay_blocks=2,
            jitter_ms=40,
            enabled=True,
            positive_feedback=True,
        )


def test_expected_positive_choice_prioritizes_passing_candidate_over_larger_rejected_margin():
    passing = dict(fractional_complete=1, exact_score=0.18, margin=0.03)
    rejected = dict(fractional_complete=1, exact_score=0.17, margin=0.10)
    source = dict(expected=dict(candidates=[rejected, passing]))
    assert _decision(source, True) == (passing, "starlink", "complete", 1)
    assert _decision(source, False) == (rejected, "unavailable", "unqualified_classifier", None)


@pytest.mark.parametrize("incomplete", [False, True])
def test_expected_completed_miss_and_incomplete_are_never_wire_absence(incomplete):
    candidates = [dict(fractional_complete=0)] if incomplete else []
    assert _decision(dict(expected=dict(candidates=candidates)), True) == (
        None,
        "unavailable",
        "incomplete_search",
        0 if incomplete else 2,
    )


@pytest.mark.parametrize("enabled,profile", [("0", POSITIVE_PROFILE), ("1", "unreviewed")])
def test_invalid_feedback_opt_in_rejects_before_opening_payload(artifacts, enabled, profile):
    _, parent, _, _ = artifacts
    result = subprocess.run(
        [
            str(parent),
            "/absent-worker",
            "/absent-templates",
            "/absent-pack",
            "968",
            "0",
            "0",
            enabled,
            "12" * 32,
            "34" * 32,
            profile,
        ],
        capture_output=True,
        text=True,
        timeout=2,
    )
    assert result.returncode == 2 and not result.stdout
    with pytest.raises(ValueError, match="unreviewed replay"):
        verify("", {}, 968, delay_blocks=0, jitter_ms=0, enabled=False, positive_feedback=True)


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
    assert "-Wl,-rpath,$ORIGIN" in receipt["command"]
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


def test_packaged_sdk_and_release_identities_are_verified_without_rebuilding(workload, tmp_path):
    original, worker, templates, pack, manifest = workload
    sdk = original.parent / "libleo-scanner-glrt.so"
    before = digest(sdk)
    parent = build(tmp_path / "consumer", sdk_library=sdk, runtime_rpath=sdk.parent)
    assert not (parent.parent / sdk.name).exists()
    assert digest(sdk) == before
    record = json.loads(parent.with_name(parent.name + ".build.json").read_text())
    assert record["dependencies_sha256"] == {str(sdk.resolve()): before}
    algorithm, configuration = "ab" * 32, "cd" * 32
    process = subprocess.run(
        [
            str(parent),
            str(worker),
            str(templates),
            str(pack),
            "968",
            "2",
            "40",
            "1",
            algorithm,
            configuration,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert process.returncode == 0, process.stderr
    checked = verify(
        process.stdout,
        manifest,
        968,
        delay_blocks=2,
        jitter_ms=40,
        enabled=True,
        algorithm_sha256=algorithm,
        configuration_sha256=configuration,
    )
    assert checked["verified"] and checked["results"] == 8
    assert checked["algorithm_sha256"] == algorithm
    assert checked["configuration_sha256"] == configuration
    with pytest.raises(ValueError, match="metadata/frame"):
        verify(process.stdout, manifest, 968, delay_blocks=2, jitter_ms=40, enabled=True)


@pytest.mark.parametrize(
    "identities",
    [
        ("ab" * 32,),
        ("0" * 64, "cd" * 32),
        ("ab" * 32, "0" * 64),
        ("AB" * 32, "cd" * 32),
        ("ab" * 32, "bad"),
        ("ab" * 32 + "\n", "cd" * 32),
    ],
)
def test_invalid_release_ids_reject_before_any_payload_is_opened(artifacts, identities):
    _, parent, _, _ = artifacts
    result = subprocess.run(
        [
            str(parent),
            "/missing-worker",
            "/missing-template",
            "/missing-pack",
            "968",
            "0",
            "0",
            "1",
            *identities,
        ],
        capture_output=True,
        text=True,
        timeout=2,
    )
    assert result.returncode == 2 and not result.stdout


@pytest.mark.parametrize("value", [None, "0" * 64, "AB" * 32, "ab" * 32 + "\n", "bad"])
def test_verifier_requires_independently_supplied_valid_release_identity(value):
    with pytest.raises(ValueError, match="expected replay identity"):
        verify("", {}, 968, delay_blocks=0, jitter_ms=0, enabled=True, algorithm_sha256=value)


@pytest.mark.parametrize(
    "path", [Path("relative"), Path("/tmp/a,other"), Path("/tmp/a:other"), Path("/tmp/a/../other")]
)
def test_unsafe_runtime_search_path_rejected_without_building(tmp_path, path):
    output = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="runtime RPATH"):
        build(output, runtime_rpath=path)
    assert not output.exists()
