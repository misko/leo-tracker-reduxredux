# Compact conditional input contract

Use model_rows.json for the existing rowwise directional baseline and conditional outcome: a detected anchor's counterpart is matched or missing in its exact simultaneous receiver probe. It contains the UTC observation time, anchor margin, receiver/lane/rate nuisance fields, track identity, and posterior-mean east/up direction for all 10,369 eligible rows.

Join it to associations.json on session_id, track_id, and observation_id = projected_observation_id. That file materializes three candidate-specific azimuth/elevation trajectories, training-only Doppler weights and RMS values at 25,323 exactly aligned support/propagation times. Sort those rows within track by UTC to form temporal features. This comparison requires no source reread or LOS regeneration.

The compact inputs do not contain per-held-observation frequency log likelihood or an ID-keyed raw CFO table. Those are not needed for the conditional reception test. If a later launch requires CFO, derive it read-only through the existing source_links.py graph-resolution functions, freeze the result and preserve the current frequency masks before scoring.

The endpoint remains conditional on a detected anchor. It cannot create a target-level neither class or identify first/last reception ordering. The existing direction branch is known-roof-position diagnostic evidence; paired receiver mapping and nominal +/-10 degree axes remain provisional.
