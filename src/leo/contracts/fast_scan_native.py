"""Native-rate fast analysis without the 2.5 MS/s predictor or its cutoff."""

from typing import Literal

from pydantic import model_validator

from leo.contracts.fast_scan import FastScanPolicyV1, FastScanSegmentResultV1, FastScanWindowResultV1


class FastScanPolicyV2(FastScanPolicyV1):
    schema_version: Literal[2] = 2
    mode: Literal["ungated"] = "ungated"
    sample_rate_hz: Literal[10_000_000] = 10_000_000
    window_samples: Literal[200_000] = 200_000
    predictor: Literal["disabled-unqualified-at-native-rate"] = "disabled-unqualified-at-native-rate"


class FastScanWindowResultV2(FastScanWindowResultV1):
    schema_version: Literal[2] = 2

    @model_validator(mode="after")
    def coherent_status(self):
        if self.scores or self.status == "skipped_fast_score":
            raise ValueError("native analysis cannot use an unqualified fast predictor")
        measured = [r.receiver_id for r in self.receivers]
        if len(set(measured)) != len(measured):
            raise ValueError("duplicate receiver results")
        if (self.status == "processed") != bool(measured):
            raise ValueError("only processed windows contain native GLRT results")
        return self


class FastScanSegmentResultV2(FastScanSegmentResultV1):
    schema_version: Literal[2] = 2
    policy: FastScanPolicyV2
    windows: tuple[FastScanWindowResultV2, ...]


def parse_fast_policy(document):
    return (FastScanPolicyV2 if document.get("schema_version") == 2 else FastScanPolicyV1).model_validate(document)


def parse_fast_result(document):
    return (FastScanSegmentResultV2 if document.get("schema_version") == 2 else FastScanSegmentResultV1).model_validate(document)
