"""Build the tiled short-filter implementation for the existing grid binding."""

import subprocess
from pathlib import Path

from .anchor_receiver import FLAGS

SOURCE = Path(__file__).with_suffix(".c")


def compile_filter(library):
    subprocess.run(["cc", *FLAGS, str(SOURCE), "-lm", "-o", str(library)], check=True)
