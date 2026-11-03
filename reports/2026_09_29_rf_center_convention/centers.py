"""Export nominal centers through the installed public frequency contract."""

import hashlib
import inspect
import json
from pathlib import Path

from leo.contracts.starlink_frequency import starlink_edge_rf_center_frequency_hz

p = Path(inspect.getfile(starlink_edge_rf_center_frequency_hz))
print(
    json.dumps(
        dict(
            source=str(p),
            sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
            centers=[
                dict(channel=c, edge=e, rf_hz=starlink_edge_rf_center_frequency_hz(c, e))
                for c in range(1, 5)
                for e in ("lower", "upper")
            ],
        ),
        indent=2,
    )
)
