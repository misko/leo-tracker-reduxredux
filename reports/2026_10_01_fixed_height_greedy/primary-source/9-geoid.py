"""Fixed-MSL to ellipsoid-height adapter backed by NOAA GEOID18 CONUS grid."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, io, math, zipfile
from pathlib import Path
import numpy as np

CENTER_LAT_DEG=38.5816
CENTER_LON_DEG=-121.4944
EARTH_RADIUS_KM=6371.007180918475
ORTHOMETRIC_HEIGHT_M=30.48
DEFAULT_GRID=Path.home()/".cache/leo/research/fixed_height_greedy/geoid/g2018u0.asc.zip"
GRID_SHA256="sha256:ffeb8faa42310488fc406554e49de9c4f6ed3fc7dc591d568e0e748dff11b6db"
GRID_URL="https://geodesy.noaa.gov/PC_PROD/GEOID18/Format_ascii/g2018u0.asc.zip"


def _sha256(path: Path) -> str:
    return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()


def _latlon_from_enu(east_km: float, north_km: float) -> tuple[float,float]:
    lat1,lon1=map(math.radians,(CENTER_LAT_DEG,CENTER_LON_DEG))
    distance=math.hypot(east_km,north_km)
    if distance == 0: return CENTER_LAT_DEG,CENTER_LON_DEG
    bearing=math.atan2(east_km,north_km); angular=distance/EARTH_RADIUS_KM
    lat2=math.asin(math.sin(lat1)*math.cos(angular)+math.cos(lat1)*math.sin(angular)*math.cos(bearing))
    lon2=lon1+math.atan2(math.sin(bearing)*math.sin(angular)*math.cos(lat1),
                         math.cos(angular)-math.sin(lat1)*math.sin(lat2))
    return math.degrees(lat2),((math.degrees(lon2)+180.)%360.)-180.


@dataclass(frozen=True)
class FixedMslGeoid18:
    lat0: float
    lon0_360: float
    dlat: float
    dlon: float
    undulation_m: np.ndarray
    input_bindings: dict

    def geoid_undulation_m(self,east_km: float,north_km: float) -> float:
        lat,lon=_latlon_from_enu(float(east_km),float(north_km)); lon%=360.
        y=(lat-self.lat0)/self.dlat; x=(lon-self.lon0_360)/self.dlon
        iy,ix=math.floor(y),math.floor(x)
        if iy<0 or ix<0 or iy+1>=self.undulation_m.shape[0] or ix+1>=self.undulation_m.shape[1]:
            raise ValueError(f"candidate ({lat:.6f}, {lon:.6f}) is outside GEOID18 grid")
        fy,fx=y-iy,x-ix; g=self.undulation_m
        return float((1-fy)*((1-fx)*g[iy,ix]+fx*g[iy,ix+1])+
                     fy*((1-fx)*g[iy+1,ix]+fx*g[iy+1,ix+1]))

    def __call__(self,east_km: float,north_km: float) -> float:
        """Return ellipsoid height in km using h = H + N."""
        return (ORTHOMETRIC_HEIGHT_M+self.geoid_undulation_m(east_km,north_km))/1000.

    def value_and_gradient(self,east_km: float,north_km: float,step_km: float=.1):
        if not math.isfinite(step_km) or step_km<=0: raise ValueError("step_km must be positive")
        value=self(east_km,north_km)
        de=(self(east_km+step_km,north_km)-self(east_km-step_km,north_km))/(2*step_km)
        dn=(self(east_km,north_km+step_km)-self(east_km,north_km-step_km))/(2*step_km)
        return value,np.array([de,dn])


def load_height_model(path: Path=DEFAULT_GRID, *, expected_sha256: str=GRID_SHA256) -> FixedMslGeoid18:
    path=Path(path); actual=_sha256(path)
    if actual != expected_sha256: raise ValueError(f"GEOID18 archive digest mismatch: {actual}")
    with zipfile.ZipFile(path) as archive:
        names=[name for name in archive.namelist() if name.lower().endswith(".asc")]
        if len(names)!=1: raise ValueError("GEOID18 archive must contain exactly one ASCII grid")
        with archive.open(names[0]) as raw:
            header=raw.readline().decode("ascii").split()
            if len(header)<6: raise ValueError("invalid GEOID18 header")
            lat0,lon0,dlat,dlon=float(header[0]),float(header[1]),float(header[2]),float(header[3])
            nlat,nlon=int(header[4]),int(header[5])
            values=np.fromstring(io.TextIOWrapper(raw,encoding="ascii").read(),sep=" ")
    if values.size != nlat*nlon: raise ValueError("GEOID18 grid cell count mismatch")
    grid=values.reshape(nlat,nlon); grid.setflags(write=False)
    bindings={"model":"GEOID18","vertical_datum":"NAVD88","orthometric_height_m":ORTHOMETRIC_HEIGHT_M,
              "height_relation":"ellipsoid_h_m = orthometric_H_m + geoid_undulation_N_m",
              "grid_url":GRID_URL,"grid_path":str(path.resolve()),"grid_sha256":actual,
              "interpolation":"bilinear","horizontal_mapping":"Sacramento-centered authalic sphere"}
    return FixedMslGeoid18(lat0,lon0,dlat,dlon,grid,bindings)
