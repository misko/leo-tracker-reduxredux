# Measuring initial continuation donors

The primary and secondary factors in a newly observed RF lane have no chance of being selected until there are three earlier votes. This experiment requests a full two-scan measurement on the first three admitted opportunities on each lane. It uses the original conditional schedule after that. A secondary factor seen solely through this initialization enters continuation history, but does not extend the eight-second scan schedule. This keeps the cost bounded to at most two extra full scans per lane for the entire recording. The receiver uses only measured frequencies, device time and lane identity. A lane comprises the antenna, channel and actual RF frequency.

The affected history has exactly twelve slots per lane. After the fifteenth admitted opportunity, all three initial measurements have expired. If the two planners agree at that point on the observed history, counters and last activity time, then every remaining decision on that lane is identical for identical native input. The experiment will verify that state for every lane before splicing any previously measured suffix.

Use the two available full before-continuation ledgers on DS30-0016 and the southern public simulation. For DS30-0155, which exposed the early missing donors, use only the initial raw windows needed to reach this equality on every admitted lane. Compare the ordinary conditional selections to their frozen publication, bind the changed selections into a new detection document and run the existing two-arm solver once. The DS30-0155 result is a targeted mechanism and position test. The previously observed failure motivated the initialization experiment. No threshold or schedule will be selected from the resulting position.

## Results

The initialized receiver recovered the measured primaries at visits 68 and 69 of DS30-0155. Its fitted position moved **122 m closer to the scoring reference** and remained **148 m farther away than deployed**. The initialization changed only these two selected observations in the entire recording. In the subsequent two-arm fit, the number of associated points fell by 36 and RF RMS decreased by about 0.16 Hz. The position benefit therefore cannot be inferred from a count of retained points. [Measurement and scored position](measurements/initial-donors.json)

| DS30-0155 method | Associated points per arm | Fixed-zero error | Fitted error | RF RMS fixed-zero / fitted |
|---|---:|---:|---:|---:|
| Deployed ALGO08v2 | 3,498 | 0.972 km | 1.157 km | 155.420 / 155.382 Hz |
| Conditional receiver | 3,470 | 1.291 km | 1.426 km | 156.077 / 156.064 Hz |
| Conditional with initial donors | 3,434 | 1.153 km | 1.304 km | 155.917 / 155.909 Hz |

The raw replay read the first 223 scheduled visits, executed 416 admitted antenna-lane opportunities and verified the conditional selection against the saved terminal at every one. The initialized planner made 28 additional second scans. For these calls, the primary-only native entry used 59.5 ms CPU and the full entry 99.0 ms, an incremental 39.5 ms in this single fixed-order measurement. At the end of the prefix, counters, schedule activity times and all continuation slots matched on every lane. The score used the verified unchanged suffix and the original solver, offer, causal archive and calibration arms. The measured boundary covers the prefix and a separate saved-input solve. The study did not time a new end-to-end publication.

| Other complete pre-continuation ledger | Admitted lane opportunities | Additional second scans | Selection changes vs conditional | Differences still present vs always scanning twice |
|---|---:|---:|---:|---:|
| DS30-0016, Gauss | 1,426 | 24 | 0 | 1 |
| Southern public simulation | 2,400 | 32 | 0 | 0 |

On the earlier DS30-0016 loss, a required donor arrived after initialization. On the southern simulation, all selected evidence was already preserved. A repeat with the initialization isolated from the frozen scheduling module reproduced the entire DS30-0155 detection document byte for byte and both saved-ledger receipts. [Previous history-rescue experiment](receiver-primary-rescue.md) · [Portable policy](../../../tools/pipeline_eval/variants/experimental/initial_donors.py) · [Runner](initial_donor_trial.py) · [Tests](../../../tests/pipeline_eval/test_initial_donor_slots.py)

## Reproduction

Run the following from the worktree on Gauss with an unused scratch directory writable by the account that reads the sealed raw capture. Each measured command uses the shared lock. The last step opens the scoring-only reference after the fitted position has been written.

~~~bash
t=reports/ALGO08/single-core-2x
p=/tmp/leo-algo08v2-2x-bench
rel=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
pair=/tmp/ds30-v2-stage-65b664/DS30-0155/pair.json
request=/srv/bulk/leo-dev/ds30-full-20261121/snapshot/inputs/DS30-0155/request.json
py=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
scratch=$(sudo -n -u leo mktemp -d /tmp/leo-initial-donor-XXXXXX)
sudo -n -u leo chmod 755 "$scratch"
serial() {
  flock -x "$p/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 "$@"
}
export PYTHONPATH="$PWD/src:$PWD:$PWD/$t" OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
serial sudo -n -u leo env PYTHONPATH="$PYTHONPATH" OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  "$rel/venv/bin/python" -BPs "$t/initial_donor_trial.py" raw "$pair" "$rel/assets" "$scratch/native.json" > "$p/initial-donor-0155.json"
for site in DS30-0016 south; do
  serial "$py" "$t/initial_donor_trial.py" ledger "$p/ledger-$site.json.gz" \
    "$p/integration-shared/pairs/$site"/candidate/fast-scan-automatic-work/*/detections.json \
    "$t/measurements/primary-residual-rescue.json" "$site"
done
serial "$py" "$t/initial_donor_trial.py" position "$pair" "$p/initial-donor-0155.json" \
  "$scratch/native.json" "$p/integration-conditional-residual-reviewed" "$request" "$p/initial-donor-fit-new.json"
"$py" "$t/initial_donor_trial.py" score "$p/initial-donor-fit-new.json" "$p/initial-donor-0155.json" \
  "$t/measurements/DS30-0155-residual-attribution.json" reports/2026_11_21_ds30_full/reference-audit.json
~~~
