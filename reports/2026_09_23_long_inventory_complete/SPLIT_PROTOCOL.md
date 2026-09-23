# Long-duration grouped split, seed 20260923

Use complete eight-hour UTC bins inside the frozen inventory interval, containing
at least 40 nominal 300-second captures wholly inside their bin. These are five
groups spanning September 21 00Z through September 22 08Z. This threshold is an
observation-coverage criterion, not a measured track-quality or position criterion.

The September 21 00Z and 08Z groups have already had six sample recordings opened
for input qualification, with full qualification now running. Exclude both from
test assignment. Choose one test group using Random(20260923).choice from the
sorted remaining eligible groups. Shuffle the four remaining groups using the
same RNG and assign the first two to training and the other two to validation.
Keep all recordings in each group together. Record source hashes and exact IDs.

This is randomized assignment conditioned on known exposure, not chronological
splitting. Metadata for every group is visible. No test track evidence, candidate
fit, residual or geographic error may be opened until model selection is frozen.
We can assert no track evidence was opened in this work for that group; historical
production analysis exists, so we cannot assert it has never been seen anywhere.

Use the same predeclared nested 1/6/16/all-scan duration views within each group;
these are correlated views, not independent replicates. Report elapsed duration
and summed capture duration separately. Earlier recent-firmware experiments are
external development evidence. Only two validation groups and one test group
remain a small-sample limitation, and adjacency may share receiver conditions.
