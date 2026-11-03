# Archived detector-quality availability pilot

Corrected binding run: the first attempt in `2026_09_29_quality_metadata` compared raw CFO with canonical dealiased CFO and failed before producing any sidecar. Preserve those receipts. This run binds baseline `measured_hz` to the reconstructed point's `normalized_dealiased_cfo_hz`, matching the archived public numerical-input implementation. Retain raw CFO, canonical dealiased CFO, relative alias index, and both raw/canonical uncertainty conventions. This is an implementation correction, not an outcome-driven scientific retry. All selection and limits remain unchanged.

Select the first chronological scan of each existing N24 pool, without reference or fit-quality filtering. Through the pinned legacy public read-only tracking input port, reconstruct the original candidate projection and track graph. Bind every exported track point to its baseline track ID, time, measured frequency, receiver, channel, RF and visit. Require original capture and analysis manifest digests. Read cached analysis only; no IQ reads or new radio collection.

Export per-point candidate/source-group identity, candidate rank, exact score, control score, margin, standard uncertainty and physical support duration into a new research sidecar. Do not modify the existing persisted export contract or source inputs. Verify pinned public-module hashes against the previously archived runtime environment.

Report field coverage and variation. The legacy standard uncertainty is computed as hypot(400 Hz, 15000 Hz/s × half the scan timing bracket); it is not assumed to be a calibrated per-point CFO variance. Detector score or margin is likewise not automatically a frequency variance. No weighting, geographic fit, reference outcome, or accuracy claim is made in this availability pilot.

One scan per DS, 60-second process deadline each, sequential reads, no retries. No QNAP mutations, production changes or publication.
