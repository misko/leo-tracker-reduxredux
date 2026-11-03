"""Extend frozen causal orbit banks without changing catalogue membership."""
from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np


def digest(path: Path) -> str:
    return "sha256:"+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def plan_extension(times_s, padding_s: float=120.0) -> dict:
    times=np.asarray(times_s,dtype=np.float64)
    if times.ndim!=1 or times.size<4 or np.any(~np.isfinite(times)) or np.any(np.diff(times)<=0):
        raise ValueError("orbit times must be finite, increasing, and contain at least four knots")
    spacing=np.diff(times)
    if not np.allclose(spacing,spacing[0],rtol=1e-12,atol=1e-12): raise ValueError("orbit cadence is not uniform")
    step=float(spacing[0])
    if not math.isfinite(padding_s) or padding_s<=0: raise ValueError("padding_s must be positive")
    count=math.ceil(padding_s/step)
    leading=times[0]-step*np.arange(count,0,-1); trailing=times[-1]+step*np.arange(1,count+1)
    expanded=np.concatenate((leading,times,trailing))
    return {"step_s":step,"requested_padding_s":float(padding_s),"added_knots_per_side":count,
            "old_query_bounds_s":[float(times[1]),float(times[-2])],
            "new_query_bounds_s":[float(expanded[1]),float(expanded[-2])],"times_s":expanded}


def verify_bindings(observation_path: Path, metadata_path: Path, state_path: Path):
    metadata=json.loads(Path(metadata_path).read_text())
    expected={"observation":metadata.get("observation_sha256"),"state":metadata.get("state_sha256"),
              "tle":metadata.get("tle",{}).get("sha256")}
    paths={"observation":Path(observation_path),"state":Path(state_path),
           "tle":Path(metadata.get("tle",{}).get("path",""))}
    for name,path in paths.items():
        if not path.is_file() or digest(path)!=expected[name]: raise ValueError(f"{name} binding mismatch")
    observations=json.loads(paths["observation"].read_text())
    if observations.get("session_id")!=metadata.get("session_id"): raise ValueError("session binding mismatch")
    if not metadata.get("tle",{}).get("causal"): raise ValueError("TLE snapshot is not declared causal")
    return metadata,observations,paths["tle"]


def _validate_propagation(error_code,position,velocity,norad_ids,times_s):
    sgp4_valid=np.all(np.asarray(error_code)==0,axis=1)
    finite=np.all(np.isfinite(position),axis=(1,2))&np.all(np.isfinite(velocity),axis=(1,2))
    valid=sgp4_valid&finite
    if not np.all(valid):
        failed=[{"row":int(i),"norad_id":int(norad_ids[i]),"sgp4_error_codes":sorted(set(map(int,np.asarray(error_code)[i]))),
                 "finite":bool(finite[i])} for i in np.flatnonzero(~valid)[:20]]
        raise ValueError(f"selected satellites failed extension propagation: {failed}")
    radius=np.linalg.norm(position,axis=-1);rows=[]
    for row in np.flatnonzero(np.any(radius<=6498.137,axis=1)):
        bad=np.flatnonzero(radius[row]<=6498.137)
        rows.append({"row":int(row),"norad_id":int(norad_ids[row]),"minimum_radius_km":float(radius[row].min()),
                     "threshold_km":6498.137,"crossing_times_s":[float(times_s[i]) for i in bad]})
    return rows


def _propagate(catalogue, indices, start_ns: int, times_s):
    from leo.sky.frames import greenwich_mean_sidereal_time_rad,julian_day_from_utc_ns,teme_to_ecef
    from leo.sky.propagation import propagate_grid
    from leo.sky.sampling import SamplingGrid
    orbit_ns=np.asarray([start_ns+round(float(t)*1e9) for t in times_s],dtype=np.int64)
    state=propagate_grid(catalogue,SamplingGrid(tuple(map(int,orbit_ns)),0,1.0),indices)
    jd,fraction=julian_day_from_utc_ns(orbit_ns)
    position,velocity=teme_to_ecef(state.position_teme_km,state.velocity_teme_km_s,
        greenwich_mean_sidereal_time_rad(jd,fraction))
    ids=np.asarray(catalogue.satellite_numbers,dtype=np.int64)[np.asarray(indices)]
    diagnostics=_validate_propagation(state.error_code,position,velocity,ids,np.asarray(times_s))
    return position,velocity,diagnostics


def extend_orbit_bank(observation_path: Path, original_metadata_path: Path,
                      original_state_path: Path, output_state_path: Path, *, padding_s: float=120.0):
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets
    metadata,observations,tle_path=verify_bindings(observation_path,original_metadata_path,original_state_path)
    with np.load(original_state_path,allow_pickle=False) as data:
        ids=np.array(data["satellite_ids"],dtype=np.int64,copy=True); old_times=np.array(data["knot_times_s"],copy=True)
        old_positions=np.array(data["positions_ecef_km"],copy=True); old_velocities=np.array(data["velocities_ecef_km_s"],copy=True)
    plan=plan_extension(old_times,padding_s); count=plan["added_knots_per_side"]
    archive=TleArchiveReader(tle_path.parents[2]); refs=[x for x in archive.list_snapshots(tle_path.parent.name) if x.path==tle_path]
    if len(refs)!=1: raise ValueError("TLE path is not one canonical public-reader snapshot")
    catalogue=parse_element_sets(archive.read(refs[0])); catalogue_ids=np.asarray(catalogue.satellite_numbers,dtype=np.int64)
    index={int(value):i for i,value in enumerate(catalogue_ids)}
    if len(index)!=len(catalogue_ids) or any(int(value) not in index for value in ids): raise ValueError("selected IDs do not map uniquely to causal catalogue")
    selected=np.asarray([index[int(value)] for value in ids],dtype=int)
    added_times=np.concatenate((plan["times_s"][:count],plan["times_s"][-count:]))
    added_positions,added_velocities,radius_crossings=_propagate(catalogue,selected,int(observations["start_utc_ns"]),added_times)
    positions=np.concatenate((added_positions[:,:count],old_positions,added_positions[:,count:]),axis=1)
    velocities=np.concatenate((added_velocities[:,:count],old_velocities,added_velocities[:,count:]),axis=1)
    if not np.array_equal(positions[:,count:-count],old_positions) or not np.array_equal(velocities[:,count:-count],old_velocities):
        raise AssertionError("original knots changed")
    output_state_path=Path(output_state_path); output_state_path.parent.mkdir(parents=True,exist_ok=True)
    np.savez(output_state_path,satellite_ids=ids,knot_times_s=plan["times_s"],positions_ecef_km=positions,velocities_ecef_km_s=velocities)
    return {"schema":"fixed-height-extended-causal-orbits/v1","session_id":metadata["session_id"],
        "generator":{"path":str(Path(__file__).resolve()),"sha256":digest(Path(__file__).resolve())},
        "parent":{"metadata_path":str(Path(original_metadata_path).resolve()),"metadata_sha256":digest(original_metadata_path),
                  "state_path":str(Path(original_state_path).resolve()),"state_sha256":digest(original_state_path)},
        "observation":{"path":str(Path(observation_path).resolve()),"sha256":digest(observation_path)},
        "tle":metadata["tle"],"catalogue_selection_proof":{"policy":"exact parent propagated IDs in exact order",
            "parent_propagated_count":metadata["propagated_count"],"extended_count":len(ids),
            "ids_equal_parent_state":True,"no_new_catalogue_ids":True},
        "extension":{"requested_padding_s":padding_s,"added_knots_per_side":count,
            "knot_step_s":plan["step_s"],"old_query_bounds_s":plan["old_query_bounds_s"],
            "new_query_bounds_s":plan["new_query_bounds_s"],"purpose":"diagnose clock excursions; does not expand clock prior",
            "post_admission_radius_threshold_crossings":radius_crossings,
            "radius_threshold_qualification":"diagnostic outside original admission interval; finite error-free SGP4 states retained"},
        "state_file":str(output_state_path.resolve()),"state_sha256":digest(output_state_path),
        "state_frame":metadata["state_frame"],"original_knots_preserved_bitwise":True}
