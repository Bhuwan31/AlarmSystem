"""Nepal's 7 provinces, 77 districts and main cities, for area targeting of alerts.

Coordinates are each district's headquarters town (approximate, ±2 km), not polygon centroids. The project has no
district boundary polygons yet, so a person's district is the one they choose when subscribing (the nearest
headquarters is only offered as a default). To target exact boundaries, load official polygons (e.g. Survey
Department of Nepal) into PostGIS and replace `nearest_district`.
"""
import math

PROVINCES = ["Koshi", "Madhesh", "Bagmati", "Gandaki", "Lumbini", "Karnali", "Sudurpashchim"]

# district: (province, headquarters, lat, lon)
DISTRICTS: dict[str, tuple[str, str, float, float]] = {
    # Koshi
    "Taplejung": ("Koshi", "Taplejung", 27.352, 87.669), "Panchthar": ("Koshi", "Phidim", 27.147, 87.758),
    "Ilam": ("Koshi", "Ilam", 26.909, 87.927), "Jhapa": ("Koshi", "Bhadrapur", 26.544, 88.094),
    "Morang": ("Koshi", "Biratnagar", 26.455, 87.270), "Sunsari": ("Koshi", "Inaruwa", 26.607, 87.148),
    "Dhankuta": ("Koshi", "Dhankuta", 26.983, 87.343), "Terhathum": ("Koshi", "Myanglung", 27.133, 87.550),
    "Sankhuwasabha": ("Koshi", "Khandbari", 27.374, 87.210), "Bhojpur": ("Koshi", "Bhojpur", 27.172, 87.048),
    "Solukhumbu": ("Koshi", "Salleri", 27.503, 86.584), "Okhaldhunga": ("Koshi", "Okhaldhunga", 27.316, 86.502),
    "Khotang": ("Koshi", "Diktel", 27.213, 86.793), "Udayapur": ("Koshi", "Gaighat", 26.790, 86.700),
    # Madhesh
    "Saptari": ("Madhesh", "Rajbiraj", 26.540, 86.747), "Siraha": ("Madhesh", "Siraha", 26.654, 86.208),
    "Dhanusha": ("Madhesh", "Janakpur", 26.729, 85.925), "Mahottari": ("Madhesh", "Jaleshwar", 26.648, 85.800),
    "Sarlahi": ("Madhesh", "Malangwa", 26.857, 85.560), "Rautahat": ("Madhesh", "Gaur", 26.767, 85.270),
    "Bara": ("Madhesh", "Kalaiya", 27.033, 85.000), "Parsa": ("Madhesh", "Birgunj", 27.012, 84.877),
    # Bagmati
    "Sindhuli": ("Bagmati", "Kamalamai", 27.208, 85.912), "Ramechhap": ("Bagmati", "Manthali", 27.395, 86.060),
    "Dolakha": ("Bagmati", "Charikot", 27.667, 86.034), "Sindhupalchok": ("Bagmati", "Chautara", 27.776, 85.712),
    "Kavrepalanchok": ("Bagmati", "Dhulikhel", 27.620, 85.553), "Lalitpur": ("Bagmati", "Lalitpur", 27.666, 85.318),
    "Bhaktapur": ("Bagmati", "Bhaktapur", 27.672, 85.428), "Kathmandu": ("Bagmati", "Kathmandu", 27.708, 85.320),
    "Nuwakot": ("Bagmati", "Bidur", 27.903, 85.148), "Rasuwa": ("Bagmati", "Dhunche", 28.111, 85.297),
    "Dhading": ("Bagmati", "Dhading Besi", 27.866, 84.904), "Makwanpur": ("Bagmati", "Hetauda", 27.428, 85.032),
    "Chitwan": ("Bagmati", "Bharatpur", 27.683, 84.435),
    # Gandaki
    "Gorkha": ("Gandaki", "Gorkha", 28.000, 84.628), "Lamjung": ("Gandaki", "Besisahar", 28.231, 84.380),
    "Tanahun": ("Gandaki", "Damauli", 27.983, 84.270), "Syangja": ("Gandaki", "Syangja", 28.096, 83.874),
    "Kaski": ("Gandaki", "Pokhara", 28.210, 83.986), "Manang": ("Gandaki", "Chame", 28.551, 84.240),
    "Mustang": ("Gandaki", "Jomsom", 28.781, 83.729), "Myagdi": ("Gandaki", "Beni", 28.349, 83.567),
    "Parbat": ("Gandaki", "Kusma", 28.222, 83.683), "Baglung": ("Gandaki", "Baglung", 28.272, 83.590),
    "Nawalpur": ("Gandaki", "Kawasoti", 27.640, 84.130),
    # Lumbini
    "Parasi": ("Lumbini", "Ramgram", 27.535, 83.668), "Rupandehi": ("Lumbini", "Siddharthanagar", 27.505, 83.452),
    "Kapilvastu": ("Lumbini", "Taulihawa", 27.542, 83.058), "Palpa": ("Lumbini", "Tansen", 27.867, 83.547),
    "Arghakhanchi": ("Lumbini", "Sandhikharka", 27.993, 83.183), "Gulmi": ("Lumbini", "Tamghas", 28.073, 83.248),
    "Rukum East": ("Lumbini", "Rukumkot", 28.600, 82.633), "Rolpa": ("Lumbini", "Liwang", 28.298, 82.648),
    "Pyuthan": ("Lumbini", "Pyuthan", 28.100, 82.857), "Dang": ("Lumbini", "Ghorahi", 28.038, 82.487),
    "Banke": ("Lumbini", "Nepalgunj", 28.050, 81.617), "Bardiya": ("Lumbini", "Gulariya", 28.178, 81.350),
    # Karnali
    "Rukum West": ("Karnali", "Musikot", 28.630, 82.480), "Salyan": ("Karnali", "Salyan Khalanga", 28.374, 82.160),
    "Dolpa": ("Karnali", "Dunai", 28.932, 82.904), "Humla": ("Karnali", "Simikot", 29.970, 81.830),
    "Jumla": ("Karnali", "Jumla", 29.274, 82.184), "Kalikot": ("Karnali", "Manma", 29.150, 81.617),
    "Mugu": ("Karnali", "Gamgadhi", 29.550, 82.150), "Surkhet": ("Karnali", "Birendranagar", 28.600, 81.633),
    "Dailekh": ("Karnali", "Dailekh", 28.844, 81.710), "Jajarkot": ("Karnali", "Jajarkot Khalanga", 28.700, 82.200),
    # Sudurpashchim
    "Bajura": ("Sudurpashchim", "Martadi", 29.450, 81.467), "Bajhang": ("Sudurpashchim", "Chainpur", 29.550, 81.200),
    "Achham": ("Sudurpashchim", "Mangalsen", 29.150, 81.290), "Doti": ("Sudurpashchim", "Dipayal", 29.262, 80.940),
    "Kailali": ("Sudurpashchim", "Dhangadhi", 28.700, 80.590), "Kanchanpur": ("Sudurpashchim", "Bhimdatta", 28.963, 80.178),
    "Dadeldhura": ("Sudurpashchim", "Dadeldhura", 29.300, 80.583), "Baitadi": ("Sudurpashchim", "Baitadi", 29.533, 80.467),
    "Darchula": ("Sudurpashchim", "Darchula", 29.850, 80.550),
}

# Alternative spellings found in DHM station metadata and in common use → canonical district name
ALIASES = {
    "sindhupalchowk": "Sindhupalchok", "kavre": "Kavrepalanchok", "kabhrepalanchok": "Kavrepalanchok",
    "tanahu": "Tanahun", "makawanpur": "Makwanpur", "dhanusa": "Dhanusha", "chitawan": "Chitwan",
    "nawalparasi east": "Nawalpur", "nawalparasi (east)": "Nawalpur", "nawalparasi west": "Parasi",
    "nawalparasi (west)": "Parasi", "rukum (east)": "Rukum East", "rukum (west)": "Rukum West",
    "kapilbastu": "Kapilvastu", "tehrathum": "Terhathum", "therathum": "Terhathum", "dadeldura": "Dadeldhura",
}

# city: (district, lat, lon, default radius km)
CITIES: dict[str, tuple[str, float, float, float]] = {
    "Kathmandu": ("Kathmandu", 27.708, 85.320, 8), "Lalitpur": ("Lalitpur", 27.666, 85.318, 5),
    "Bhaktapur": ("Bhaktapur", 27.672, 85.428, 4), "Pokhara": ("Kaski", 28.210, 83.986, 8),
    "Biratnagar": ("Morang", 26.455, 87.270, 6), "Birgunj": ("Parsa", 27.012, 84.877, 6),
    "Bharatpur": ("Chitwan", 27.683, 84.435, 7), "Dharan": ("Sunsari", 26.812, 87.284, 5),
    "Itahari": ("Sunsari", 26.663, 87.274, 5), "Janakpur": ("Dhanusha", 26.729, 85.925, 5),
    "Butwal": ("Rupandehi", 27.700, 83.448, 6), "Siddharthanagar": ("Rupandehi", 27.505, 83.452, 5),
    "Hetauda": ("Makwanpur", 27.428, 85.032, 6), "Nepalgunj": ("Banke", 28.050, 81.617, 5),
    "Dhangadhi": ("Kailali", 28.700, 80.590, 6), "Birendranagar": ("Surkhet", 28.600, 81.633, 5),
    "Ghorahi": ("Dang", 28.038, 82.487, 5), "Tulsipur": ("Dang", 28.131, 82.297, 5),
    "Damak": ("Jhapa", 26.659, 87.702, 4), "Bhimdatta": ("Kanchanpur", 28.963, 80.178, 5),
    "Gorkha": ("Gorkha", 28.000, 84.628, 3), "Tansen": ("Palpa", 27.867, 83.547, 3),
}


def canonical_district(name: str | None) -> str | None:
    if not name:
        return None
    n = name.strip()
    for d in DISTRICTS:
        if d.lower() == n.lower():
            return d
    return ALIASES.get(n.lower())


def canonical_province(name: str | None) -> str | None:
    if not name:
        return None
    n = name.strip().lower().replace(" province", "")
    return next((p for p in PROVINCES if p.lower() == n), None)


def canonical_city(name: str | None) -> str | None:
    if not name:
        return None
    return next((c for c in CITIES if c.lower() == name.strip().lower()), None)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(a)))


def nearest_district(lat: float, lon: float) -> tuple[str, str, float]:
    """(district, province, km to its headquarters). Only a default: boundaries are not modelled."""
    d, (prov, _, dlat, dlon) = min(DISTRICTS.items(), key=lambda kv: haversine_km(lat, lon, kv[1][2], kv[1][3]))
    return d, prov, haversine_km(lat, lon, dlat, dlon)


def place_label(lat: float, lon: float) -> str:
    """Human label for a point: nearest city if within 15 km, else '<district HQ> area, <district> district'."""
    city, (cd, clat, clon, _) = min(CITIES.items(), key=lambda kv: haversine_km(lat, lon, kv[1][1], kv[1][2]))
    dist = haversine_km(lat, lon, clat, clon)
    district, province, _ = nearest_district(lat, lon)
    if dist <= 15:
        return f"near {city}, {cd} district ({dist:.1f} km from centre)" if dist > 1.5 else f"{city}, {cd} district"
    hq = DISTRICTS[district][1]
    return f"{hq} area, {district} district, {province} Province"


def areas() -> dict:
    return {
        "provinces": PROVINCES,
        "districts": [{"name": d, "province": p, "hq": hq, "lat": la, "lon": lo} for d, (p, hq, la, lo) in DISTRICTS.items()],
        "cities": [{"name": c, "district": d, "lat": la, "lon": lo, "radius_km": r} for c, (d, la, lo, r) in CITIES.items()],
        "note": "District and city points are headquarters / town centres (approximate). District membership of a "
                "subscriber is the district they chose.",
    }
