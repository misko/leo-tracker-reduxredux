import ast
import json
import sys
from collections import OrderedDict
from contextlib import contextmanager
from hashlib import sha256
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval import cavity_runtime
from tools.pipeline_eval.qualification import compact_catalogue_build as overlay


@pytest.fixture(scope="module")
def release():
    return cavity_runtime.release_files(cavity_runtime.RELEASE, "phase-release")


def syntax(release, candidate=True):
    source = overlay.parser(release[overlay.ELEMENTS].decode(), candidate)
    owner = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef))

    def catalogue(names, numbers, satellites):
        return SimpleNamespace(names=names, satellite_numbers=numbers, satellites=satellites)

    namespace = {
        "sys": sys,
        "OrderedDict": OrderedDict,
        "sha256": sha256,
        "ElementSetCatalogue": catalogue,
        "ElementSetError": ValueError,
    }
    exec(compile(ast.Module(body=[owner], type_ignores=[]), "regional-elements", "exec"), namespace)
    return namespace


def record(number, suffix=""):
    return SimpleNamespace(
        name=f"{number}{suffix}",
        satellite_number=number,
        first_line=str(number),
        second_line=suffix,
    )


def test_projection_requires_full_validation_of_exact_text_and_builds_fresh_selected_objects(
    release,
):
    ns = syntax(release)
    docs = {
        "verified": (record(3), record(1), record(3, "alias")),
        "modified": (record(3), record(1, "bad")),
    }
    calls = []

    def construct(first, second):
        calls.append((first, second))
        if second == "bad":
            raise ValueError("corrupt unselected value")
        return SimpleNamespace(satnum=int(first), suffix=second)

    ns["parse_element_set_records"] = docs.__getitem__
    ns["Satrec"] = SimpleNamespace(twoline2rv=construct)
    p = ns["ElementParser"](0)
    cold = p("verified", selected={3})
    assert cold.satellite_numbers == (3, 1, 3)
    projected = p("verified", selected={3})
    assert projected.satellite_numbers == (3, 3)
    assert projected.names == ("3", "3alias")
    assert projected.satellites[0] is not cold.satellites[0]
    assert calls == [("3", ""), ("1", ""), ("3", "alias"), ("3", ""), ("3", "alias")]
    assert (p.offered, p.constructed, p.planned, p.bytes) == (6, 5, 1, 0)
    for _ in range(2):
        with pytest.raises(ns["ElementSetError"], match="catalog object 1"):
            p("modified", selected={3})
    assert p.planned == 1


def test_native_id_disagreement_and_stock_override_never_narrow(release):
    for candidate in (False, True):
        ns = syntax(release, candidate=candidate)
        ns["parse_element_set_records"] = lambda _: (record(12), record(13))
        ns["Satrec"] = SimpleNamespace(
            twoline2rv=lambda first, _: SimpleNamespace(satnum=int(first) + 1)
        )
        p = ns["ElementParser"]()
        assert p("text").satellite_numbers == (13, 14)
        assert p("text", selected={14}).satellite_numbers == (13, 14)
        assert p.planned == 0


def test_last_use_accepts_regional_port_and_releases_existing_text_cache(release):
    ns = syntax(release)
    ns["parse_element_set_records"] = lambda _: (record(3), record(7))
    ns["Satrec"] = SimpleNamespace(twoline2rv=lambda first, _: SimpleNamespace(satnum=int(first)))
    parser = ns["ElementParser"]()
    parser("text")
    assert parser.bytes > 0
    src = overlay.lifetime(release[overlay.LIFETIME].decode())
    # The last-use port needs only its own function and context manager.
    function = next(node for node in ast.parse(src).body if getattr(node, "name", "") == "last_use")
    namespace = {"contextmanager": contextmanager}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "last-use", "exec"), namespace)
    receipt = {}
    with namespace["last_use"](parser, receipt) as prepared:
        assert prepared.screened is True
        assert prepared("text", selected={7}).satellite_numbers == (7,)
        assert parser.bytes == 0
    assert receipt["released_entries"] == 1
    assert parser.maximum_bytes > 0


def test_measured_forecast_witness_handles_numpy_arrays_and_scalar_flags(release, capsys):
    body = overlay.application(release[overlay.APPLICATION].decode())
    function = next(
        n for n in ast.parse(body).body if getattr(n, "name", "") == "prepare_native_scan"
    )
    witness = function.body[-2]
    observations = dict(
        own_parser=True,
        sky={"bank": object(), "nominal_elements": {}},
        history={"past_versions": {}},
        prior={"signed": np.bool_(True), "errors": np.array([1.0, 2.0])},
        element_parser=SimpleNamespace(offered=10, constructed=2, planned=1, statistics=dict),
    )
    exec(
        compile(ast.Module(body=[witness], type_ignores=[]), "forecast-witness", "exec"),
        observations,
    )
    row = json.loads(capsys.readouterr().err.removeprefix("catalogue-work "))
    assert (row["offered"], row["constructed"]) == (10, 2)
    assert len(row["evidence_sha256"]) == 64
