import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { PositionMethods } from "./PositionMethods";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("shows all conditional methods and truth-only error", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({
    session_id: "scan-test", state: "complete", manifest: {
      document: {
        session_id: "scan-test", input_manifest_sha256: "sha256:input",
        reference_position: { source: "user-provided-report-reference", latitude_deg: 37.8, longitude_deg: -122.4 },
        methods: [
          { method: "expanded-doppler", state: "diagnostic", latitude_deg: 37.81, longitude_deg: -122.41, horizontal_error_m: 1234, reasons: [] },
          { method: "orbit-corrected", state: "failed", latitude_deg: null, longitude_deg: null, horizontal_error_m: null, reasons: ["UTC is unqualified"] },
          { method: "identity-mixture", state: "insufficient", latitude_deg: null, longitude_deg: null, horizontal_error_m: null, reasons: ["too few identities"] },
        ],
      },
      artifacts: [
        { method: "expanded-doppler", sha256: "sha256:a" },
        { method: "orbit-corrected", sha256: "sha256:b" },
        { method: "identity-mixture", sha256: "sha256:c" },
      ],
    },
  }) }));
  render(<PositionMethods sessionId="scan-test" inputDigest="sha256:input" />);
  expect(await screen.findByText(/1.234 km from the user-supplied reference/)).toBeInTheDocument();
  expect(screen.getByText(/not GPS measurements/)).toBeInTheDocument();
  expect(screen.getAllByRole("img")).toHaveLength(3);
  expect(screen.getByText(/UTC is unqualified/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Download position methods JSON" })).toBeInTheDocument();
});

it("shows pending and rejects a mismatched capture", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({
    session_id: "scan-test", state: "pending", manifest: null,
  }) }).mockResolvedValue({ ok: true, json: async () => ({
    session_id: "other", state: "pending", manifest: null,
  }) }));
  render(<PositionMethods sessionId="scan-test" />);
  expect(await screen.findByText("Position method evidence is pending.")).toBeInTheDocument();
});
