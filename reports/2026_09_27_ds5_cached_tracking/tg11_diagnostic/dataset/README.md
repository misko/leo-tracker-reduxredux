# TG11 diagnostic dataset

`cases.json` freezes 52 constructed physical cases. Only the 26 `development`
cases are materialized. The 26 `validation` cases have frozen seeds, source
counters, components, amplitudes, phases, and output paths, but their IQ files
remain absent until a detector candidate is frozen.

Load one development case with:

```python
import json
from pathlib import Path
import numpy as np

root = Path("reports/2026_09_27_ds5_cached_tracking/tg11_diagnostic/dataset")
manifest = json.loads((root / "cases.json").read_text())
case = next(item for item in manifest["cases"] if item["split"] == "development")
iq = np.load(root / case["raw_npy"]["path"], allow_pickle=False)
assert iq.dtype.str == "<i2" and iq.shape == tuple(case["raw_npy"]["shape"])
```

The last axes are receiver then IQ: `iq[sample, receiver, 0]` is I and
`iq[sample, receiver, 1]` is Q. Truth describes injected components and contains
no detector outcomes. Do not materialize or inspect validation IQ before the
candidate source freeze.
