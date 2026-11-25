"""Exercise the two-case raw wrapper without solving or opening waveform files."""

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def experiment(monkeypatch):
    here = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
    monkeypatch.syspath_prepend(str(here))
    import combined_small_panel
    import combined_small_panel_entry

    return combined_small_panel, combined_small_panel_entry


def test_source_delta_allows_only_the_qualified_slots(experiment):
    panel, _ = experiment
    root = "reports/ALGO08/v3/"
    batch = root + "integrated_original_batch.py"
    receiver = root + "receiver.py"
    new = {root + "prefetch_snapshots.py": "slots", root + "legacy_snapshot_reuse.py": "readv"}
    control = dict(native="unpadded", sources={batch: "old", receiver: "stable"})
    trial = dict(native="unpadded", sources={batch: "slot opt-in", receiver: "stable", **new})
    assert panel.checked_source_delta(control, trial) == {batch, *new}
    trial["sources"][receiver] = "changed"
    with pytest.raises(ValueError, match="outside the private prefetch port"):
        panel.checked_source_delta(control, trial)


def test_wraps_actual_handoff_and_ordinary_grid_once(experiment, monkeypatch):
    _, entry = experiment
    seen = []
    native = dict(receiver_identity="signed")

    @contextmanager
    def masked_graph(_app, _tracks, _feature, _config, document, audit, *, stock_ports):
        assert document is native and stock_ports == ["released"]
        audit["test_bound"] = True
        seen.append("graph opened")
        yield
        seen.append("graph closed")

    @contextmanager
    def checked_grid(_file, pin, audit, *, proof):
        assert pin == entry.GRID_PIN and proof is True
        audit["certified_stock_refusal"] += 1
        seen.append("grid opened")
        yield
        seen.append("grid closed")

    boot = SimpleNamespace(now=lambda: (), clock=lambda _: dict(cpu_s=0))
    ports = SimpleNamespace(
        bind=masked_graph,
        app=None,
        tracks=None,
        feature=None,
        config=None,
        stock=["released"],
        canonical=lambda packet: packet["receiver_identity"],
        grid=SimpleNamespace(STOCK_POSTERIOR_SHA256="stock", profiled_grid=checked_grid),
    )
    monkeypatch.setattr(entry, "load_ports", lambda _: ports)
    audit = dict(publication_calls=0, cfo={}, grid={})

    def ordinary(*_args, **_options):
        seen.append("ordinary publication")
        return "ordinary result"

    publish = entry.publication(boot, ordinary, audit)
    handoff = SimpleNamespace(native=native)
    specification = dict(posterior_grid_handoff=dict(sha256="stock"))
    assert publish(None, None, specification, handoff) == "ordinary result"
    assert seen == [
        "graph opened",
        "grid opened",
        "ordinary publication",
        "grid closed",
        "graph closed",
    ]
    assert audit["handoff_sha256"] == "signed"
    assert audit["grid"]["certified_stock_refusal"] == 1
    with pytest.raises(ValueError, match="one original authenticated handoff"):
        publish(None, None, specification, handoff)


def test_withhold_can_skip_positive_ports(experiment, tmp_path):
    panel, entry = experiment
    recipe = dict(rule=entry.SCHEDULE, streams=["edge", "channel", "actual_rf_hz"])
    panel.write(
        tmp_path / "unified-short-bootstrap.json",
        dict(
            native_sha256="unchanged native",
            held_anchor_route=dict(receiver_recipe=recipe),
        ),
    )
    audit = dict(publication_calls=0, cfo={}, grid={})
    entry.finish(tmp_path, dict(decision="withheld"), audit, panel)
    witness = json.loads((tmp_path / "combined-small-panel-witness.json").read_text())
    assert (
        witness["native_sha256"] == "unchanged native"
        and not witness["cfo"]
        and not witness["grid"]
    )
    with pytest.raises(ValueError, match="expected route"):
        entry.finish(tmp_path, dict(decision="complete"), audit, panel)


def test_mincore_keeps_a_read_only_sample_on_its_existing_pages(experiment, tmp_path):
    import combined_small_panel_residency as resident

    file = tmp_path / "sample"
    file.write_bytes(b"x" * (resident.PAGE + 17))
    before = file.read_bytes()
    with resident.read_only_map(file) as (address, length):
        assert resident.missing(address, length) == []
    assert file.read_bytes() == before


def test_each_transaction_has_its_own_order_and_returns_prior_exit(experiment, tmp_path):
    panel, _ = experiment
    ready = dict(cases={"DS30-0016": dict(residency=dict(nonresident=["missing"]))})
    case = "DS30-0107"
    with pytest.raises(ValueError, match="within-case order"):
        panel.authorized_order(tmp_path, ready, case, "charted")
    assert panel.authorized_order(tmp_path, ready, case, "trial") == 0
    first = tmp_path / case / "trial"
    first.mkdir(parents=True)
    panel.write(first / "process.json", dict(finished_unix_ns=42))
    panel.write(first / "verified.json", {})
    assert panel.authorized_order(tmp_path, ready, case, "charted") == 42
    with pytest.raises(ValueError, match="fresh transaction"):
        panel.authorized_order(tmp_path, ready, case, "trial")


def test_short_gap_requires_exact_unstarted_successor(experiment):
    panel, _ = experiment
    common = dict(
        case="DS30-0218",
        admission_state="deferred_storage_busy",
        verified_pair=False,
        raw_identity_sha256="sha256:9b08c27dfd179fcfa112d19bc6c4b1f10b3efd3f948005a8a298dc9b927866c9",
    )
    stock = dict(common, algorithm="installed", outcome="complete", acquisition_verified=True)
    successor = dict(
        common,
        algorithm="successor",
        outcome="pending",
        acquisition_verified=False,
        attempt=None,
        child_started_unix_ns=None,
        attempt_result_sha256=None,
    )
    assert panel.official_0218_is_pending([stock, successor])
    assert not panel.official_0218_is_pending([stock, dict(successor, child_started_unix_ns=42)])
    assert not panel.official_0218_is_pending([stock, dict(successor, raw_identity_sha256="wrong")])


def test_native_meter_accounts_for_the_command_it_reaps(experiment):
    import sys

    from combined_small_panel_meter import measure

    receipt = measure([sys.executable, "-IB", "-c", "sum(range(60000))"])
    assert receipt["exit_code"] == 0 and receipt["minor_faults"] > 0
    assert receipt["cpu_s"] == receipt["user_cpu_s"] + receipt["system_cpu_s"]
    assert receipt["wall_s"] > 0 and receipt["cpu_s"] > 0


def test_natural_scope_counts_only_bounded_original_pages(experiment):
    panel, _ = experiment
    root = Path("/dev/shm/known-staged-source")
    member = str(root / "segment" / "iq-000001.ci16.zst")
    state = dict(nonresident=[dict(file=member, size=25_003, res=20_480)])
    assert panel.bounded_natural_source(state, root, page=4096)["nonresident_page_bytes"] == 8192
    with pytest.raises(ValueError, match="extent bound"):
        panel.bounded_natural_source(
            dict(nonresident=[dict(file=member, size=8_388_609, res=0)]), root, page=4096
        )
    with pytest.raises(ValueError, match="compressed members"):
        panel.bounded_natural_source(
            dict(nonresident=[dict(file=str(root / "manifest.json"), size=1, res=0)]),
            root,
            page=4096,
        )
