import {cleanup,render,screen,waitFor} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {FastStandardAnalysis} from "./FastStandardAnalysis";

afterEach(()=>{cleanup();vi.unstubAllGlobals();});
const names=["ch1-4-all","ch5-8-all","ch1-4-unassociated","ch5-8-unassociated","ch1-4-residuals","ch5-8-residuals","track-rms","position"];

it("reads v2 by its own model and rejects a v1 receipt under a v2 run",async()=>{
  let model="algo08-two-scan-compact-v5-v2";
  vi.stubGlobal("fetch",vi.fn(async()=>({ok:true,json:async()=>({schema_version:3,
    model_version:model,state:"withheld",reason:"no_active_curvature",artifacts:[]})})));
  const view=render(<FastStandardAnalysis runId="algo08-v2-first"/>);
  expect(await screen.findByText(/Position withheld/)).toBeInTheDocument();
  model="algo08-two-scan-compact-v5-v1";
  view.rerender(<FastStandardAnalysis runId="algo08-v2-second"/>);
  expect(await screen.findByRole("alert")).toHaveTextContent("another algorithm");
});

it("displays the declared search area even when the receiver withholds",async()=>{
  vi.stubGlobal("fetch",vi.fn(async()=>({ok:true,json:async()=>({schema_version:3,
    model_version:"algo08-two-scan-compact-v5-v1",state:"withheld",reason:"no_active_curvature",
    region:{center:[-33,20],width_km:18,screen_center:[-33,20]},artifacts:[]})})));
  render(<FastStandardAnalysis runId="algo08-south"/>);
  expect(await screen.findByText(/18 km square centered at -33, 20/)).toBeInTheDocument();
  expect(screen.queryAllByRole("img")).toHaveLength(0);
});
const arm={endpoint_latlon:[37.842403850242285,-122.49124137019581],associated_points:3000,
  associated_percent:75,tracks:90,satellites:20,residual_rms_hz:115,evaluation_error_m:883.504916};
const result={schema_version:1,state:"complete",model_version:"algo07-causal-guarded-reassociation-v1",
  selected_model:"algo04-causal-numerical-v1",decision:"ALGO06_fallback",glrt_points:4000,
  arms:{fitted_c:arm,c0:{...arm,evaluation_error_m:911.9615}},
  evaluation_reference:{latitude_deg:37.849061591561885,longitude_deg:-122.48574968092912},
  artifacts:names.map(name=>({name,sha256:"sha256:"+"a".repeat(64)}))};

it("shows the standard result, exact fallback and all eight versioned PNGs",async()=>{
  vi.stubGlobal("fetch",vi.fn(async()=>({ok:true,json:async()=>result})));
  render(<FastStandardAnalysis runId="scan"/>);
  expect(await screen.findByText("883.5 m")).toBeInTheDocument();
  expect(screen.getByText("912.0 m")).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Complete · retained ALGO04 solution");
  expect(screen.getAllByRole("img")).toHaveLength(8);
  for(const image of screen.getAllByRole("img"))expect(image.getAttribute("src")).toContain("?sha256=sha256%3A");
  expect(screen.getByText(/Evaluation reference: 37.84906159/)).toBeInTheDocument();
});

it("never presents an old or pending result as completed ALGO07",async()=>{
  vi.stubGlobal("fetch",vi.fn(async()=>({ok:true,json:async()=>({...result,model_version:"legacy"})})));
  render(<FastStandardAnalysis runId="scan"/>);
  expect(await screen.findByRole("alert")).toHaveTextContent("another algorithm");
  expect(screen.queryByText("883.5 m")).not.toBeInTheDocument();
});

it("renders the eight ALGO08 figures with their own algorithm identity",async()=>{
  vi.stubGlobal("fetch",vi.fn(async()=>({ok:true,json:async()=>({...result,schema_version:2,
    model_version:"algo08-two-scan-compact-v5-v1",selected_model:"algo08-two-scan-compact-v5-v1"})})));
  render(<FastStandardAnalysis runId="algo08-test"/>);
  expect(await screen.findByText("Complete · two-scan cancellation and compact v5")).toBeInTheDocument();
  expect(screen.getAllByRole("img")).toHaveLength(8);
  expect(screen.getByRole("link",{name:"Download standard ALGO08 result"})).toBeInTheDocument();
});

it("explains a withheld ALGO08 position",async()=>{
  vi.stubGlobal("fetch",vi.fn(async()=>({ok:true,json:async()=>({schema_version:2,
    state:"withheld",model_version:"algo08-two-scan-compact-v5-v1",reason:"no_active_curvature"})})));
  render(<FastStandardAnalysis runId="algo08-test"/>);
  expect(await screen.findByText("Position withheld · no_active_curvature")).toBeInTheDocument();
  expect(screen.queryAllByRole("img")).toHaveLength(0);
});

it("does not invent evaluation accuracy without a confirmed reference",async()=>{
  vi.stubGlobal("fetch",vi.fn(async()=>({ok:true,json:async()=>({...result,evaluation_reference:null,
    arms:{c0:{...arm,evaluation_error_m:null},fitted_c:{...arm,evaluation_error_m:null}}})})));
  render(<FastStandardAnalysis runId="scan"/>);
  await waitFor(()=>expect(screen.getAllByText("Reference unavailable")).toHaveLength(2));
});
