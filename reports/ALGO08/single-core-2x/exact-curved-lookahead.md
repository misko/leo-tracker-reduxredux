# Frozen exact receiver, curved design and compressed-member hint

The research successor `sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f` composes three measured components. It inherits the all-factor exact receiver, full two-scan schedule, paired decoded SHA-256, wrapped longitude and terminal regional guard from `a54606…`. The existing two calibration arms, original search offer and screening center follow the same interfaces. A complete file comparison permits changes to the specification, experimental launcher and two measured source files. The receiver and all native libraries retain their parent digests. [Freeze receipt](measurements/exact-curved-lookahead-freeze.json)

| Component | Independent measured evidence |
|---|---|
| All-factor exact fractional score | Matches every deployed probe row on the 128-visit dense lower-pilot and public southern upper-pilot prefixes. Selected-score repair cost 2.84% and 0.39% more CPU respectively in the matched prefix comparisons. [Receiver transfer](receiver-fractional-score-transfer.md) |
| Curved likelihood design | Reproduces both deployed arm endpoints and owners on dense DS30-0008 and an independent public southern saved input. Dense saved-solver CPU moved from 56.16 to 53.64 seconds and elapsed time from 57.03 to 57.78 seconds in one pair. [Saved solver comparison](solver-curved-design.md) |
| One compressed-member hint | Two 16 MiB next-member hints saved a median 221.6 ms of cold acquisition elapsed time across three private full-size pairs. Each pair read the same charged bytes and reproduced the exact raw authority, probes and 282 selections. This is a generated XFS acquisition control. [Ingress trial](full-member-lookahead.md) |

`member_lookahead: true` requires paired SHA-256 ingress. It scopes the checked hint to the serial acquisition callback. The first visible window from each in-scope member can submit advice for the next manifest-listed member, capped at its first 16 MiB. Reading, decoding, checksum verification and observation ordering stay with the paired reader. The launcher performs no prelaunch reads of recording members. A platform without the advisory API uses the normal reader and reports zero hints. Acquisition returns `attempts`, `submitted`, `submitted_bytes`, `cpu_ns` and `wall_ns` in the launch diagnostics. Earlier specs omit the flag and run the original acquisition route. [Launcher](../../../tools/pipeline_eval/qualification/experimental_publication.py) · [Measured hint source](../../../tools/pipeline_eval/variants/experimental/receiver_member_lookahead.py)

The freezer binds the exact parent, the receiver transfer report, the curved solver’s two verified saved comparisons, the installed solver source pins and the full-size ingress evidence. Startup and component tests exercised module origin and digest validation, the default, unsupported advice and prior freeze reconstruction. The combined build has no paired timing or position result yet. [Freezer](freeze_exact_curved_lookahead.py) · [Component tests](../../../tests/pipeline_eval/test_freeze_exact_curved_lookahead.py)

## Reproduce the freeze

Use fresh bundle and receipt paths. The destination path enters the specification digest. The launcher is `reports/ALGO08/single-core-2x/run-candidate` inside the new bundle.

```sh
bench=/tmp/leo-algo08v2-2x-bench
PYTHONPATH=src:. python -BPs -m reports.ALGO08.single-core-2x.freeze_exact_curved_lookahead \
  "$bench/integration-fractional-absolute-all" "$new_bundle" "$new_receipt"
```

For an earlier curved-design freeze, give its freezer the original `81ce543a5` launcher through `--launcher-source`. The original launcher can come from the earlier bundle or a checkout of that commit. Its byte digest is checked before copying. The all-factor receiver parent was frozen by the separately pinned receiver recipe at `adbed2064`. [Earlier curved-design freeze](solver-curved-design.md#frozen-selected-score-successor) · [Receiver freeze recipe](receiver-fractional-absolute-score.md)
