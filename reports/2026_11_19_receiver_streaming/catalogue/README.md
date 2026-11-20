# Bytewise TLE checksums in full v5

The checksum lookup produced the same value as the original on all 22,284 DS26 and 22,370 DS29 orbital element lines. Five paired timing passes on each catalogue gave median speedups of 11.56× and 12.21× for the checksum calculation. A full catalogue pass took about 7 ms with the replacement. [DS26 timings](DS26-0036.json) · [DS29 timings](DS29-0082.json) · [Protocol](PROTOCOL.md)

Both numerical v5 fits started from the original GLRT detections and the same causal catalogue. All four coordinates exactly matched fresh full numerical v5, as did the associated observation counts, conditional Doppler RMS and frequency objectives. [Position chart](../figures/fitted_c/catalogue_checksum.png) · [Candidate predictions](positions.jsonl.gz) · [DS26 numerical control](../finish/DS26-0036-v5_lean.json) · [DS29 numerical control](../finish/DS29-0082-v5_lean.json)

| Recording | Observations per arm | Position error, zero / fitted (km) | Conditional Doppler RMS, zero / fitted (Hz) | Worker wall time (s) |
|---|---:|---:|---:|---:|
| DS26-0036 | 2,690 | 1.278 / 1.208 | 74.761 / 74.682 | 151.92 |
| DS29-0082 | 929 | 0.567 / 0.517 | 97.004 / 96.684 | 117.10 |

The end-position runs used one numerical thread per worker on the host. Controls on different CPU cores supplied the matched numerical outputs. The paired speed measurement covers only checksum verification. The full runtime includes catalogue preparation, track processing and position inference.

The lookup maps each ASCII digit to its value and a minus sign to one. It sums the first 68 columns exactly as the original does. Non-ASCII input follows the original digit conversion. This changes an inner loop in the numerical benchmark variant. [Implementation](../../../tools/pipeline_eval/variants/catalogue_checksum.py)

To rerun the position measurements and time each bound catalogue on an available local CPU, run from the repository root.

```sh
.venv/bin/python -m tools.pipeline_eval run --panel smoke --variant catalogue_checksum --jobs 2 --pin --out /tmp/tle-position
CPU=$(awk '/Cpus_allowed_list/ {print $2}' /proc/self/status | cut -d, -f1 | cut -d- -f1)
for recording in DS26-0036 DS29-0082
do
    taskset -c "$CPU" .venv/bin/python -m tools.pipeline_eval.qualification.catalogue_checksum \
        --case "$recording" --out "/tmp/tle-position/$recording-checksum.json"
done
```
