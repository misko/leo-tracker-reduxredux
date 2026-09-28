# Build status

V1 is rejected: its conditioned key omitted the appended final grid frequency.
The paths below are retained only as a record and must not be qualified or
deployed. V2 supersedes them.

| Build | Path | Receipt SHA-256 | Status |
| --- | --- | --- | --- |
| Host V1 | `/var/tmp/leo-host-refinement-cache-v1` | `fefa36662e13f2c5cc773e276bb0d983d0931d2e2cd208d3c5d7dbc2f74784be` | rejected unsafe key |
| Host ASAN/UBSAN V1 | `/var/tmp/leo-host-refinement-cache-asan-v1` | `9a0c163173dc2bbbbc7c14ce3c7ed13bb4d38194a0fdb2775ea09c043da0e203` | rejected unsafe key |
| ARM V1 | `/var/tmp/leo-arm-refinement-cache-v1` | `7c0f2f940260831c2e65d6cb95bfead22ad00749c148628fefb7cfd954858d3f` | rejected unsafe key |
| Host V2 | `/var/tmp/leo-host-refinement-cache-v2` | `25489a05b8a1b157085be7562e9bf1de31d5a36cfa1cba4ef8c7c0cc6d15be2d` | safe key; all units pass |
| Host ASAN/UBSAN V2 | `/var/tmp/leo-host-refinement-cache-asan-v2` | `8673f06eabffbc2c4b96762e364366f52e89b7b89f358a103da68a4b3732a249` | safe key; all units pass |
| ARM V2 | `/var/tmp/leo-arm-refinement-cache-v2` | `ed98e1ae44ad279c6f1d13b7286ea9ea029a793e90f611345133a839f756cbc6` | safe key; cross-build only |

Exact V1 and V2 source snapshots and receipts are archived under `builds/`. No hardware
or cohort execution was performed by the implementation agent. Candidate
parity and any performance claim require root-owned cohort measurement.
