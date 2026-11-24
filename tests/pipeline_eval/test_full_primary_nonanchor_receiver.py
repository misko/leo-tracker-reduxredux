from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from reports.ALGO08.v3.ds30_0016_full_primary_transfer import invocation
from reports.ALGO08.v3 import full_primary_nonanchor_receiver as receiver


def test_opt_in_rebinds_only_the_receiver_and_output():
    original = ["/timeout", "--kill-after=2s", "75s", "/python", "-IB", "/entry", "--recording", "/signed",
                "--region", "/original-offer", "--archive", "/original-archive", "--output", "/old",
                "--short-binary", "/short.so", "--verify-original-once", "--sparse8-primary"]
    new = invocation(original, Path("/next"))
    expected_pairs = {"--recording": "/signed", "--region": "/original-offer", "--archive": "/original-archive",
                      "--output": "/next"}
    assert new[:5] == original[:5] and new[5].endswith("/integrated_original_entry.py")
    assert all(new[new.index(flag) + 1] == value for flag, value in expected_pairs.items())
    assert {"--verify-original-once", "--full-primary-nonanchors"} <= set(new)
    assert not {"--short-binary", "/short.so", "--sparse8-primary"} & set(new)
    assert original[-1] == "--sparse8-primary"


def test_native_binding_uses_full_context_for_both_roles_and_restores_constructor(monkeypatch):
    roles = receiver.mixed.FULL_RULE
    original_call = SimpleNamespace(argtypes=[str], restype=int)
    primary_call = SimpleNamespace()
    seen = []

    def constructor(library, pilot, mode):
        seen.append((library, pilot, mode))
        return SimpleNamespace(call=original_call, maximum=2)

    @contextmanager
    def detector(_self, **_kwargs):
        yield tuple(receiver.mixed.NativePath("/installed.so", "pilot", mode) for mode in set(roles))

    monkeypatch.setattr(receiver.mixed, "NativePath", constructor)
    monkeypatch.setattr(receiver.mixed, "verified", lambda *_args: b"verified")
    monkeypatch.setattr(receiver.mixed.MixedApertureDetector, "detector", detector)
    monkeypatch.setattr(receiver.ctypes, "CDLL", lambda _path: SimpleNamespace(primary_factors=primary_call))
    receiver_port = receiver.FullPrimaryNonanchor("/installed.so")
    with receiver_port.detector() as paths:
        assert receiver.mixed.NativePath is constructor
        by_rank = {path.maximum: path.call for path in paths}
        assert by_rank == {1: primary_call, 2: original_call}
        assert (primary_call.argtypes, primary_call.restype) == ([str], int)
    assert seen == [("/installed.so", "pilot", "full")] * 2


def test_receipt_and_recipe_name_the_paid_apertures():
    port = object.__new__(receiver.FullPrimaryNonanchor)
    receiver.mixed.MixedApertureDetector.__init__(port, "/installed.so", receiver.mixed.INSTALLED_SHA,
                                                 full_coverage=True)
    port.native_calls.update(full=2, short_primary=14)
    audit = port.receipt()
    recipe = receiver.recipe()
    assert audit["rule"] == recipe["rule"] == ["20ms_two_scan"] + ["20ms_primary"] * 7
    assert recipe["aperture_samples"] == [200_000, 200_000]
    assert audit["native_calls"] == {"20ms_primary": 14, "20ms_two_scan": 2}
    assert audit["primary_helper_sha256"] == recipe["primary_helper_sha256"]
    assert "short_primary_sha256" not in audit
