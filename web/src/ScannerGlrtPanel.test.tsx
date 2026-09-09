import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ScannerGlrtPanel } from "./ScannerGlrtPanel";
import { getScannerGlrt } from "./api";
import type { ScannerGlrtPublicationV1 } from "./api";

function publication(sessionId = "scan-glrt", count = 1): ScannerGlrtPublicationV1 {
  const start = 9007199254741011n;
  return {
    schema_version: 1, kind: "scanner_glrt_publication", session_id: sessionId,
    input_manifest_sha256: `sha256:${"c".repeat(64)}`, algorithm_sha256: "a".repeat(64),
    configuration_sha256: "b".repeat(64), published_utc_ns: "1788870000000000001", error: null,
    evidence: {
      session: "123", generation: "456", negotiated: true, mode: "unqualified-evidence",
      source_terminal_attested: true, final_received: true, expected_results: count,
      dropped_results: 0, result_sequence_limit: count, delivery_complete: true,
      classification_complete: false, error: null,
      results: Array.from({ length: count }, (_, i) => ({
        sequence: String(i), visit: String(i), valid_start: String(start),
        valid_end: String(start + 300000n), search_start: String(start),
        search_end: String(start + 300000n), confirmation_start: String(start + 1n),
        confirmation_end: String(start + 50001n), rate_hz: 2500000,
        channel: 1, edge: "lower", rx: 1, verdict: "unavailable", reason: "unqualified_classifier",
        search_window_mask: 63, exact_score: 0.25, control_score: 0.06, margin: 0.19,
        cfo_hz: 173123, epoch_sample_counter: String(start + 318n),
        fractional_offset_samples: 0.375, cpu_ms: 64, wall_ms: 70,
      })),
    },
  };
}

function respond(value: unknown, status = 200): Response {
  return { ok: status === 200, status, json: async () => value } as Response;
}

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("radio-side GLRT", () => {
  it("presents explicit positive-only detections without implying absence", async () => {
    const value = publication();
    value.evidence!.mode = "positive-only-v1";
    value.evidence!.classification_complete = true;
    Object.assign(value.evidence!.results[0], { verdict: "starlink", reason: "complete" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(value)));
    render(<ScannerGlrtPanel sessionId="scan-glrt" />);
    await screen.findByText("Starlink");
    expect(screen.getByText(/Positive-only detection/)).toHaveTextContent("do not establish signal absence");
    expect(screen.queryByText("No signal")).not.toBeInTheDocument();
  });

  it("rejects an absence claim from the positive-only profile", async () => {
    const value = publication();
    value.evidence!.mode = "positive-only-v1";
    Object.assign(value.evidence!.results[0], { verdict: "no_signal", reason: "complete" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(value)));
    await expect(getScannerGlrt("scan-glrt")).rejects.toThrow(/cannot assert signal absence/);
  });

  it("shows unqualified results independently from delivery, duty and exact epoch", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(publication())));
    render(<ScannerGlrtPanel sessionId="scan-glrt" />);
    await screen.findByText("Unqualified measurements — not Starlink classifications.");
    expect(screen.getByText(/1\/1 results delivered/)).toHaveTextContent("classification incomplete");
    expect(screen.getByText(/Screen 6\/6/)).toHaveTextContent("confirm 20.0 ms");
    expect(screen.getByText("9007199254741329")).toBeInTheDocument();
    expect(screen.getByText("+0.3750 samples")).toBeInTheDocument();
    expect(screen.getByText("173.123 kHz")).toBeInTheDocument();
    expect(screen.queryByText("No signal")).not.toBeInTheDocument();
    expect(screen.getByText(/compute times are not measured scanner duty/)).toBeInTheDocument();
  });

  it("treats missing history as unknown, not a negative detection", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(null, 404)));
    render(<ScannerGlrtPanel sessionId="scan-glrt" />);
    await screen.findByText(/No on-radio GLRT evidence was recorded/);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText(/Signal presence is unknown/)).toBeInTheDocument();
  });

  it("shows API failure without declaring the recording failed", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(null, 409)));
    render(<ScannerGlrtPanel sessionId="scan-glrt" />);
    await screen.findByText(/GLRT evidence request failed \(409\)/);
    expect(screen.getByRole("status")).toHaveTextContent("not a no-signal result");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows a durable detector failure without inventing rows or absence", async () => {
    const value = publication();
    value.evidence = null;
    value.error = "radio supplied no GLRT evidence after capture";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(value)));
    render(<ScannerGlrtPanel sessionId="scan-glrt" />);
    await screen.findByText(/radio supplied no GLRT evidence/);
    expect(screen.getByRole("status")).toHaveTextContent("not a no-signal result");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("paginates a bounded result inventory", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(publication("scan-glrt", 51))));
    render(<ScannerGlrtPanel sessionId="scan-glrt" />);
    await screen.findByText("Showing 1–50 of 51");
    expect(screen.getAllByRole("row")).toHaveLength(51);
    fireEvent.click(screen.getByRole("button", { name: "Next GLRT results" }));
    expect(screen.getByText("Showing 51–51 of 51")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(2);
    expect(screen.getByText("50 · CH1L")).toBeInTheDocument();
  });

  it("discards an old session response even when fetch ignores cancellation", async () => {
    let finishOld: (value: Response) => void = () => {};
    const oldResponse = new Promise<Response>((resolve) => { finishOld = resolve; });
    vi.stubGlobal("fetch", vi.fn().mockReturnValueOnce(oldResponse)
      .mockResolvedValueOnce(respond(publication("new-session"))));
    const view = render(<ScannerGlrtPanel sessionId="old-session" />);
    view.rerender(<ScannerGlrtPanel sessionId="new-session" />);
    await screen.findByText("new-session");
    await act(async () => { finishOld(respond(publication("old-session"))); });
    expect(screen.queryByText("old-session")).not.toBeInTheDocument();
  });

  it("retains partial-delivery failures explicitly", async () => {
    const value = publication();
    value.evidence!.delivery_complete = false;
    value.evidence!.final_received = false;
    value.evidence!.error = "missing terminal result frame";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(value)));
    render(<ScannerGlrtPanel sessionId="scan-glrt" />);
    await screen.findByText(/missing terminal result frame/);
    expect(screen.getByText(/1\/1 results delivered/)).toHaveTextContent("delivery incomplete");
  });

  it("never renders rounded counters or unqualified positive claims", async () => {
    const rounded = publication();
    Object.assign(rounded.evidence!.results[0], { epoch_sample_counter: 9007199254741328 });
    const positive = publication();
    positive.evidence!.results[0].verdict = "starlink";
    for (const value of [rounded, positive, { ...publication(), session_id: "wrong" }]) {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(value)));
      await expect(getScannerGlrt("scan-glrt")).rejects.toThrow();
    }
  });

  it("does not overlap slow polls and cancels on unmount", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn().mockReturnValue(new Promise(() => {}));
    vi.stubGlobal("fetch", fetcher);
    const view = render(<ScannerGlrtPanel sessionId="scan-glrt" />);
    await act(async () => { vi.advanceTimersByTime(60000); });
    expect(fetcher).toHaveBeenCalledTimes(1);
    const signal = fetcher.mock.calls[0][1].signal as AbortSignal;
    view.unmount();
    expect(signal.aborted).toBe(true);
    vi.useRealTimers();
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  });

  it.each([
    { verdict: "unknown-status" }, { exact_score: null }, { margin: "0.19" },
    { cpu_ms: -1 }, { rate_hz: 0 }, { channel: 5 }, { edge: "other" },
    { search_window_mask: 64 }, { reason: null }, { confirmation_end: "1" },
    { cfo_hz: Number.NaN }, { fractional_offset_samples: 3 },
  ])("contains malformed measurements inside the GLRT panel: %j", async (patch) => {
    const value = publication();
    Object.assign(value.evidence!.results[0], patch);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(value)));
    render(<ScannerGlrtPanel sessionId="scan-glrt" />);
    await screen.findByText(/GLRT evidence unavailable/);
    expect(screen.getByRole("status")).toHaveTextContent("not a no-signal result");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByText("No signal")).not.toBeInTheDocument();
  });
});
