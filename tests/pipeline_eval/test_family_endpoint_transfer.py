from contextlib import contextmanager
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

import family_endpoint_transfer as transfer


@pytest.mark.parametrize("mode", ["combined", "stock"])
def test_only_combined_installs_the_exact_two_outer_bindings(monkeypatch, tmp_path, mode):
    fired = []

    @contextmanager
    def isolate():
        fired.append("isolation and shared endpoint")
        yield

    @contextmanager
    def fit(witness):
        witness["entered"] = True
        fired.append("named finish")
        yield

    def publish(options):
        assert options.direct_residual_figures and options.direct_orbit_figures
        fired.append("publish")

    def fake_worker(job, selected, output, **_):
        assert selected == ("cumulative" if mode == "combined" else "stock")
        if selected == "cumulative":
            entry.publish_active(SimpleNamespace())

    entry = SimpleNamespace(publish_active=publish)
    monkeypatch.setitem(sys.modules, "unified_short_bootstrap", entry)
    monkeypatch.setitem(sys.modules, "isolated_salvage", SimpleNamespace(binding=isolate))
    monkeypatch.setitem(sys.modules, "named_survivor_fit", SimpleNamespace(binding=fit))
    monkeypatch.setattr(transfer, "worker", fake_worker)
    job = tmp_path / "request.json"
    job.write_text(json.dumps(dict(native_sha256="a"*64, issued=4219, admitted=3527)))
    target = tmp_path / mode
    target.mkdir()
    transfer.invoke(job, mode, target)
    receipt = json.loads((target/"bound-package.json").read_bytes())
    assert entry.publish_active is publish
    assert receipt["entered_fixed_final_fit"] == (mode == "combined")
    assert fired == (["isolation and shared endpoint", "named finish", "publish"] if mode == "combined" else [])


def test_staged_archive_stops_before_any_copy_if_above_cap(monkeypatch, tmp_path):
    from leo.operations.tle_archive import TleArchiveReader

    item = SimpleNamespace(path=Path("fake"), sha256="123", byte_size=transfer.CAP+1)
    monkeypatch.setattr(TleArchiveReader, "list_snapshots", lambda *_: [item])
    enrollment = dict(original_archive=dict(root=str(tmp_path), snapshots_sha256="unused"),
                      archive_bytes=item.byte_size, snapshots=1)
    with pytest.raises(ValueError, match="Bounded causal archive"):
        transfer.stage_archive(enrollment, tmp_path / "stage")
    assert not (tmp_path / "stage").exists()
