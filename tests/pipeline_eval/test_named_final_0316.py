"""Keep the final-fit transfer on the admitted signed inputs and reviewed options."""

from types import SimpleNamespace

import pytest

from named_final_0316 import PROJECTION, configure, manifest_files


def test_metadata_port_adds_only_manifest_filename_and_keeps_order():
    directories = [["/original/segment-000", "sha256:first"], ["/original/segment-001", "sha256:second"]]
    inventory = dict(segments=[dict(path=path, manifest_digest=pin) for path, pin in directories])
    assert manifest_files(directories, inventory) == [[path+"/manifest.json", pin] for path, pin in directories]
    with pytest.raises(ValueError, match="manifest roster"):
        manifest_files(list(reversed(directories)), inventory)
    with pytest.raises(ValueError, match="manifest roster"):
        manifest_files([[directories[0][0], "sha256:wrong"], directories[1]], inventory)


def test_discovery_keeps_original_options_and_enables_original_finish_and_guards():
    options = SimpleNamespace(exact_graph_reuse=True, one_pass_web_png=True, recording="/original", region="/offer")
    configure(options)
    assert options.recording == "/original" and options.region == "/offer"
    assert options.exact_graph_reuse and options.one_pass_web_png
    assert options.named_survivor_finish and options.withhold_empty_family_calibration
    assert options.reuse_verified_png_reads and options.direct_residual_figures and options.direct_orbit_figures
    assert options.grid_feature_projection_library == PROJECTION
