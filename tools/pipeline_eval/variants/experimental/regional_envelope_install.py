"""Install the measured hard-support guard in one installed v3 publication."""

from contextlib import contextmanager
from functools import wraps
from hashlib import sha256
from pathlib import Path
from runpy import run_path
from unittest.mock import patch

REGIONAL_SOURCE = "8132d840c76bd585c3102e59e0a1746a8e50a8f75ba02979b9273f6b1a0403dd"
FINE_SOURCE = "a86e62fed9eb7c286747fcf20e246010b3f06774dc9f79843ea7f8610a0fa7b4"


@contextmanager
def install(publication, specification, args):
    if specification.get("curved_design") is not True or specification.get("solver") != "screened-tiled-finish":
        raise ValueError("Regional support guard requires the frozen v3 solver composition")
    source = Path(__file__).with_name("regional_envelope.py")
    if sha256(source.read_bytes()).hexdigest() != REGIONAL_SOURCE:
        raise ValueError("Unexpected regional envelope source")
    original = publication._with_curved_design
    counts = {"solves": []}
    regional = None

    def configure(*parameters, **options):
        nonlocal regional
        solve = original(*parameters, **options)
        if regional is None:
            # The frozen launcher calls this after installing its lazy facades
            # and binding its original stable salvage gate.
            regional = run_path(str(source))["regional_fine_salvage"]

        @wraps(solve)
        def guarded(*inputs, **keywords):
            with regional(prune=True, expected_source_sha256=FINE_SOURCE) as work:
                result = solve(*inputs, **keywords)
            counts["solves"].append(dict(work))
            return result

        return guarded

    with patch.object(publication, "_with_curved_design", configure):
        yield counts
