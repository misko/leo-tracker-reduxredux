# Generic recovery coverage

All193 members are accounted for. Partial progress is diagnostic; full-cohort position metrics remain withheld until full terminal and matched-position coverage.

| Dataset | Members | Terminal | Matched fitted-c positions | Matched c=0 positions |
|---|---:|---:|---:|---:|
|DS16|63|26|26|26|
|DS17|51|25|25|25|
|DS18|34|26|26|26|
|POST18-development|45|25|25|25|

`coverage-report.json` records every member/status, recovery qualification, trigger/fallback, runtime/source metrics and matched arms. Archived85 controls are distinct from current B7 baselines; frequency-fit effects are separate from position accuracy.

```json
{
  "full_membership": 193,
  "terminal_members": 102,
  "full_census_position_metrics_withheld": true,
  "arms": {
    "fitted-c": {
      "matched_position_count": 102,
      "missing_or_failed_positions": 91,
      "full_census_metrics_withheld": true
    },
    "zero-c": {
      "matched_position_count": 102,
      "missing_or_failed_positions": 91,
      "full_census_metrics_withheld": true
    }
  }
}
```
