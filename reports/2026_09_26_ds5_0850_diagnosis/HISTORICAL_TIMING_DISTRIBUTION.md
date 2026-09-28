# Historical TLE equivalent-timing distribution

The figure uses the existing 10,162 distinct element-epoch pairs from 257 satellites, pooled descriptively across historical training and validation groups. Each pair has equal weight; pairs from the same satellite are correlated. No prior is refitted and no observations are trimmed.

Equivalent timing is the first-order along-velocity projection of the difference between two TLE-propagated positions at a common epoch. It is **not** a verified orbital error, an observed receiver-clock correction, or exactly the same quantity as a fitted receiver-Doppler time shift. Large orbital disagreements need particular care because the first-order approximation can be poor.

For older elements aged 12–24 hours, the observed median is -0.137 seconds and the central 90% interval is **-4.059 to +1.189 seconds**. Of 1,296 pairs, **six (0.463%) have absolute equivalent timing at least 41.9 seconds**, including **two positive** differences at least +41.9 seconds. These six pairs involve five satellites; all are in the historical training partition (6/1,086), and none is in the satellite-disjoint validation partition (0/210).

The existing t4 prior assigns only 3.303e-7 probability (0.000033%) outside +/-41.9 seconds. Its tail is therefore much thinner than the descriptive pooled historical frequency, by about 14,018 times at this threshold. The earlier very small probability was a statement about this fitted prior, **not an empirical historical event rate**. Robustly fitting the central distribution did not capture the observed tail adequately.

This supports investigating a better tail/mixture model and the provenance of large TLE disagreements. It does not prove that a +41.9-second RF fit is a correct association or a valid physical correction. Under 12 hours, there are only 12 historical pairs, so a tight young-element prior remains insufficiently supported.

Artifacts:

- `historical_timing_distribution.png` / `.pdf`: signed empirical distributions by age, and the 12–24-hour absolute-tail comparison.
- `historical_timing_distribution.json`: full age-bin quantiles, tail counts, split accounting and source digest.
- `plot_historical_timing.py`: reproducible figure generation from the frozen archive-pair artifact.
