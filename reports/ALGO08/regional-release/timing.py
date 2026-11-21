"""Time the installed, pinned baseline or regional fit plus its eight figures on one CPU."""
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter, process_time

from leo.operations.tle_archive import TleArchiveReader
from leo.presentation.fast_standard_analysis import render
from tools.algo08_position import solve


def measure(case, assets, region_file=None):
    data = Path("/srv/bulk/leo-dev/ds30-full-20261121")
    receipt = json.loads((data / "runs" / case / "compact_two_scan/acquisition.json").read_bytes())
    raw = Path(receipt["native_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == receipt["native_sha256"]
    native = json.loads(raw)
    archive = TleArchiveReader(data / "snapshot/inputs" / case / "tle")
    optional = []
    if region_file:
        from leo.contracts.algo08_region import Algo08Region
        optional.append(Algo08Region.parse(json.loads(Path(region_file).read_bytes())))
    started, cpu = perf_counter(), process_time()
    result, packet, _ = solve(native, archive, Path(assets), *optional)
    fit_wall, fit_cpu = perf_counter() - started, process_time() - cpu
    started, cpu = perf_counter(), process_time()
    images = render(packet, title=case)
    return dict(case=case, assets=str(assets), arms=result["arms"], fit_wall_s=fit_wall,
                fit_cpu_s=fit_cpu, render_wall_s=perf_counter()-started, render_cpu_s=process_time()-cpu,
                pngs=len(images), grid_evaluated=packet["position_grid"]["evaluated_points"])


if __name__ == "__main__":
    print(json.dumps(measure(*sys.argv[1:])))
