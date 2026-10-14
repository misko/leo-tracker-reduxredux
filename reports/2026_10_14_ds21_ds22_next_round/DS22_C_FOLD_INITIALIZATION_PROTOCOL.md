# DS22-075 randomized training-block initialization

This prospective conditional-development experiment changes initialization, not the likelihood, priors, bank, or acceptance threshold. The original full-training discovery and calibration frame remain shared. It does not use held observations, locked cases, or reference-selected seeds.

The immutable helper `model_a_randomized_block_folds` resets `default_rng(20261014)` for this recording, permutes sorted unique `floor(original observation time / 20)` blocks, and assigns permutation ordinal modulo two. The complete map, row assignment hash and counts are persisted before fitting. There is no redraw or support balancing.

Both conditional and propensity arms use the original C-all nongeographic state at each original C-all, C-low and C-high training-selected geography. Propensity coordinates start at zero. Each geography retains its original 25 km search disk. All twelve fixed-geography profiles (two arms, two folds, three positions) must terminate and seal before any continuation. Only accepted complete fold states receive one full-training free-geography continuation under the same arm and disk. Maximum added cost is twelve profiles plus twelve continuations, each 20 seconds and 600 optimizer iterations. This is not a 600-objective-call cap. Independent strict KKT acceptance remains 0.001; failed calls are preserved and never retried.

The original accepted conditional full-data incumbent remains eligible after exact objective/NLL replay. The prior propensity arm has no accepted incumbent. Selection is by full-training objective among accepted free states within each arm; fixed fold scores never select the final position. Total objectives are not compared across likelihood arms.

Qualification uses 190 wrapper closure and finite-difference objectives plus one incumbent replay (191 actual calls; cap 195), with a 120-second internal cap. It checks raw/conditional normalization, zero-tail nesting, original gradients/posteriors, every propensity derivative on both folds, own-disk feasibility and unchanged starts. Each arm/fold fitting unit permits at most three fits under 180-second internal, 195-second TERM and 200-second KILL limits. At most four units run concurrently. Any fitter initializer adjustment above 1e-12 is refused as an explicit admission failure, not silently projected. No failed original experiment is rerun.

Final evaluation requires every unit seal and the global seal first. Distances remain comparisons against the configured, unconfirmed station. Historical raw full and shared-discovery half results are context only, not eligible selectors or matched halves of these new models.

## Separate C019 coverage limitation

Independent replay of the original C019 prior and six recorded disk centers places the configured station at native XY (-87.0357958832, -80.9908603467), 118.889651 km from the prior center and inside its 250 km radius. Every original 25 km disk excludes that point. Minimum planar clearance is 79.784175 km at start 4; current anchor disks 0 and 5 have clearances 129.724816 and 203.272401 km. This post-seal diagnosis does not choose new seeds. C019 needs a separate training-only discovery coverage control; this protocol makes no C019 numerical changes.
