# Wave3 first8/last8 frozen-input audit

Read-only metadata and hash audit; no IQ, preparation, score, or reference
artifact was accessed.

- `inputs-first8-last8-ready-v1.json` hashes to
  `19d831221ae383bc2477fdcf0993f784d36faa6b36fa65cb783a5ffcc2da7403`.
  It covers all 88 plan captures: 16 ready and 72 unavailable.
- Its first eight capture records are byte-for-byte equal to the prior frozen
  first-eight input. The last eight each bind one export, manifest, and bank;
  their session and track-export digests agree with the frozen artifact links.
  Eligible-mask exclusions remain bank-local and are not silently dropped.
- The original 1,200-second lease receipt remains preserved. The independent
  completion receipt for single088 records a reused export and a successful
  88.585589-second bank within its stated 240-second cap.
- Singles081 through 087 each have a persisted seal. At audit time, the
  single088/group8-11 directory has requests and the single088 response, but no
  persisted group results or seal; group11 is therefore pending, not complete.

No binding defect was found in the inspected frozen inputs. This report makes
no claim about pending group11 execution.
