# Sharing cyclic pilot filters across signed CFO

The native FFTW bank fits **32 shared inverse rows** in the projected warm callback budget and **16** in the measured cold CPU budget, after granting the existing oracle confirmation path. The two pinned pilot edges need at least **303 and 310** rows to retain 90% of mean template power on the admitted signed grid, even with the optimal mean-power basis. Testing off-grid CFOs raises that particular basis's requirements to **431 and 428**. At 32 rows, none of the 138 saved primary and residual factor CFOs retains half its template power. This fixed linear bank stops at the measured kernel and span screen. [Prespecified protocol](shared-ambiguity-protocol.md) · [Complete timing and coverage receipt](measurements/shared-ambiguity.json)

## Shared filters

For cyclic delay \(\tau\), the proposed score is the correlation between the input row and the 704-tap pilot modulated by signed CFO \(f\). Write the modulated template as \(p_f\). Approximate it using its projection into an \(R\)-dimensional span of pilot templates. The bank FFTs the input once. Each basis vector needs a single pointwise spectral multiply and inverse FFT to cover all timing phases. The carrier-specific response is a linear combination of the shared inverse rows. This shares work across signed frequency and across cyclic delay. The earlier carrier-bound experiment starts from individual timing hypotheses. The polyphase experiment changes the lag correlations' inverse co-ordinates. The raw shortlist and full differential scout operate on other statistics and miss weak residual support. [Carrier-row bounds](carrier-fft-bound.md) · [Polyphase timing](receiver-polyphase-timing.md) · [Raw shortlist](../single-core-2x/receiver-shortlist.md) · [Differential scout](differential-fold.md)

The kernel grants one perfectly aligned quarter-rate mode at no cost and zero work for recovering all the signed combinations, ranking, and copying output. It times the shared forward FFT, the full inverse rows, and the complex spectral multiplications. Both sequential in-place and batched FFTW plans execute on real complex values from each pinned pilot edge. The native code reproduces separate direct cyclic dot products across wrapped lag to within \(6.5\times10^{-9}\) in these trials. The 4,096-point sensitivity gives the method a smaller radix-2 transform and still fits the supported 3,333 lags and 704-tap linear aperture. [Native bank kernel](../../../tools/pipeline_eval/variants/experimental/receiver_shared_ambiguity.c)

The complete dense callback can use **0.581 ms/lane cold CPU** or **0.689 ms/lane projected warm elapsed**. The FFT bank alone is measured per folded mode per scout. Multiplying by 148/96 scouts per dense lane and charging the previous fixed guarded oracle confirmation at **0.368 ms/lane** leaves **0.138 ms/scout cold** and **0.208 ms/scout warm** for the search. These allowances include the existing reader outside the callback and assume the favorable earlier solver and publication scenarios. They already grant free original I/Q alignment and perfect empty-lane routing. The original exact verifier cost more than the whole callback with oracle proposals. [Complete acquisition split and boundary](low-bit-pilot.md) · [Original-sample verifier and residual cost](directed-verifier.md)

## Limits of the linear span

Normalize the template energy to one. For an orthogonal projector \(P\), the retained power of \(p_f\) is \(\|P p_f\|^2\). Let \(F\) of the \(N\) DFT bins lie in the signed band. The band-average retained power cannot exceed

\[
  \frac{N}{F}\sum_{j=1}^R \operatorname{sort}(|p|^2)_j.
\]

Summing over the full DFT period gives \(N\sum_t |p_t|^2 P_{tt}\) by Parseval. Restricting to the band discards nonnegative terms. Since the diagonal of a rank-\(R\) orthogonal projector lies in \([0,1]\) and sums to \(R\), taking the largest \(R\) tap powers gives the displayed bound. The same lower bound on total rank applies to a bank that uses several local bases and collects their inverse rows. A nonlinear filter or a method that avoids forming complete rows has a different cost model.

The sum of the leading eigenvalues of the weighted signed-template covariance gives the actual best mean retained power of any linear span. That necessary rank can be smaller than the rank needed at every CFO. The last column per edge checks quarter-bin offsets between all training bins against the mean-optimized basis. It is a result for that basis only.

| Required power | Lower Parseval floor | Lower best-mean floor | Lower off-grid minimum | Upper Parseval floor | Upper best-mean floor | Upper off-grid minimum |
|---|---:|---:|---:|---:|---:|---:|
| 50% | 66 | 103 | 183 | 71 | 107 | 187 |
| 90% | 166 | 303 | 431 | 174 | 310 | 428 |

With the 4,800-point kernel and all downstream work free, the largest tested warm-admissible rank is 64 on both edges. Parseval gives upper bounds on its band-average power of **49.1% lower and 46.4% upper**, even for an ideal span. The optimal-mean bases actually retain 36.2% and 34.9% on average. At the confirmation-inclusive warm rank of 32, the minima on held-out quarter bins are **0.160 and 0.150**. This span constraint precedes interpolation design. More accurate interpolation among the same shared rows cannot restore the omitted components. [Weighted covariance and numerical checks](shared_ambiguity_trial.py)

The sequential 4,800-point plan was the faster arm at the budgeted ranks, with 16 rows taking 0.101–0.103 ms/scout, 32 taking 0.195–0.197 ms and 64 taking 0.389–0.394 ms. At 320 rows it took 2.70–2.92 ms/scout. The shorter transform took **0.754–0.757 ms/scout** at the 90% Parseval floors of 166 and 174 rows, or at least 1.16 ms/lane at the measured scout mix, before reconstruction or verification. At the stronger mean-optimal 90% floors of 303 and 310 rows the shorter transform alone cost **1.444–1.760 ms/scout**. The exact-pilot rank requirement exceeds the whole budget even under this favorable transform sensitivity. [Five native repetitions and both FFT plans](measurements/shared-ambiguity.json)

### Saved factor support and interference

Scores at saved signed CFOs use the original installed factor records captured in the directed replay. The archived weak index gives the pilot edge. Only factor metadata and the index were opened. The span is fitted on the entire signed design grid and sees no recording, timing, site or factor data. At warm rank 32 the 22 weak residuals have template power **0.187–0.220** and the 28 dense residuals **0.202–0.222**. The 36 weak primaries span 0.185–0.227, and the 52 dense primaries 0.202–0.228. None reaches 50%, including with rank 64 and free confirmation. This is support in the proposed waveform representation. It is not a measured detection recall. [Saved factor rows in the receipt](measurements/shared-ambiguity.json)

In four synthetic two-pilot cases per edge, a 10%-RMS companion has projected desired response **0.018–0.023** against 0.100 for the corresponding full template. The close, equal-delay case shows strong leakage greater than the weak response for both the full and projected templates. The widely separated upper-edge case with 32 quarter-rate samples of delay changes strong leakage from **0.0025 to 0.0217**, exceeding the 0.0191 projected weak response. Rescaling the projected filter would amplify its desired response and leakage together. The rolled comparison and full responses are retained in the receipt. These synthetic projections do not use the planted timing or CFO to nominate a waveform, run a receiver gate, or infer positions.

This screen rules out the tested shared full-row bank within the whole callback budget. It does not bound sparse transforms that select and evaluate individual lag-frequency regions by a different statistic. No raw waveform replay, position solve, or release change was needed for this decision.

## Reproduce

```sh
tree=/home/mouse9911/gits/leo-tracker-reduxredux
bench=/tmp/leo-algo08v2-2x-bench
work=$(mktemp -d /var/tmp/leo-v3-shared-ambiguity.XXXXXX)
lock() {
  flock -x "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 timeout 35s \
    env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="$PWD:$PWD/src" "$tree/.venv/bin/python" -BPs "$@"
}
lock -m reports.ALGO08.v3.shared_ambiguity_trial "$work/kernel.so" /opt/leo-algo08/current/assets \
  reports/ALGO08/v3/measurements/low-bit-pilot.json \
  reports/ALGO08/v3/measurements/directed-verifier.json.gz \
  "$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip"
lock -m pytest -q tests/pipeline_eval/test_shared_ambiguity.py
```

Four component tests passed, covering the Dirichlet covariance, Parseval rank, total callback arithmetic, and direct native cyclic correlations with signed CFOs.
