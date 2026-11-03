"""Append only 48–72h-old causal candidates to immutable ALGO02 inputs.

Archive access is read-only. Original state arrays, elements, previous TLEs and
GLRT contracts are preserved. Only newly admitted candidates get new states.
"""

import argparse
import copy
import os
from pathlib import Path
import numpy as np
from sgp4.exporter import export_tle
from analyze_dsx01_fixed_site import ecef_states
from leo.operations.causal_tle_catalogue import causal_catalogue
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import geodetic_to_ecef_km,ecef_to_enu_matrix,look_angles
from leo.sky.propagation import ElementSetCatalogue,parse_element_sets
from run_algo01_ds23_sample import ROOT,read,write,sha

SOURCE=ROOT/"reports/2026_10_19_algo02_ds23_full"
OUT=ROOT/"reports/2026_10_19_algo03_catalogue72"


def older_candidate(epoch,cutoff):
    return cutoff-72*3600_000_000_000<=epoch<cutoff-48*3600_000_000_000


def append_bank(original,position,velocity,numbers):
    if len(set(numbers))!=len(numbers) or set(numbers).intersection(map(int,original["norad"])):
        raise ValueError("new unique catalogue identities required")
    n=len(numbers);shape=(n,len(original["time_s"]),3)
    if position.shape!=shape or velocity.shape!=shape:raise ValueError("one new state per knot required")
    result={k:v.copy() for k,v in original.items()}
    result["position_km"]=np.concatenate((original["position_km"],position))
    result["velocity_km_s"]=np.concatenate((original["velocity_km_s"],velocity))
    result["norad"]=np.r_[original["norad"],np.asarray(numbers,dtype=original["norad"].dtype)]
    result["phase_sigma_s"]=np.r_[original["phase_sigma_s"],np.ones(n)]
    return result


class CachedReader:
    def __init__(self,reader):self.reader=reader;self.snapshots=reader.list_snapshots("space-track");self.text={}
    def list_snapshots(self,provider):
        if provider!="space-track":raise ValueError("unexpected provider")
        return self.snapshots
    def read(self,snapshot):
        if snapshot.sha256 not in self.text:self.text[snapshot.sha256]=self.reader.read(snapshot)
        return self.text[snapshot.sha256]


def prepare(case,reader):
    source=SOURCE/case;original_receipt=read(SOURCE/"causal_prior"/case/"receipt.json")
    original_elements=read(source/"nominal_elements.json");cutoff=original_receipt["cutoff_utc_ns"]
    directory=OUT/case;directory.mkdir(exist_ok=True)
    receipt_path=directory/"extension_receipt.json"
    if receipt_path.exists():raise FileExistsError("preserve scientific extension")
    with np.load(source/"bank.npz") as f:original={k:f[k] for k in f.files}
    catalogue=causal_catalogue(reader,cutoff,maximum_age_s=72*3600.)
    chosen=[k for k,(n,p) in enumerate(zip(catalogue.catalogue.satellite_numbers,catalogue.provenance,strict=True))
            if str(n) not in original_elements and older_candidate(p["element_epoch_utc_ns"],cutoff)]
    numbers=[];new_elements={};text="";new_previous={};new_previous_text=""
    position=np.empty((0,len(original["time_s"]),3));velocity=position.copy()
    if chosen:
        c=catalogue.catalogue
        selected=ElementSetCatalogue(tuple(c.names[k] for k in chosen),tuple(c.satellite_numbers[k] for k in chosen),tuple(c.satellites[k] for k in chosen))
        duration=max(300.,float(original["time_s"][-1]-17))
        coarse=np.arange(0.,duration+5,5.)
        p,v,good=ecef_states(selected,original_receipt["origin_utc_ns"],coarse)
        _,elevation,_,_=look_angles(p,v,geodetic_to_ecef_km(37.5,-122.,0.),ecef_to_enu_matrix(37.5,-122.))
        visible=[j for j in range(len(chosen)) if good[j] and elevation[j].max()>=-12.]
        chosen=[chosen[j] for j in visible]
        if chosen:
            selected=ElementSetCatalogue(tuple(c.names[k] for k in chosen),tuple(c.satellite_numbers[k] for k in chosen),tuple(c.satellites[k] for k in chosen))
            position,velocity,good=ecef_states(selected,original_receipt["origin_utc_ns"],original["time_s"])
            if not good.all():raise ValueError("added causal propagation failed")
            numbers=list(selected.satellite_numbers)
            for k in chosen:
                number=c.satellite_numbers[k];lines=list(export_tle(c.satellites[k]));provenance=catalogue.provenance[k]
                assert provenance["collected_utc_ns"]<=cutoff and older_candidate(provenance["element_epoch_utc_ns"],cutoff)
                new_elements[str(number)]=dict(lines=lines,provenance=provenance)
                text+=f"0 {c.names[k]}\n{lines[0]}\n{lines[1]}\n"
            for snapshot in reader.list_snapshots("space-track"):
                if not cutoff-72*3600_000_000_000<=snapshot.collected_utc_ns<=cutoff:continue
                parsed=parse_element_sets(reader.read(snapshot))
                for name,n,sat,epoch in zip(parsed.names,parsed.satellite_numbers,parsed.satellites,parsed.element_epoch_utc_ns(),strict=True):
                    if str(n) not in new_elements or epoch>cutoff:continue
                    if new_elements[str(n)]["provenance"]["element_epoch_utc_ns"]-epoch<1_000_000_000:continue
                    key=(epoch,snapshot.collected_utc_ns,snapshot.sha256)
                    if n not in new_previous or key>new_previous[n][0]:new_previous[n]=(key,name,sat,snapshot)
    previous_sources=copy.deepcopy(read(SOURCE/"causal_prior"/case/"previous_receipt.json"))
    for n,(key,name,sat,snapshot) in sorted(new_previous.items()):
        lines=export_tle(sat);new_previous_text+=f"0 {name}\n{lines[0]}\n{lines[1]}\n"
        previous_sources["sources"][str(n)]=dict(epoch_utc_ns=int(key[0]),collected_utc_ns=key[1],snapshot_digest=snapshot.digest)
    previous=(SOURCE/"causal_prior"/case/"previous.tle").read_text()+new_previous_text
    elements=dict(original_elements,**new_elements)
    bank=append_bank(original,position,velocity,numbers)
    np.savez_compressed(directory/"bank.npz",**bank)
    write(directory/"nominal_elements.json",elements)
    (directory/"selected.tle").write_text((source/"selected.tle").read_text()+text)
    (directory/"previous.tle").write_text(previous)
    previous_sources["catalogue_sha256"]=sha(directory/"previous.tle")
    write(directory/"previous_receipt.json",previous_sources)
    receipt=copy.deepcopy(original_receipt)
    receipt.update(bank_sha256=sha(directory/"bank.npz"),latest_tle_sha256=sha(directory/"selected.tle"),
        previous_tle_sha256=sha(directory/"previous.tle"),candidate_count=len(bank["norad"]),previous_count=len(previous_sources["sources"]),
        candidate_extension="only additional 48–72h-old causal elements; original candidates and priors unchanged")
    write(directory/"receipt.json",receipt)
    nold=len(original["norad"])
    for key in ("position_km","velocity_km_s","norad","phase_sigma_s"):
        assert np.array_equal(bank[key][:nold],original[key])
    write(receipt_path,dict(case=case,original_candidates=nold,added_candidates=numbers,
        new_candidates_with_genuine_previous=sorted(new_previous),all_original_states_and_elements_bit_exact=True,
        no_GPS_or_post_scan_TLE_used=True,original_hyperparameters_remain_frozen=True,
        original_bank_sha256=sha(source/"bank.npz"),original_receipt_sha256=sha(SOURCE/"causal_prior"/case/"receipt.json"),
        source_sha256=sha(Path(__file__)),files_sha256={p.name:sha(p) for p in directory.iterdir() if p.is_file() and not p.is_symlink() and p.name!="extension_receipt.json"}))
    owner=OUT.stat()
    for p in directory.iterdir():
        if p.is_file() and not p.is_symlink():os.chown(p,owner.st_uid,owner.st_gid)
    print(case,"added causal candidates",len(numbers),"previous",len(new_previous),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--case")
    args=parser.parse_args();OUT.mkdir(exist_ok=True)
    reader=CachedReader(TleArchiveReader(Path("/var/lib/leo/tle")))
    cases=[args.case] if args.case else [r["dataset_label"] for r in read(ROOT/"reports/2026_10_18_algo01_ds23_random20/sample.json")["selected"]]
    for case in cases:prepare(case,reader)
