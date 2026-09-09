import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AdaptiveHopBrowser, AdaptiveHopDetail } from "./AdaptiveHopPanel";
import { getAdaptiveSession, getAdaptiveSessions } from "./adaptive-api";
import { adaptiveDetailFixture, adaptivePageFixture } from "./adaptive-fixtures";

const respond = (value: unknown, status = 200) => ({ ok: status === 200, status, json: async () => value }) as Response;
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("adaptive actual-visit presentation", () => {
  it("shows retained inventory, source time, shadow proposals and cooldown without claiming absence", async () => {
    const detail = adaptiveDetailFixture();
    const fetcher = vi.fn(async (path: string) => path.endsWith("/glrt") || path.endsWith("/analysis") ? respond(null, 404) : respond(detail));
    vi.stubGlobal("fetch", fetcher);
    render(<AdaptiveHopDetail sessionId="adaptive-test" />);
    await screen.findByRole("heading", { name: "Actual channel visits" });
    expect(screen.getByText("53 / 54")).toBeInTheDocument();
    expect(screen.getByText(/Proposals did not change/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Actual retained visits/ })).toBeInTheDocument();
    expect(await screen.findByText(/It is not queued here/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Inspect visit 25" }));
    const choice = screen.getByLabelText("Selected hop decision");
    expect(choice).toHaveTextContent("actual CH2L; proposed CH1U");
    expect(choice).toHaveTextContent("2 consecutive misses · 1.500 s cooldown remaining");
    expect(choice).toHaveTextContent(detail.visits[25].valid_start_counter);
    fireEvent.click(screen.getByRole("button", { name: "Next visits" }));
    expect(screen.getByRole("table", { name: "Adaptive visit decisions" })).toHaveTextContent("Incomplete; not retained");
    expect(within(screen.getByRole("table", { name: "Adaptive visit decisions" })).getAllByRole("row")).toHaveLength(5);
    await screen.findByText(/No on-radio GLRT evidence was recorded/);
    expect(fetcher.mock.calls.some(([path]) => path === "/api/v1/scanner/adaptive-sessions/adaptive-test/glrt")).toBe(true);
    expect(screen.queryByText("No signal")).not.toBeInTheDocument();
  });

  it("keeps empty cancellation time and duty unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn(async (path: string) => path.endsWith("/glrt") || path.endsWith("/analysis") ? respond(null, 404) : respond(adaptiveDetailFixture("empty", 0))));
    render(<AdaptiveHopDetail sessionId="empty" />);
    await screen.findByText("No hop was started.");
    expect(screen.getByText(/No attested device-time span/)).toBeInTheDocument();
    expect(screen.getByText("Source-counter duty").parentElement).toHaveTextContent("Unavailable");
    expect(screen.queryByText("0.00%")).not.toBeInTheDocument();
  });

  it("keeps read errors explicit and separate from detector results", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(null, 409)));
    render(<AdaptiveHopDetail sessionId="corrupt" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("409");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("selects a capture and paginates history", async () => {
    const page = adaptivePageFixture();
    page.total = 6; page.next_cursor = 5;
    const fetcher = vi.fn().mockResolvedValueOnce(respond(page)).mockResolvedValue(respond({ ...page, cursor: 5, next_cursor: null }));
    vi.stubGlobal("fetch", fetcher);
    const onSelect = vi.fn();
    render(<AdaptiveHopBrowser selectedId={null} onSelect={onSelect} />);
    fireEvent.click(await screen.findByRole("button", { name: /adaptive-test/ }));
    expect(onSelect).toHaveBeenCalledWith("adaptive-test");
    fireEvent.click(screen.getByRole("button", { name: "Next adaptive captures" }));
    await screen.findByText("6–6 of 6");
    expect(fetcher.mock.calls[1][0]).toContain("cursor=5");
  });

  it("distinguishes old-server support from an empty successful history", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(null, 404)));
    render(<AdaptiveHopBrowser selectedId={null} onSelect={() => {}} />);
    await screen.findByText("Adaptive history is not available on this server.");
    expect(screen.queryByText(/No adaptive or shadow capture has been published/)).not.toBeInTheDocument();
  });

  it("ignores a late response from the previously selected scan", async () => {
    let finishOld: (value: Response) => void = () => {};
    const old = new Promise<Response>(resolve => { finishOld = resolve; });
    vi.stubGlobal("fetch", vi.fn((path: string) => path.endsWith("/glrt") || path.endsWith("/analysis") ? Promise.resolve(respond(null, 404))
      : path.endsWith("/old") ? old : Promise.resolve(respond(adaptiveDetailFixture("new")))));
    const view = render(<AdaptiveHopDetail sessionId="old" />);
    view.rerender(<AdaptiveHopDetail sessionId="new" />);
    await screen.findByText("new");
    await act(async () => { finishOld(respond(adaptiveDetailFixture("old"))); });
    expect(screen.queryByText("old")).not.toBeInTheDocument();
  });

  it("does not overlap slow history polls and aborts when unmounted", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn().mockReturnValue(new Promise(() => {}));
    vi.stubGlobal("fetch", fetcher);
    const view = render(<AdaptiveHopBrowser selectedId={null} onSelect={() => {}} />);
    await act(async () => { vi.advanceTimersByTime(90000); });
    expect(fetcher).toHaveBeenCalledTimes(1);
    view.unmount();
    expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true);
  });

  it.each(["rounded", "wrong-session", "wrong-source-time", "retained-tail", "shadow-target", "overlap-masks"])("rejects malformed %s evidence", async fault => {
    const value = adaptiveDetailFixture();
    if (fault === "rounded") Object.assign(value.visits[0], { valid_start_counter: Number(value.visits[0].valid_start_counter) });
    if (fault === "wrong-session") value.capture.session_id = "wrong";
    if (fault === "wrong-source-time") value.visits[0].valid_start_seconds += .001;
    if (fault === "retained-tail") value.visits.at(-1)!.retained = true;
    if (fault === "shadow-target") value.visits[25].target_index = 2;
    if (fault === "overlap-masks") value.visits[25].quiet_mask = 13;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(value)));
    await expect(getAdaptiveSession("adaptive-test")).rejects.toThrow();
  });

  it("rejects legacy fixed history on the adaptive route", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond({ schema_version: 3, items: [] })));
    await expect(getAdaptiveSessions(0)).rejects.toThrow(/invalid/);
  });
});
