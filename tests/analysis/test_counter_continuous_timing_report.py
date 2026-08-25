from __future__ import annotations

import gzip
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
REPORT = ROOT / "reports" / "2026_08_25_counter_continuous_frame_timing_and_delay.md"
LONG_ROOT = ROOT / "reports" / "figures" / "2026_08_25_counter_continuous_frame_timing"
GRID_ROOT = ROOT / "reports" / "figures" / "2026_08_25_fractional_delay_grid"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def test_report_figure_links_resolve() -> None:
    text = REPORT.read_text(encoding="utf-8")
    links = re.findall(r"\]\((figures/[^)]+)\)", text)

    assert links
    assert all((REPORT.parent / link).is_file() for link in links)


def test_frozen_timing_and_grid_artifacts_match_declared_bytes() -> None:
    expected = {
        LONG_ROOT / "long-track-evidence.json": (
            "619a715143c20801efbe8be3dee012b1a83e3fc730d588bb3a2c6cd2382de579"
        ),
        LONG_ROOT / "epoch-doppler-curvature.json": (
            "24bf59d774c2ca20dd896dd090fdafe146abca5218c54f161c1e07c3ac203f7d"
        ),
        LONG_ROOT / "epoch-residual-detailed-fit.json": (
            "743827a8cc836cd3b04610b698cb2f0236c17bd585cc2af11fcf169f5055a0e8"
        ),
        LONG_ROOT / "long-track-full.png": (
            "b193a7260c66a43fbaebefc3d0df6c8690d941a5117ba4c6909226d5d979a2ce"
        ),
        LONG_ROOT / "detailed-epoch-doppler.png": (
            "512e442db18729b139950170a0496fe269576cbc51c05658156a2f3c0acb71c6"
        ),
        LONG_ROOT / "detailed-epoch-residual-fit.png": (
            "a19fcfebf4571788703a8c41233ff958ab89f055800bd1562a1b065ffb2f6703"
        ),
        GRID_ROOT / "anchor016-fine-grid-evidence.json": (
            "340f134a165a24db1471c197a3316fdff677dbaa2ccdbba785c2066730a32c98"
        ),
        GRID_ROOT / "anchor016-frame-rows.json": (
            "faddda18fa2b769ac3a574154c376c808ba3ec43f5ea1a0718adc896d5d2412f"
        ),
        GRID_ROOT / "anchor016-fine-grid-crossfit.png": (
            "4dcb14870f8846019ddd73761f1226368d60495fbb945b15625b023906bee0d6"
        ),
    }

    assert {path: _sha256(path) for path in expected} == expected


def test_compressed_frame_ledger_reproduces_manifest_bound_rows() -> None:
    digest = hashlib.sha256()
    with gzip.open(LONG_ROOT / "long-track-frame-rows.jsonl.gz", "rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)

    assert digest.hexdigest() == (
        "2d40f818bb76723629227704066137c0947a9523742f60fdd1cfad3a79842fd4"
    )


def test_fractional_grid_remains_fail_closed() -> None:
    evidence = json.loads(
        (GRID_ROOT / "anchor016-fine-grid-evidence.json").read_text(encoding="utf-8")
    )
    acceptance = evidence["real_crossfit"]["acceptance"]
    directions = evidence["real_crossfit"]["primary_direct_time_blocked_directions"]

    assert acceptance["accepted"] is False
    assert acceptance["blocked_gain_positive_both_directions"] is False
    assert acceptance["blocked_all_exact_and_control_maxima_interior"] is False
    assert directions[0]["heldout_gain_over_integer"] > 0.0
    assert directions[1]["heldout_gain_over_integer"] < 0.0


def test_retained_source_snapshots_match_report_provenance() -> None:
    expected = {
        LONG_ROOT / "source" / "run_new_continuity_probe.py": (
            "e6234ad4a82a0158b569cc289f71f659e90f812cce673107c987b8eb6902022f"
        ),
        LONG_ROOT / "source" / "plot_new_long_continuity.py": (
            "37b9fc2bd9538b9226157e29621cef9f7bae16c972117016c1d4e4df020200b7"
        ),
        LONG_ROOT / "source" / "render_detailed_epoch_doppler.py": (
            "f51b34194aa1024caf976f837b1408276afba46fe83bbf2c944295494c5e80ff"
        ),
        LONG_ROOT / "source" / "render_epoch_residual_anatomy.py": (
            "ce6fa5ee9985956dd7e5b353f181256ca93e414ffe5ad54ac0e235a7ed0a06d7"
        ),
        GRID_ROOT / "source" / "fine_grid_anchor016_prototype.py": (
            "792484b4ec15cd0c91e32b630fb4c04e0177308615275ac173897847e8b9d503"
        ),
    }

    assert {path: _sha256(path) for path in expected} == expected
