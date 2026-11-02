import { act, cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { FastScanView } from "./FastScanView";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

it.each([null, .03])("preserves CFO evidence when fast scores are missing (other score %s)", async (otherScore) => {
  const report = { run_id: "run", recording_name: "native-rate", window_count: 3,
    counts: { processed: 3, skipped_fast_score: 0, invalid_capture: 0 },
    policy: { mode: "ungated", threshold: .0132, margin_gate: .025, strong_margin: .1 },
    rf_mapping_authorities: ["hypothesis"], time_basis: "relative sample counter",
    channels: [{ channel: 8, receiver_id: 0, processed: 3, skipped: 0, active: 2, strong: 2 }],
    points: [
      { channel: 8, receiver_id: 0, visit: 1, time_s: .3, score: null, margin: .2, cfo_hz: 1000 },
      { channel: 8, receiver_id: 0, visit: 2, time_s: .6, score: otherScore, margin: .3, cfo_hz: 1200 },
      { channel: 8, receiver_id: 0, visit: 3, time_s: .9, score: .02, margin: null, cfo_hz: 1400 },
    ] };
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ ok: true,
    json: async () => url.endsWith("/automatic") ? { items: [] }
      : url.includes("?") ? { items: [report] } : report })));
  render(<FastScanView />);
  const cfoPlot = await screen.findByRole("img", { name: "RX1 CFO over time" });
  expect(cfoPlot.querySelectorAll("circle")).toHaveLength(2);
  expect(cfoPlot).toHaveTextContent("score unavailable, margin 0.20000, CFO 1000.0 Hz");
  fireEvent.change(screen.getByLabelText("Plot"), { target: { value: "score" } });
  if (otherScore === null) {
    expect(screen.getByText("No windows with both a fast score and GLRT margin.")).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "RX1 fast score versus GLRT margin" })).not.toBeInTheDocument();
  } else {
    expect(screen.getByRole("img", { name: "RX1 fast score versus GLRT margin" }).querySelectorAll("circle")).toHaveLength(1);
  }
  fireEvent.change(screen.getByLabelText("Plot"), { target: { value: "cfo" } });
  expect(screen.getByRole("img", { name: "RX1 CFO over time" }).querySelectorAll("circle")).toHaveLength(2);
});
it("keeps the orbit panel visible before PNG publication", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ ok: true, json: async () =>
    url.endsWith("/orbits") ? { artifacts: [] }
      : { items: url.includes("?") ? [{ run_id: "run", recording_name: "capture" }] : [] } })));
  render(<FastScanView recordingId="capture" />);
  expect(await screen.findByText(/Orbit PNGs have not been published/)).toBeInTheDocument();
});
it("reports an orbit API failure instead of hiding the section", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({
    ok: !url.endsWith("/orbits"), status: 503, json: async () =>
      ({ items: url.includes("?") ? [{ run_id: "run", recording_name: "capture" }] : [] }),
  })));
  render(<FastScanView recordingId="capture" />);
  expect(await screen.findByText(/Orbit plots unavailable:.*503/)).toBeInTheDocument();
});
it("shows four published orbit PNGs with download links", async () => {
  const names = ["ch1-4-all", "ch5-8-all", "ch1-4-unassociated", "ch5-8-unassociated"];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ ok: true, json: async () =>
    url.endsWith("/orbits") ? { artifacts: names.map(name => ({ name })) }
      : { items: url.includes("?") ? [{ run_id: "run", recording_name: "capture" }] : [] } })));
  render(<FastScanView recordingId="capture" />);
  const image = await screen.findByRole("img", { name: "CH1–4 · All GLRT" });
  expect(image).toHaveAttribute("src", "/api/v1/fast-scans/run/orbits/ch1-4-all.png");
  expect(screen.getAllByRole("img")).toHaveLength(4);
  expect(screen.getByRole("link", { name: "CH5–8 · Unassociated GLRT only · PNG" }))
    .toHaveAttribute("href", "/api/v1/fast-scans/run/orbits/ch5-8-unassociated.png");
});
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
  expect((await screen.findAllByRole("alert"))[0]).toHaveTextContent("503");
  expect(screen.getByText("Artifacts: shared-session")).toBeInTheDocument();
  expect(screen.getByText("Analysis complete")).toBeInTheDocument();
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
