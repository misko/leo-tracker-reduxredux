"""Keep application tests on this checkout when oracle scripts alter sys.path."""

import sys
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SOURCE))

# Bind the package before collection imports research scripts that add reference
# checkout paths. Reference native libraries remain explicit numerical oracles.
import leo  # noqa: E402

if Path(leo.__file__).resolve().parent != SOURCE / "leo":
    raise RuntimeError("research tests must import the current checkout's leo package")
