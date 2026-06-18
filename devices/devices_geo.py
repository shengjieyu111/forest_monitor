import random

def generate_location_point(location):
    cfg = LOCATION_GEO_MAP.get(location)

    if not cfg:
        return None, None

    lng0, lat0 = cfg["center"]
    r = cfg["radius"]

    # 在中心点附近随机散布
    lng = lng0 + random.uniform(-r, r)
    lat = lat0 + random.uniform(-r, r)

    return lng, lat

LOCATION_GEO_MAP = {
    "CORE_SCENIC": {
        "center": (116.397, 39.908),
        "radius": 0.01
    },
    "FIRE_ZONE": {
        "center": (116.410, 39.915),
        "radius": 0.008
    },
    "ENTRANCE_GATE": {
        "center": (116.402, 39.905),
        "radius": 0.006
    },
    "INFRA_AREA": {
        "center": (116.390, 39.912),
        "radius": 0.007
    },
    "TRAIL_ZONE": {
        "center": (116.415, 39.900),
        "radius": 0.009
    }
}