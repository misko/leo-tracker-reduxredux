import { act, cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { FastScanView } from "./FastScanView";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });
it("embeds a selected recording and discovers its GLRT result after sealing", async () => {
  vi.useFakeTimers(); let published = false;
  const report = { run_id: "run", recording_name: "selected-fast", window_count: 2,
    counts: { processed: 1, skipped_fast_score: 1, invalid_capture: 0 },
    policy: { mode: "gated", threshold: .0132, margin_gate: .025, strong_margin: .1 },
    rf_mapping_authorities: ["hypothesis"], time_basis: "relative", channels: [], points: [], session_id: "tracking-id" };
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ ok: true, json: async () =>
    url.endsWith("/automatic") ? { items: [{ recording_id: "selected-fast", state: published ? "tracking" : "recording" }] }
      : url.includes("?") ? { items: published ? [report] : [] } : report })));
  await act(async () => { render(<FastScanView recordingId="selected-fast" renderTracking={id => <p>{id}</p>} />); });
  expect(screen.getByRole("status")).toHaveTextContent("recording");
  expect(screen.queryByLabelText("Recording")).not.toBeInTheDocument();
  published = true;
  await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
  expect(screen.getByText("tracking-id")).toBeInTheDocument();
  expect(screen.getByText(/2 visits: 1 processed/)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Actual channel visits" }).closest("header"))
    .toHaveClass("recording-heading", "scanner-heading");
  const diagnostics = screen.getByText("Fast-score diagnostics and channel activity").closest("details")!;
  expect(diagnostics).not.toHaveAttribute("open");
  expect(screen.getByText("tracking-id").compareDocumentPosition(diagnostics))
    .toBe(Node.DOCUMENT_POSITION_FOLLOWING);
});
it("distinguishes gated windows from GLRT activity and offers channel-colored plots", async () => {
  const report = { run_id: "run", recording_name: "lower", window_count: 2,
    counts: { processed: 1, skipped_fast_score: 1, invalid_capture: 0 },
    policy: { mode: "gated", threshold: .0132, margin_gate: .025, strong_margin: .1 },
    rf_mapping_authorities: ["hypothesis"], time_basis: "relative sample counter",
    channels: [{ channel: 8, receiver_id: 0, processed: 1, skipped: 1, active: 1, strong: 1 }],
    points: [{ channel: 8, receiver_id: 0, visit: 2, time_s: .3, score: .02, margin: .2, cfo_hz: 1000 }] };
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ ok: true,
    json: async () => url.endsWith("/automatic") ? { items: [] }
      : url.includes("?") ? { items: [report] } : report })));
  render(<FastScanView />);
  expect(await screen.findByText(/2 visits: 1 processed/)).toBeInTheDocument();
  expect(screen.getByText(/A skipped window has no GLRT/)).toBeInTheDocument();
  fireEvent.click(screen.getByText("Fast-score diagnostics and channel activity"));
  expect(screen.getByRole("img", { name: "RX1 CFO over time" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Plot"), { target: { value: "score" } });
  expect(screen.getByRole("img", { name: "RX1 fast score versus GLRT margin" })).toBeInTheDocument();
});

it("keeps shared artifacts available when the fast report request fails", async () => {
  const summary = { run_id: "run", recording_name: "capture" };
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({
    ok: url.includes("?") || url.endsWith("/automatic"), status: 503,
    json: async () => ({items: url.endsWith("/automatic")
      ? [{ recording_id: "capture", state: "complete", session_id: "shared-session" }]
      : [summary]}),
  })));
  render(<FastScanView recordingId="capture" renderTracking={id => <p>Artifacts: {id}</p>} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("503");
  expect(screen.getByText("Artifacts: shared-session")).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Analysis complete");
});
it("shows API errors instead of an empty successful scan", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 503 })));
  render(<FastScanView />);
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("503"));
});

it("discovers a newly recording scan without reopening the view", async () => {
  vi.useFakeTimers();
  let jobs: unknown[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ ok: true,
    json: async () => ({ items: url.endsWith("/automatic") ? jobs : [] }) })));
  await act(async () => { render(<FastScanView />); });
  expect(screen.queryByText("new-lower-scan")).not.toBeInTheDocument();
  jobs = [{ recording_id: "new-lower-scan", state: "recording", edge: "lower",
    captured_windows: 42 }];
  await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
  expect(screen.getByText("new-lower-scan")).toBeInTheDocument();
  expect(screen.getByText("42")).toBeInTheDocument();
});
