# Counter UTC RC1: real IQ import acceptance

The 300-second, 10 MS/s archive `scan-fw-9af2dd5b20d987b2` was captured on
radio `104000b29905000e17000800065934759d` at `192.168.1.15`, running the
published counter-UTC RC1 firmware. All 2,138 planned visits were delivered:
10,262,400,000 IQ bytes, with no skipped, invalid or cancelled visits. Receiver
settings were restored. The separate production radio was not accessed.

The real importer verified every compressed and uncompressed IQ payload digest
and published `HostAdaptiveHopIqManifestV6` with `CounterUtcTimingV4`. Capture,
receipt and timing evidence retained the same radio identity. Reimport returned
the same session in 0.431 seconds without creating a second session.

- Source archive manifest: `sha256:78b362a4b2a21a96ae8da8b091fcbe8b1387b5ca9bbb73f4d58727af1522750e`.
- Published tracker manifest: `sha256:43be1b328fd456bcc2e053b8b071dfb7287508f0cee40d36ead27a40e3a6883e`.
- Valid samples: 2,565,600,000; full source envelope: 3,000,000,000 samples.
- Tracker importer source: `480f877ae237e2f8ed2880ca6d97a09cbe82bfa8`.
- Host capture started at PPU `60486cf6f318959e1d8f7fd78c5b4289127c7867`;
  subsequent typing/test-only changes do not alter capture behavior.

`timing_is_qualified_for_tle` remains false: hardware timing bounds lack a
calibration reference, radio serial and boot UUID. This is the expected result.
The test closes the full real-IQ import gap; it does not demonstrate absolute
UTC accuracy, measured TLE performance, or independent RF-marker calibration.

The initial import invocation refused a missing destination root before writing
a session. Creating the isolated local root allowed the same archive to import.
The older five-second smoke refusal remains valid under the unchanged
300-second complete-session contract.
