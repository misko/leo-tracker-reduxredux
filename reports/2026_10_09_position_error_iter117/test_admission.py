import json
import runpy
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent / "2026_10_09_position_error_iter111"


def test_real_main_accepts_original_protocol_key_without_input_work(monkeypatch):
    namespace = runpy.run_path(str(HERE / "audit.py"))
    main = namespace["main"]
    monkeypatch.setitem(main.__globals__, "HERE", ORIGINAL)
    monkeypatch.setattr(sys, "argv", ["audit.py", "--shard", "0"])
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.setenv(name, "1")
    seen = []

    def no_input(binding, digest):
        seen.append(binding)
        return dict(status="synthetic-no-input")

    monkeypatch.setitem(main.__globals__, "evaluate", no_input)
    main()
    plan = json.loads((ORIGINAL / "protocol.json").read_text())
    assert seen == plan["members"][::2]


def test_original_main_reproduces_missing_key_before_input(monkeypatch):
    main = runpy.run_path(str(ORIGINAL / "audit.py"))["main"]
    monkeypatch.setattr(sys, "argv", ["audit.py", "--shard", "0"])
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.setenv(name, "1")
    monkeypatch.setitem(main.__globals__, "evaluate", lambda *a: pytest.fail("input work"))
    with pytest.raises(KeyError, match="qr_chunk_rows"):
        main()
