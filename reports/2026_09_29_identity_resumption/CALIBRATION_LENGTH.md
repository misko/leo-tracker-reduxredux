# Does the longer decode explain poor matched-time coverage?

The census decoded four frames per excerpt, whereas the new matched-time tests
requested up to 15. Because recovery estimates drift and SSS channel response
using frame observations, changing the frame limit can change calibration. We
tested this concrete methodological explanation before interpreting recovery
failures as a limitation of the signal observations.

## Fixed replay

Replay the first candidate at the first selected excerpt from each of the five
simultaneous-track pairs, plus the two successful long-track excerpts that match
their original census visit. This is seven predetermined cases, with no search
over replacement visits or frame limits. Use exactly the saved candidate and
probe parameters, verify the reread raw-excerpt SHA256, and run the unchanged
decoder with a four-frame limit. The read-only process completed within its
180-second bound. Original outputs and golden fixtures were retained.

Changing frame count changes the deterministic random calibration/evaluation
split. Compare quality directly only on the shared evaluation frame, index 3.
The other frames are not interchangeable holdouts.

| Track / stored visit | Four-frame pilot coherence, frame 3 | Longer-decode coherence, frame 3 |
|---|---:|---:|
| DS7-F069-T0007 / 853 | 0.4182 | 0.4196 |
| DS7-F020-T0028 / 1094 | 0.4365 | 0.4338 |
| DS7-F035-T0033 / 1512 | 0.4755 | 0.4758 |
| DS7-F042-T0022 / 893 | 0.5190 | 0.5198 |
| DS7-F042-T0046 / 1817 | 0.4371 | 0.4062 |
| DS10-F010-T0031 / 1085 | 0.6067 | 0.6067 |
| DS10-F010-T0040 / 1517 | 0.5168 | 0.5189 |

All seven retain the same pass/fail outcome at the fixed >0.5 threshold.
The two successful controls reproduce the census's reported minimum coherence
values on this frame. F069 visit 853 gains one qualified evaluation frame in
the four-frame run, but it is outside the common evaluation set; this is not
evidence of a rescued paired comparison.

These observations do not support frame-count-dependent calibration as the main
explanation for poor matched-time coverage in the selected cases. They do not
prove calibration is identical at every carrier or validate all header signs.
No header identity claim, bit-error rate, or new semantic field follows.

## Reproduction and verification

`calibration_length.py` refuses to overwrite its result and records original and
new NPZ hashes, raw-excerpt hashes, receipt hashes, common-frame quality and its
own method hash. Run with:

```sh
sudo -n -g leo env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 180 /opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python -I /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_29_identity_resumption/calibration_length.py
```

Ignored `local/calibration-length/executed-recovery.py` preserves the exact source
matching `result.json` before line-wrap-only lint fixes. The focused test checks
that only shared held-out frames are compared and that disjoint partitions yield
no common frames. It and Ruff pass. Data remain ignored and uncommitted; no new
RF, production changes or golden-fixture changes were made.
