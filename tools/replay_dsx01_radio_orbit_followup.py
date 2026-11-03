"""Rebuild comparison products from frozen sources and pinned on-disk inputs."""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "reports/2026_10_18_dsx01_radio_orbit_followup"
FROZEN = CHECKPOINT / "run_sources"


def run():
    sys.path[:0] = [str(FROZEN / "tools"), str(FROZEN / "src")]
    import report_dsx01_radio_orbit_followup as report

    # Frozen tools derive paths from their source location. Keep their code,
    # but bind data ports to the same original repository inputs. Do not alter
    # this harness's own paths or any numerical value.
    for name, module in tuple(sys.modules.items()):
        if name == "__main__" or module is None:
            continue
        for key, value in tuple(vars(module).items()):
            if isinstance(value, Path) and value.is_relative_to(FROZEN):
                setattr(module, key, ROOT / value.relative_to(FROZEN))
    destination = CHECKPOINT / "replay_products"
    destination.mkdir(exist_ok=True)
    for name in ("local_information.json", "precision_backend_checks.json"):
        shutil.copy2(CHECKPOINT / name, destination / name)
    report.OUTPUT = destination
    report.run(list(report.SPECS))
    import document_dsx01_radio_orbit_followup as document

    document.run()
    print(json.dumps(dict(frozen_sources_only=True, output=str(destination))), flush=True)


if __name__ == "__main__":
    run()
