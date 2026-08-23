#!/usr/bin/env python3
"""Persist compact, reproducible database evidence for the fixed operational cohort."""

# ruff: noqa: E501 -- long SQL fragments are kept contiguous for audit readability.

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
START = "2026-08-23T07:03:41Z"
END = "2026-08-23T15:03:41Z"


def query(sql: str) -> object:
    result = subprocess.run(
        ("sudo", "-n", "-u", "postgres", "psql", "-X", "-d", "leo_tracker", "-At", "-c", sql),
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout.strip())


COHORT = f"""
with cohort_operations as (
  select *, substring(outcome from 'capture (cap-[^ ]+) committed') as session_id
  from acquisition_operation
  where scheduled_for >= '{START}'::timestamptz and scheduled_for < '{END}'::timestamptz
), cohort_runs as (
  select ar.* from analysis_run ar
  join cohort_operations op on op.session_id=ar.session_id
  where ar.trigger='new_capture'
)
"""


def main() -> None:
    evidence = {
        "schema_version": 1,
        "window": {"start": START, "end": END},
        "release_rows": query(
            "select coalesce(json_agg(row_to_json(x) order by x.created_at),'[]'::json) from "
            "(select id,code_revision,created_at from pipeline_release "
            f"where created_at between '{START}'::timestamptz - interval '1 hour' and '{END}'::timestamptz) x"
        ),
        "processing_job_states": query(
            COHORT
            + "select coalesce(json_agg(row_to_json(x) order by x.pipeline_lane,x.state),'[]'::json) "
            "from (select cr.pipeline_lane,pj.state,count(*) count,sum(pj.attempt_count) attempts,"
            "count(*) filter(where pj.attempt_count>1) retried_jobs from cohort_runs cr "
            "join processing_job pj on pj.run_id=cr.id group by 1,2) x"
        ),
        "failed_attempt_signatures": query(
            COHORT
            + "select coalesce(json_agg(row_to_json(x) order by x.count desc,x.signature),'[]'::json) "
            "from (select case "
            "when pja.error like 'LeaseLostError:%' then 'analysis run failed' "
            "when pja.error like 'ProcessingError: isolated analyzer exited without a receipt%' then 'isolated analyzer exited without receipt' "
            "when pja.error like 'RunRejectedError: ValueError: exclusive residual-Hough%' then 'residual-Hough proposal rejected' "
            "when pja.error like 'RunRejectedError: ValidationError:%KalmanTrajectoryTrackV1%' then 'Kalman frame order rejected' "
            "else left(coalesce(pja.error,''),160) end signature,count(*) count "
            "from cohort_runs cr join processing_job pj on pj.run_id=cr.id "
            "join processing_job_attempt pja on pja.job_id=pj.id where pja.state='failed' group by 1) x"
        ),
        "recovered_retries": query(
            COHORT
            + "select coalesce(json_agg(row_to_json(x) order by x.started_at),'[]'::json) from ("
            "select cr.pipeline_lane,cr.session_id,pj.id job_id,pj.stage_key,pj.attempt_count,pj.state,"
            "min(pja.started_at) started_at,max(pja.completed_at) completed_at,"
            "string_agg(coalesce(pja.error,'succeeded'), ' -> ' order by pja.attempt_number) history "
            "from cohort_runs cr join processing_job pj on pj.run_id=cr.id "
            "join processing_job_attempt pja on pja.job_id=pj.id where pj.attempt_count>1 "
            "group by cr.pipeline_lane,cr.session_id,pj.id,pj.stage_key,pj.attempt_count,pj.state) x"
        ),
        "duplicate_counts": query(
            COHORT + "select json_build_object("
            "'operation_keys',(select count(*) from (select operation_key from cohort_operations group by operation_key having count(*)>1) d),"
            "'session_lane_release_runs',(select count(*) from (select session_id,pipeline_lane,pipeline_release_id from cohort_runs group by 1,2,3 having count(*)>1) d),"
            "'run_stage_scope_jobs',(select count(*) from (select pj.run_id,pj.stage_key,pj.scope_key from processing_job pj where pj.run_id in(select id from cohort_runs) group by 1,2,3 having count(*)>1) d),"
            "'run_scope_kind_products',(select count(*) from (select ap.run_id,ap.scope_id,ap.kind from analysis_product ap where ap.run_id in(select id from cohort_runs) group by 1,2,3 having count(*)>1) d))"
        ),
    }
    (ROOT / "operational-database-audit.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
