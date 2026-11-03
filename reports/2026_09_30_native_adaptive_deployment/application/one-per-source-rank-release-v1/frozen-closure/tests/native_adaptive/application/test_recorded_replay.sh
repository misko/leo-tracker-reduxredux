#!/usr/bin/env bash
set -euo pipefail
binary=${1:?binary required}
projection=${2:?projection TSV required}
targets=${3:?target metadata required}
tles=${4:?TLE catalogue required}
reference=${5:?reference candidates required}
search=${6:?search metadata required}
diagnostic=${7:?diagnostic TSV path required}
output="$($binary "$projection" "$targets" "$tles" "$reference" "$search" "$diagnostic")"
[[ "$output" == *'"schema":"leo-recorded-session-replay/v2"'* ]]
[[ "$output" == *'"source_rows":24681'* ]]
[[ "$output" == *'"projected":394'* ]]
[[ "$output" == *'"queue_dropped":0'* ]]
[[ "$output" == *'"tracks":11'* ]]
[[ "$output" == *'"reference_membership_exact":true'* ]]
[[ "$output" == *'"orbit_records":11129'* ]]
[[ "$output" == *'"scored_points":1'* ]]
[[ "$output" =~ \"matched_tracks\":[1-9][0-9]* ]]
[[ "$output" == *'"server_score_parity_claimed":false'* ]]
[[ "$output" == *'"stage_timing_ms":{"load_validate":'* ]]
for stage in all_row_prefix_projection selected_ingress_drain publish \
  reference_diagnostic orbit_build search_begin search_resume total; do
  [[ "$output" == *"\"$stage\":"* ]]
done
[[ "$(wc -l < "$diagnostic")" -eq 151 ]]
[[ "$(head -n 1 "$diagnostic")" == $'track_index\ttracklet_id\tsupport_digest\tpartition_seed\tpoint_index\tcandidate_id\tobservation_id\tsupport_start_utc_ns\tsupport_center_utc_ns\tsupport_end_utc_ns\tmoment2\tmoment2_bits\tmoment3\tmoment3_bits\ttraining\ttime_s\tmeasured_hz' ]]
printf '%s\n' "$output"
