"""Distance calculation and ETA calculation plugin using Haversine formula."""
import math
from app.core.config import settings


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on Earth in kilometers."""
    R = 6371.0  # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 2)


def calculate_travel_minutes(distance_km: float, speed_kmh: float = None, prep_minutes: float = 10.0) -> float:
    """Calculate estimated travel time in minutes based on average speed and prep time."""
    speed = speed_kmh or settings.AVG_SPEED_KMH
    if speed <= 0:
        speed = 40.0
    travel_hours = distance_km / speed
    return round(prep_minutes + (travel_hours * 60.0), 1)
