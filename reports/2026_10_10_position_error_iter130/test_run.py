import runpy
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

api = runpy.run_path(str(Path(__file__).with_name("run.py")))


def test_exclusive_crash_claim_blocks_automatic_retry(tmp_path):
    binding = {"member": {"inventory_label": "test"}}
    (tmp_path / "test.claim.json").write_text("{}")
    with pytest.raises(FileExistsError):
        api["member"](
            binding, "digest", lambda *_: pytest.fail("reconstructed"), {}, None, tmp_path
        )
