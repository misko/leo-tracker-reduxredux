import importlib.util
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("remaining43_inventory", HERE / "inventory.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_latest_by_provider_is_strict_and_deterministic():
    refs = [
        SimpleNamespace(provider="a", collected_utc_ns=10, digest="sha256:a"),
        SimpleNamespace(provider="a", collected_utc_ns=20, digest="sha256:b"),
        SimpleNamespace(provider="b", collected_utc_ns=20, digest="sha256:c"),
    ]
    selected = MODULE.latest_by_provider(refs, 20)
    assert [(row.provider, row.digest) for row in selected] == [("a", "sha256:a")]
    selected = MODULE.latest_by_provider(refs, 21)
    assert [(row.provider, row.digest) for row in selected] == [
        ("a", "sha256:b"), ("b", "sha256:c")
    ]


def test_catalogue_comparison_distinguishes_bytes_epoch_and_sgp4(monkeypatch):
    old = SimpleNamespace(first_line="old1", second_line="old2")
    byte_only = SimpleNamespace(first_line="new1", second_line="new2")
    semantic = SimpleNamespace(first_line="sem1", second_line="sem2")
    fields = {
        id(old): {name: 1.0 for name in MODULE.FIELDS},
        id(byte_only): {name: 1.0 for name in MODULE.FIELDS},
        id(semantic): {name: (2.0 if name == "mo" else 1.0) for name in MODULE.FIELDS},
    }
    monkeypatch.setattr(MODULE, "sgp4_fields", lambda row: fields[id(row)])
    original = {
        1: ((100, 10, "sha256:a", "element:a"), old),
        2: ((100, 10, "sha256:a", "element:a"), old),
    }
    selected = {
        1: ((100, 20, "sha256:b", "element:b"), byte_only),
        2: ((200, 20, "sha256:b", "element:c"), semantic),
    }
    result = MODULE.compare_catalogues(original, selected)
    assert result["changed_element_bytes"] == 2
    assert result["byte_only_no_sgp4_change"] == 1
    assert result["changed_sgp4_inputs"] == 1
    assert result["newer_epoch_and_changed_sgp4"] == 1
