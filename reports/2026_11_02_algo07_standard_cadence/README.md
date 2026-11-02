# Standard ALGO07 fast analysis and acquisition cadence

ALGO07 is the standard fast-scan localization and figure source. Older B7/Hard60, shared-model and experimental outputs remain available in a collapsed historical section, with their original contracts and artifacts intact.

The standard card reports the actual selected endpoint, retained model on fallback, both calibration arms, native point coverage, track/family counts and conditional residual RMS. A separately attached user-confirmed evaluation reference can report geographic error after fitting. Missing references remain explicitly unavailable; no reference is supplied to numerical inference.

Eight new PNGs are published atomically for each completed ALGO07 result: CH1–4 and CH5–8 GLRT/selected owners/orbital predictions; both bands' unassociated GLRT and remaining graph polynomials; both bands' residuals; RMS for every associated fragment; and both published positions in the 25 × 25 km region. The immutable manifest binds all image digests to the scientific terminal, input, native observations, tracks and both ownership maps. The browser requests digest-qualified PNG URLs, so a previous algorithm's cached image cannot silently appear as the current one.

The rendering process reconstructs the published model, checks both endpoints and RF objectives, and reports every published owner. It performs no position or satellite search. For predictive phase mixtures, diagnostic curves use conditional MAP predictions rather than claiming a joint measurement posterior. Figure frequency coordinates are the original native measured CFO, including receiver corrections in the prediction. Evaluation metadata stays outside the scientific terminal.

The automatic fast pipeline now finishes when the ALGO07 publication is complete. It exports the same qualified GLRT evidence and lets the existing ALGO02→ALGO07 workers consume their existing public ports. It does not run the older full diagnostic pipeline by default. The installed native-rate GLRT source is preserved byte-for-byte except for the orchestration overlay and its new presentation/reconciliation dependencies.

The scheduler retains the existing five-minute capture and 7.5-minute inactive gap. Analysis backlog no longer gates acquisition. Capture still requires the acquisition authority, its pause/ownership locks, the pipeline lock and a 30 GB recording-filesystem reserve; the recorder retains its own native-rate full-capture reserve checks. No manual or extended RF campaign is introduced.

Abandoned operational recording states are reconciled only while the acquisition authority can be exclusively claimed and the real checkpoint is at least 30 minutes old. Discovery timestamps do not establish capture liveness. Invalid old checkpoints remain evidence of interruption; their IQ and checkpoint bytes are never changed or fabricated as sealed captures. Live acquisition ownership and recent checkpoints prevent reconciliation.

Deployment verification, exact runtime paths, all PNG checks and observed normal timer starts are recorded in the accompanying verification receipt. Rollback removes only the newly installed API, watcher and capture-orchestration overrides, stops the standard-figure worker, and restores the preceding service commands. Existing scientific terminals and image namespaces are preserved.
