"""Geocode addresses via Nominatim, with an on-disk cache so a given address
is only ever looked up once across all future runs."""
import json
import re
import time
from pathlib import Path

from geopy.geocoders import Nominatim

CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "geocode_cache.json"
NOMINATIM_DELAY_SECONDS = 1  # respect Nominatim's usage policy (max 1 req/sec)


def _clean_for_geocoding(address: str) -> str:
    """Simplify a permit address into something Nominatim can actually match.

    Confirmed against real failures: some permits list multiple addresses
    joined with " | " (geocode the first); "Unit:G"-style suffixes aren't
    part of a street address; and the postal codes the city reports
    (especially for new construction) often don't match what Nominatim has
    on file, causing an otherwise-correct address to fail outright.
    """
    address = address.split(" | ")[0]
    address = re.sub(r",?\s*Unit:[^,]+", "", address)
    address = re.sub(r"\s+[A-Z]\d[A-Z]\s?\d[A-Z]\d\s*$", "", address)
    return address.strip()


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def _geocode_one(geolocator, address: str, neighbourhood: str | None) -> dict | None:
    try:
        location = geolocator.geocode(_clean_for_geocoding(address), timeout=10)
    except Exception:
        location = None
    time.sleep(NOMINATIM_DELAY_SECONDS)
    if location:
        return {"lat": location.latitude, "lon": location.longitude, "approximate": False}

    # Brand-new subdivisions are sometimes issued permits before OpenStreetMap
    # has mapped the street itself — this is exactly the "leading edge of new
    # development" signal the project cares about, so fall back to a
    # neighbourhood-level pin rather than dropping the permit from the map.
    if neighbourhood:
        try:
            location = geolocator.geocode(f"{neighbourhood}, Regina, Saskatchewan", timeout=10)
        except Exception:
            location = None
        time.sleep(NOMINATIM_DELAY_SECONDS)
        if location:
            return {"lat": location.latitude, "lon": location.longitude, "approximate": True}

    return None


def geocode_all(
    addresses: list[str], neighbourhoods: dict[str, str] | None = None
) -> dict[str, dict | None]:
    """City address points first (exact, authoritative); OpenStreetMap
    (cached, rate-limited) only for addresses the city layer doesn't have.

    Each result carries `method`: "city_address_point", "osm_address", or
    "neighbourhood_centroid" (approximate), so downstream joins can trust or
    discount the point accordingly."""
    from scraper.address_points import fetch_address_index, normalize_address

    index = fetch_address_index()
    results: dict[str, dict | None] = {}
    misses = []
    for address in dict.fromkeys(addresses):
        hit = index.get(normalize_address(address))
        if hit:
            results[address] = {"lon": hit[0], "lat": hit[1], "approximate": False, "method": "city_address_point"}
        else:
            misses.append(address)

    if misses:
        fallback = geocode_addresses(misses, neighbourhoods)
        for address in misses:
            found = fallback.get(address)
            if found:
                method = "neighbourhood_centroid" if found.get("approximate") else "osm_address"
                results[address] = {**found, "method": method}
            else:
                results[address] = None
    return {a: results.get(a) for a in addresses}


def geocode_addresses(
    addresses: list[str], neighbourhoods: dict[str, str] | None = None
) -> dict[str, dict | None]:
    """Return {address: {"lat", "lon", "approximate"} or None} for every address given.

    `neighbourhoods` optionally maps address -> a coarser area name (e.g. a
    community/subdivision name) to fall back to if the exact address can't
    be resolved. Cached addresses are never re-queried against Nominatim.
    """
    cache = _load_cache()
    geolocator = Nominatim(user_agent="regina-transparency-tracker")
    neighbourhoods = neighbourhoods or {}

    uncached = [a for a in dict.fromkeys(addresses) if a not in cache]
    for i, address in enumerate(uncached):
        cache[address] = _geocode_one(geolocator, address, neighbourhoods.get(address))
        # Persist as we go — a run against ~1000+ uncached addresses can take
        # 15-20+ minutes at Nominatim's rate limit, and a mid-run interruption
        # shouldn't throw away everything looked up so far.
        if (i + 1) % 20 == 0:
            _save_cache(cache)

    if uncached:
        _save_cache(cache)

    return {a: cache.get(a) for a in addresses}
