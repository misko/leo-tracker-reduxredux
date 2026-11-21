"""Scientific input for one regional ALGO08 localization."""
import math
from dataclasses import dataclass


def _coordinate(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or not all(type(v) in (int, float) and math.isfinite(v) for v in value)):
        raise ValueError("A finite latitude and longitude pair is required")
    lat, lon = map(float, value)
    if not -90 < lat < 90 or not -180 <= lon <= 180:
        raise ValueError("Regional coordinates are outside the geographic domain")
    return lat, lon


@dataclass(frozen=True)
class Algo08Region:
    center: tuple[float, float]
    width_km: float
    screen_center: tuple[float, float] | None = None

    def __post_init__(self):
        center = _coordinate(self.center)
        screen = center if self.screen_center is None else _coordinate(self.screen_center)
        w = self.width_km
        if type(w) not in (float, int) or not math.isfinite(w) or w <= 0:
            raise ValueError("Search width must be positive and finite")
        lat, lon = center
        if (abs(lat) + w / (2 * 111.) >= 90
                or abs(lon) + w / (2 * 111.32 * math.cos(math.radians(lat))) > 180):
            raise ValueError("The local search square crosses a pole or the longitude seam")
        object.__setattr__(self, 'center', center)
        object.__setattr__(self, 'screen_center', screen)
        object.__setattr__(self, 'width_km', float(w))

    @classmethod
    def parse(cls, doc):
        if not isinstance(doc, dict) or set(doc) not in (
                {'center', 'width_km'}, {'center', 'width_km', 'screen_center'}):
            raise ValueError("Expected center, width_km and optional screen_center")
        return cls(**doc)

    def document(self):
        return dict(center=list(self.center), width_km=self.width_km,
                    screen_center=list(self.screen_center))
