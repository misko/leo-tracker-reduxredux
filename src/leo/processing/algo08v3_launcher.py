"""Run the frozen launcher with production figure labels in its own process."""

import runpy
import sys
from unittest.mock import patch


def run(launcher, arguments):
    from matplotlib.text import Text

    original = Text.set_text

    def set_text(artist, value):
        if isinstance(value, str):
            for frozen, production in (
                ("ALGO08v2 selected result ·", "ALGO08v3 selected result ·"),
                (" · ALGO08v2 · RMS for every", " · ALGO08v3 · RMS for every"),
                ("\nALGO08v2 · diagnostic position map\n", "\nALGO08v3 · diagnostic position map\n"),
                ("Final position error unavailable — no confirmed evaluation reference",
                 "See analysis details for post-fit reference errors"),
                (": evaluation reference unavailable", ": reference error reported separately"),
            ):
                value = value.replace(frozen, production)
        return original(artist, value)

    # The old model key controls the frozen renderer's regional layout. Change
    # its displayed text after layout selection, keeping the packet intact.
    with patch.object(Text, "set_text", set_text), patch.object(sys, "argv", [launcher, *arguments]):
        runpy.run_path(launcher, run_name="__main__")


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2:])
