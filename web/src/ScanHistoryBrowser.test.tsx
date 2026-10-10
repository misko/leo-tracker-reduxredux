import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ScanHistoryBrowser } from "./ScanHistoryBrowser";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });
const adaptive = { session_id: "adaptive-old", captured_at: "2026-10-10T01:00:00Z",
  recorded_at: "2026-10-10T01:00:00Z", mode: "adaptive", selected_edge: "upper",
  sample_rate_hz: 2500000, retained_visits: 2214, started_visits: 2214, terminal_state: "completed" };
const fast = { recording_id: "fast-new", state: "recording", edge: "lower", captured_windows: 12,
  started_utc_ns: Date.parse("2026-10-10T02:00:00Z") * 1e6, updated_utc_ns: Date.now() * 1e6 };

it("combines both modes chronologically and selects by stable identity", async () => {
  const select = vi.fn();
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ ok: true, json: async () =>
    url.includes("adaptive-sessions") ? { items: [adaptive], total: 1, next_cursor: null } : { items: [fast] } })));
  render(<ScanHistoryBrowser selectedId={null} onSelect={select} />);
  await screen.findByText("fast-new");
  const buttons = within(screen.getByRole("table")).getAllByRole("button");
  expect(buttons[0]).toHaveTextContent("fast-new");
  expect(select).toHaveBeenCalledWith(expect.objectContaining({ id: "fast-new", mode: "fast" }));
  fireEvent.click(buttons[1]);
  expect(select).toHaveBeenLastCalledWith(expect.objectContaining({ id: "adaptive-old", mode: "adaptive" }));
  fireEvent.change(screen.getByLabelText("Scan mode"), { target: { value: "adaptive" } });
  expect(screen.queryByText("fast-new")).not.toBeInTheDocument();
});

it("polls new recordings without changing the user's selection", async () => {
  vi.useFakeTimers(); let jobs: unknown[] = []; const select = vi.fn();
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ ok: true, json: async () =>
    url.includes("adaptive-sessions") ? { items: [adaptive], total: 1, next_cursor: null } : { items: jobs } })));
  await act(async () => { render(<ScanHistoryBrowser selectedId="adaptive-old" onSelect={select} />); });
  jobs = [fast];
  await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
  expect(screen.getByText("fast-new")).toBeInTheDocument();
  expect(select).not.toHaveBeenCalled();
});

it("keeps fast history available when adaptive history fails", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ ok: !url.includes("adaptive-sessions"), status: 503,
    json: async () => ({ items: [fast] }) })));
  render(<ScanHistoryBrowser selectedId="fast-new" onSelect={() => {}} />);
  expect(await screen.findByText("fast-new")).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("503");
});

it("uses the existing reader's page size when navigating back", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ items: [] }) })));
  const load = vi.fn(async (cursor: number) => ({ items: [{ ...adaptive, session_id: `page-${cursor}` }],
    total: 50, limit: 10, next_cursor: cursor + 10 }));
  render(<ScanHistoryBrowser selectedId="keep" onSelect={() => {}} loadAdaptive={load} />);
  await screen.findByText("page-0");
  fireEvent.click(screen.getByRole("button", { name: "Older adaptive captures" }));
  await screen.findByText("page-10");
  fireEvent.click(screen.getByRole("button", { name: "Older adaptive captures" }));
  await screen.findByText("page-20");
  fireEvent.click(screen.getByRole("button", { name: "Newer adaptive captures" }));
  await screen.findByText("page-10");
});
