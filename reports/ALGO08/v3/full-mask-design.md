# Borrow the full normal design at the finalist bound

The enabled released curved-design port gathers every selected row into a second
dense array and then multiplies each gathered element by its column scale. The
ordinary `position.refreshed` finalist supplies a full observation mask and
`NormalPosition.calculate` supplies all-one column scales in both calibration
arms. With these inputs, the selector can pass a read-only view of the fresh
design to the bound. Both arms keep distinct designs and every optimizer
evaluation still takes place.

This is downstream of the existing curved assembly and selected-rows-first
optimization. The earlier finalist tangent and grid geometry studies accelerated
or bounded geometric evaluations, and the signed state and phase-reuse studies
examined repeated states and conditioning. The gain here applies at distinct
states after assembly, without a geometry, position, or posterior cache.

## Scope and equivalence

The [research context](full_mask_design.py) attaches inside the enabled,
source-pinned released curved-design scope on a single synchronous solver
process. It checks the actual normal calculation, the installed native wrapper
and binary, and the original Python bound that handles native rejections. The
installed layout and run entry points read their design argument, and the cache
retains only symbolic structure. The original fallback reads its input and
computes whitening into a new array. Contiguity, 64-bit native dtype, array
shape, a full mask, and exact unit scales are checked. The released joint
calculation already verifies that the fresh design is finite. Every eligible
element is forwarded in its original row/column order. Multiplying by
binary64 one is exact for these finite values, including signed zero.

Partial masks, nonunit scales, noncontiguous or unsupported inputs, custom
bound callbacks and unrecognized ports use the original path. The history
selector stays outside the normal context and its nonunit priors retain their
original scaling. The existing selector still counts calls and records the
time within its original boundary. Native rejections, fit stopping, bounds,
response/variance selection, posterior factorization and residuals use the
same released code. The source and binary pins define this controlled research
environment.

## Component evidence

The installed ALGO08v3 Python, source and native library ran the actual released
two-round `position.refreshed` path at two synthetic WGS84 sites. Each fixture
contains four curved tracks, two radios, different RF frequencies, explicit
aliases and 172 observations on prepared Earth-fixed trajectories. The
comparison covers every evaluation, including all posterior fields, features,
RF residuals, objective terms, phase updates, bounds encountered, ordered
membership, local and geographic endpoints, and three fixed position queries.
Byte agreement held separately for each calibration arm and geography.

| Synthetic origin | Calibration | Forwarded calls | Design-copy bytes avoided | Unit multiplies avoided |
| --- | --- | ---: | ---: | ---: |
| 0°, 0° | Fixed zero | 47 | 2,457,536 | 307,192 |
| 0°, 0° | Fitted | 40 | 2,146,560 | 268,320 |
| 23° S, 137° E | Fixed zero | 47 | 2,457,536 | 307,192 |
| 23° S, 137° E | Fitted | 47 | 2,522,208 | 315,276 |
| Total | | 181 | 9,583,840 | 1,197,980 |

Each arm's baseline and candidate had the same native activations and symbolic
cache counts. The guard covered 31,132 mask entries and 6,965 scale entries,
and creates a small read-only view per eligible evaluation. These are logical
copy and element counts. Native factorization was also forced to reject on
conditioning and on an unsupported layout with too many private columns per
curve. The original Python fallback returned the same bytes in each case. A live
partial mask and a changed native callback exercised the released selector.
An initial three-curve fixture confirmed that singleton receiver/band groups
can exceed the released layout's two-private-column limit. The paired fixture
was expanded to four curves to exercise native activation on both radios, and
the private-column failure became its own regression test.

## Existing clock ceilings

The archived normal-selector CPU counter directly bounds the old work this
particular change could remove. It includes every normal selector call, so
ineligible calls and the guard reduce any realized gain further.

| Archived path | Normal selections | Selector CPU ceiling |
| --- | ---: | ---: |
| Integrated original 20/8 DS30-0016, positive first | 45 | 0.307 ms |
| Integrated original 20/8 DS30-0016, withholding first | 45 | 0.323 ms |
| Older saved dense DS30-0008, original bounds | 428 | 468.452 ms |
| Older saved dense DS30-0008, bounds treatment | 428 | 435.637 ms |
| Saved DS30-0255, conditional-repair worker | 131 | 180.406 ms |

The weak workflow has essentially no time at this boundary. The older dense
path leaves under half a CPU second gross. No physical position, whole solve,
publication, or new timing measurement was made. The
[operation receipt](measurements/full-mask-design.json) binds the archived
counter sources. The prototype is isolated from the field CLI and frozen
builds.

## Reproduce

Run the [11 component checks](../../../tests/pipeline_eval/test_full_mask_design.py)
with the deployed Python and package paths. Add the development site-packages
path at the end strictly for pytest. The tests explicitly mark the installed
native ABI cases and report operation counts. The checks were restricted to
CPU 3 at nice 15 with one numeric thread.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
PYTHONPATH=.:/opt/leo-algo08/algo08v3/payload:"$release/src" \
nice -n 15 taskset -c 3 "$release/venv/bin/python" -B -c '
import sys
sys.path.append("/home/mouse9911/gits/leo-tracker-reduxredux/.venv/lib/python3.12/site-packages")
import pytest
sys.exit(pytest.main(["-p", "no:cacheprovider", "-q", "-s",
                      "tests/pipeline_eval/test_full_mask_design.py"]))
'
```
