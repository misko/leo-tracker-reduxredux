import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { PartialBandPanel } from "./PartialBandPanel";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("shows complete low-rate products with source and artifact digests", async () => {
  const fetcher = vi.fn().mockResolvedValue({ok:true, json: async () => ({state:"figures_ready",completed_visits:2,
    manifest:{probe_count:24,candidate_probe_count:3,artifacts:[{name:"coverage.png",sha256:"sha256:bbb",byte_count:42},{name:"probes.jsonl.gz",sha256:"sha256:ccc",byte_count:42}]}})});
  vi.stubGlobal("fetch", fetcher);
  render(<PartialBandPanel sessionId="scan-fw-0123456789abcdef" inputDigest="sha256:aaa" />);
  expect(await screen.findByText(/24 analyzed probes/)).toBeInTheDocument();
  expect(screen.getByAltText("Partial-band coverage.png").getAttribute("src")).toContain("artifact_sha256=sha256%3Abbb");
  expect(screen.getByRole("link", {name:"Download probes.jsonl.gz"})).toBeInTheDocument();
  expect(fetcher.mock.calls[0][0]).toContain("input_manifest_sha256=sha256%3Aaaa");
  expect(screen.getByText(/not satellite identities/)).toBeInTheDocument();
});

it("reports a verification failure without displaying stale figures", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ok:false,status:409}));
  render(<PartialBandPanel sessionId="scan-fw-0123456789abcdef" inputDigest="sha256:aaa" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("409");
  expect(screen.queryByRole("img")).toBeNull();
});
