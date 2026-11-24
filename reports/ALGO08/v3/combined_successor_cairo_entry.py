"""Opt the original-file guarded successor into the standard six-Cairo publisher."""

from functools import partial
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import combined_successor_raw_entry as guarded


def main():
    import legacy_block_raw_entry as original

    options = set(sys.argv[1:])
    if not options.intersection(("--cairo-six-sheets", "-h", "--help")):
        raise ValueError("The dedicated original-file entry requires --cairo-six-sheets")
    # Keep the reader, scoped successor and normal publication entry intact.
    enabled = partial(original.run, allow_cairo_orbits=True)
    previous_smoke = guarded.smoke

    def smoke(args, acceleration):
        from direct_orbit_figures import library

        if not original.orbit_renderer(args, allow_cairo_orbits=True) or not callable(library().cairo_image_surface_create):
            raise ValueError("The six-sheet renderer did not bind at startup")
        previous_smoke(args, acceleration)

    with patch.object(original, "run", enabled), patch.object(guarded, "smoke", smoke):
        guarded.main()


if __name__ == "__main__":
    main()
