# Frozen joint solver on the saved northern offers

The unchanged joint solver returned both northern containing fits and withheld both fits on the far omitted offer. The containing result used all **302 original v3 owners** and a complete 137-point grid. Horizontal error increased **0.066 / 0.083 km** while both curved RF residuals improved. Both increases stayed within the 0.25 km development allowance. Neither offer invoked repair or v3 fallback. [Frozen repair and gates](blind-joint-repair.md) · [Numeric summary](measurements/blind-joint-north-summary.json) · [Full receipts](measurements/blind-joint-north.json.gz)

| Northern offer and stage | Error km, `c = 0` / fitted | Curved RF RMS Hz, `c = 0` / fitted | Decision |
| --- | ---: | ---: | --- |
| Containing v3 terminal | 0.106 / 0.141 | 5.406 / 5.167 | Both returned |
| Containing candidate terminal | 0.172 / 0.223 | 5.385 / 5.151 | Both returned |
| Far omitted candidate diagnostic | 52.459 / 52.441 | 51.384 / 51.016 | Both compatible before the exterior check |
| Far omitted candidate and v3 terminal | — | — | Both withheld |

The containing fit used the same 285 curved and 17 predictive owners in both calibration arms. Its standard evidence packet replayed the exact objective with zero delta. On that support, fitting `c` lowered RMS by 0.234 Hz and increased horizontal error by 0.052 km. The distant offer began with 228 curved points, restored 34 using the frozen one-pass RF salvage, and accepted both diagnostic fits on those 262 curved points. Their west-bound endpoints activated the original exterior check. Both receivers supported the exterior and the terminal withheld for `both_receivers_support_far_exterior`. Truth entered after fitting. [Original public reference](../regional-release/scoring-key.json)

| Saved offer | Candidate CPU / elapsed s | Fresh v3 CPU / elapsed s | Candidate stage |
| --- | ---: | ---: | --- |
| North containing | 4.492 / 4.493 | 5.627 / 5.628 | 0.742 CPU s numerical evidence |
| North far omitted | 7.208 / 7.208 | 9.672 / 9.673 | 2.974 CPU s exterior check |

The candidate ran first in each pair and saved 20.2% and 25.5% CPU, respectively. The fresh controls reproduced the archived stock arm positions, owners, decisions and science digests. These are saved northern development offers, with one containing reference and one distant omission from the same recording. The small position regressions and the lack of independent near-omission coverage leave the release's site accuracy and withholding gates open. [Matched archived v3 inputs](measurements/aperture-summary.json)

The runner accepts the original sealed-offer names from the shared aperture input loader, and the scorer can select those receipts explicitly. The fit and repair source files match commit `d91390f38` byte for byte. Eight routing and fit tests passed. Under the same pinned, low-priority Gauss wrapper in the earlier report, run `blind_joint_trial.py` with `north-containing` and `north-far`, `--repair`, and fresh outputs. Then pass `--case north-containing --case north-far` to the scorer. [Reproduction settings](blind-joint.md#reproduction) · [Routing tests](../../../tests/pipeline_eval/test_algo08v3_blind_joint_routing.py)
