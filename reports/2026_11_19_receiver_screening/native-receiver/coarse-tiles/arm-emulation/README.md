# ARM numerical qualification

Both cross-compiled kernels reproduced all **112 ordered seeds**, **two peer retries**, **17 integer passes** and **19 fractional passes** on each of the AArch64 and Cortex-A9 builds. All six historical held visits ran from raw stereo CI16 through the complete detector. Each candidate matched its same-target incumbent verifier bytes. The independent archive audit agreed on all distinct ranks and reported two equivalent seed reorderings for each build. [Per-visit parity](qualification.csv) · [Complete archive audit](archive-audits.json)

The largest retained coarse-score shift on either target was 2.59 × 10⁻⁹ for the phase-pair kernel and 5.91 × 10⁻⁸ for the symmetric-carrier kernel. The largest differences from the independently archived oracle were 7.79 × 10⁻¹⁴ in fractional margin, 3.01 × 10⁻¹³ samples in fractional timing and 0 Hz in fractional residual frequency. [Recorded numerical limits and observation clocks](archive-audits.json)

These were offline QEMU process runs. Physical board throughput and localization were unmeasured. The executable hashes and compiler flags are in the parent receipt. [Build lock](../build-lock.json) · [Native x86 timing](../README.md) · [Appendix seal](qualification-lock.json)
