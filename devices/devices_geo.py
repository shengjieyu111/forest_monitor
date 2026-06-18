import random


JIUFENG_CENTER = (116.031, 39.993)

JIUFENG_BOUNDARY = [
    (116.0148, 39.9822),
    (116.0208, 39.9778),
    (116.0338, 39.9800),
    (116.0458, 39.9872),
    (116.0474, 39.9988),
    (116.0398, 40.0088),
    (116.0252, 40.0082),
    (116.0130, 39.9970),
]

LOCATION_GEO_MAP = {
    "CORE_SCENIC": {"center": (116.0310, 39.9932), "radius": 0.0032},
    "FIRE_ZONE": {"center": (116.0390, 40.0004), "radius": 0.0028},
    "ENTRANCE_GATE": {"center": (116.0200, 39.9844), "radius": 0.0024},
    "INFRA_AREA": {"center": (116.0260, 39.9866), "radius": 0.0025},
    "TRAIL_ZONE": {"center": (116.0340, 40.0040), "radius": 0.0030},
}


def generate_location_point(location, seed=None):
    cfg = LOCATION_GEO_MAP.get(location)
    if not cfg:
        return None, None

    rng = random.Random(str(seed)) if seed is not None else random
    lng0, lat0 = cfg["center"]
    r = cfg["radius"]
    return lng0 + rng.uniform(-r, r), lat0 + rng.uniform(-r, r)


def generate_device_location_point(location, device_id):
    return generate_location_point(location, seed=f"{location}:{device_id}")
