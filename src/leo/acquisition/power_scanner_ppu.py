"""Metadata conversion for the public PWR1 client; contains no IQ transport."""

from __future__ import annotations

from typing import Any

from leo.contracts.power_scanner import StandalonePowerResultV1


def power_measurements(status: dict[str, Any], key: str) -> list[dict[str, Any]]:
    from pluto_plus.standalone_power import PowerResult

    values = []
    for raw in status[key]:
        measurement = PowerResult.decode(
            raw, session=status["session"], generation=status["generation"]
        ).measurement()
        value = StandalonePowerResultV1(
            **measurement,
            table_sha256=f"sha256:{status['table_sha256']}",
            guard_samples=status["guard_samples"],
            adc12_qualified=status["adc12_qualified"],
            threshold_energy=tuple(status["threshold_energy"]),
            datapath_caps=status.get("datapath_caps"),
        )
        values.append(value.model_dump(mode="json"))
    return values
