# Shared model production deployment — 2026-10-16

`shared-scan-q-v2` is enabled in production. The dedicated `leo-fast-shared-position.service` automatically processes exported fast-scan TrackingInputs, including new arrivals and the historical backlog, newest first. It runs one bounded job at a time. Each input/model pair is processed once; failed or interrupted jobs remain explicit and are not automatically retried. Processing starts after a fast scan has exported its TrackingInput.

The immutable release is `/opt/leo-fast-auto/20261016-shared-r2`, with numerical source `f4d80d41edd84ca613a2e9ea02f11bf853fb8fc1`. It fits the full available CH1–8 observations using the shared satellite-probability model and fitted calibration coefficient c. Fresh sequential A and joint B fits supply two initial states; the lowest-objective independently accepted shared fit supplies the result. The production initializer is `generic-cold24-shape3-fresh-six-ab-v1`. It does not read DS labels, saved research fits, or configured reference positions.

This initializer differs from the completed DS21/DS22 research evaluation. **Deployment does not establish an accuracy improvement, a 0.5 km target, or superiority to either four-channel half.** Subsequent performance reports must evaluate this exact release and keep missing estimates in the denominator of the established cumulative-error plots.

Source fits retain their 15-second solver/20-second total budget. Final shared fits receive 60/65 seconds, with unchanged strict stationarity threshold 0.001. The complete attempt is capped at 1,200 seconds; the supervisor also bounds the whole process group. Unavailable estimates remain unavailable rather than being replaced with rejected endpoints.

## Validation and operations

Twenty-four numerical/runtime component tests, 31 integration/staging/API tests, and two frozen-source replay tests passed. Exact objective and gradient parity with the research oracle was checked. Immutable release smoke checks covered the service user, native extension, CLI, and API enabled/disabled behavior.

The original lower canary completed with an accepted B-source shared fit (stationarity 0.000720). The original upper canary exhausted the shorter v1 final-fit budget. Controlled replays reused the exact original sources, with no repeated discovery or source fitting: v2 preserved the lower result and accepted the upper B-source fit at stationarity 0.000916 in 28.70 seconds. These are convergence and operational checks, not position-accuracy measurements. See the [controlled upper replay](SHARED_PRODUCTION_UPPER_Q_BUDGET_V2.md).

Production activation initially exposed an output-directory ownership problem. The service now creates its owned publication directory before entering the service sandbox (`457491ad8`); it subsequently started normally. The API was restarted to expose the new namespace. The legacy fast-scan worker remained running with PID 2592250 throughout activation, and the concurrently deployed fast-orbits API routes were preserved. No RF collection or QNAP mutation was performed.

Results and progress are available at `/api/v1/fast-scan-shared-model` and `/api/v1/fast-scan-shared-model/{job_id}`. Outputs live under `/srv/bulk/leo/fast-scan-shared-model-v1/shared-scan-q-v2/jobs/`. Existing legacy products remain separately available; this change does not replace their UI displays.

The [deployment receipt](shared_production_deployment.json) records observed service state, the initial production job, immutable release hashes, and fresh end-to-end qualification status. It is a timestamped snapshot, not a claim that the backlog has completed. Release environment files: [worker](shared-production-20261016/r2/analysis-release.conf), [API](shared-production-20261016/r2/api-release.conf). The [original adapter design](SHARED_SCAN_PRODUCTION_ADAPTER.md) documents v1; the budgets and version above supersede its v1 settings.

The additional fresh end-to-end r2 upper canary completed successfully at 16:10:53 UTC after 409.43 seconds of inference. It repeated preparation, discovery, source fitting and final shared fitting using the staged release, and selected B with strict stationarity 0.000915812. Its objective and endpoint matched the controlled frozen-source replay. The qualification unit exited successfully.

## Rollback

Stop and disable only `leo-fast-shared-position.service`. Verify the API drop-in digest against the receipt, then remove only `/etc/systemd/system/leo-api.service.d/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-shared-position.conf`, run `systemctl daemon-reload`, and restart `leo-api.service`. This restores the preceding fast-orbits API overlay. Preserve both immutable releases and all result/qualification evidence. The legacy fast-scan worker does not need restarting.
