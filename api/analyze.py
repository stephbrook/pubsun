from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone, time
from typing import Callable

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.warp import transform
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import nearest_points, unary_union

from sun_check import MEL, sun_position

SOLAR = "https://solar.googleapis.com/v1/"
NOT_STREETS = {
    "footway",
    "cycleway",
    "path",
    "steps",
    "corridor",
    "bridleway",
    "track",
    "construction",
    "proposed",
    "elevator",
    "platform",
}

CACHE_DIR = os.environ.get("CACHE_DIR", os.path.join(os.path.dirname(__file__), "cache"))
Progress = Callable[[str], None]
USER_AGENT = "SchoonerWeather/1.0 (pub sun lookup; local)"
OVERPASS = "https://overpass.openstreetmap.fr/api/interpreter"
NOMINATIM = "https://nominatim.openstreetmap.org/search"


class AnalyzeError(Exception):
    pass


def _http_json(req: urllib.request.Request, timeout: int = 25) -> dict | list:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:240]
        raise AnalyzeError(f"OpenStreetMap HTTP {exc.code}: {body}") from exc
    except Exception as exc:
        raise AnalyzeError(f"OpenStreetMap failed: {exc}") from exc


def _overpass(query: str) -> dict:
    body = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(
        OVERPASS,
        data=body,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    data = _http_json(req)
    if not isinstance(data, dict):
        raise AnalyzeError("OpenStreetMap returned an unexpected response.")
    return data


def _geom_for(el: dict, polygons: bool):
    coords = [(p["lon"], p["lat"]) for p in el.get("geometry") or []]
    if polygons:
        if el.get("type") == "relation":
            rings = []
            for member in el.get("members") or []:
                if member.get("role") not in ("outer", "", None):
                    continue
                ring = [(p["lon"], p["lat"]) for p in member.get("geometry") or []]
                if len(ring) >= 4:
                    if ring[0] != ring[-1]:
                        ring.append(ring[0])
                    rings.append(ring)
            if not rings:
                return None
            try:
                geom = Polygon(rings[0])
            except Exception:
                return None
        else:
            if len(coords) < 4:
                return None
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            try:
                geom = Polygon(coords)
            except Exception:
                return None
        if geom.is_empty or not geom.is_valid:
            return None
        return geom
    if len(coords) < 2:
        return None
    return LineString(coords)


def _overpass_to_gdf(data: dict, *, kind: str) -> gpd.GeoDataFrame:
    polygons = kind == "building"
    rows = []
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        if kind == "building" and "building" not in tags:
            continue
        if kind == "highway" and "highway" not in tags:
            continue
        geom = _geom_for(el, polygons)
        if geom is None:
            continue
        rows.append(
            {
                "name": tags.get("name"),
                "highway": tags.get("highway"),
                "building": tags.get("building"),
                "geometry": geom,
            }
        )
    cols = ["name", "highway", "building", "geometry"]
    if not rows:
        return gpd.GeoDataFrame(columns=cols, crs="EPSG:4326")
    return gpd.GeoDataFrame(rows, columns=cols, crs="EPSG:4326")


def _save_gdf(gdf: gpd.GeoDataFrame, path: str) -> None:
    try:
        gdf.to_file(path, driver="GeoJSON")
    except Exception:
        pass


def _load_osm(lat: float, lon: float, dist: float, slug: str) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    key = f"{lat:.5f}_{lon:.5f}_{int(dist)}"
    paths = [
        (
            os.path.join(CACHE_DIR, f"{key}_buildings.geojson"),
            os.path.join(CACHE_DIR, f"{key}_streets.geojson"),
        ),
        (
            os.path.join(CACHE_DIR, f"{slug}_buildings.geojson"),
            os.path.join(CACHE_DIR, f"{slug}_streets.geojson"),
        ),
    ]
    for b_path, s_path in paths:
        if os.path.exists(b_path) and os.path.exists(s_path):
            return gpd.read_file(b_path), gpd.read_file(s_path)

    query = (
        f"[out:json][timeout:25];("
        f'way["building"](around:{int(dist)},{lat},{lon});'
        f'relation["building"](around:{int(dist)},{lat},{lon});'
        f'way["highway"]["name"](around:{int(dist)},{lat},{lon});'
        f");out geom;"
    )
    data = _overpass(query)
    buildings = _overpass_to_gdf(data, kind="building")
    streets = _overpass_to_gdf(data, kind="highway")
    _save_gdf(buildings, paths[0][0])
    _save_gdf(streets, paths[0][1])
    return buildings, streets


def _google_json(req: urllib.request.Request) -> dict | None:
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _place_ll(place_id: str, key: str) -> tuple[float, float] | None:
    pid = place_id.split("/")[-1]
    req = urllib.request.Request(
        f"https://places.googleapis.com/v1/places/{urllib.parse.quote(pid)}",
        headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": "location"},
    )
    loc = (_google_json(req) or {}).get("location") or {}
    try:
        return float(loc["latitude"]), float(loc["longitude"])
    except (KeyError, TypeError, ValueError):
        return None


def _google_geocode(address: str, key: str) -> tuple[float, float] | None:
    q = urllib.parse.urlencode({"address": address, "key": key, "region": "au"})
    req = urllib.request.Request(f"https://maps.googleapis.com/maps/api/geocode/json?{q}")
    data = _google_json(req)
    if not data or data.get("status") != "OK":
        return None
    try:
        loc = data["results"][0]["geometry"]["location"]
        return float(loc["lat"]), float(loc["lng"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _nominatim(address: str) -> tuple[float, float] | None:
    queries = [address]
    if address.lower().startswith("the "):
        queries.append(address[4:])
    name = address.split(",")[0].strip()
    if name and name not in queries:
        queries.append(name)
    seen: set[str] = set()
    for q in queries:
        if q in seen:
            continue
        seen.add(q)
        req = urllib.request.Request(
            f"{NOMINATIM}?{urllib.parse.urlencode({'q': q, 'format': 'jsonv2', 'limit': 1, 'countrycodes': 'au'})}",
            headers={"User-Agent": USER_AGENT},
        )
        try:
            data = _http_json(req, timeout=10)
        except AnalyzeError:
            continue
        if isinstance(data, list) and data:
            try:
                return float(data[0]["lat"]), float(data[0]["lon"])
            except (KeyError, TypeError, ValueError):
                continue
    return None


def _geocode(address: str, place_id: str | None = None) -> tuple[float, float]:
    key = os.environ.get("GOOGLE_KEY")
    if place_id and key:
        found = _place_ll(place_id, key)
        if found:
            return found
    if key:
        found = _google_geocode(address, key)
        if found:
            return found
    found = _nominatim(address)
    if found:
        return found
    raise AnalyzeError(f"Could not find that address: {address}")


def get_json(url: str):
    try:
        with urllib.request.urlopen(url) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise AnalyzeError(f"Solar API error {e.code}: {body}") from e


def fetch_dsm(lat: float, lon: float, key: str, tif: str, radius: int) -> dict:
    bi = get_json(
        SOLAR
        + "buildingInsights:findClosest?"
        + urllib.parse.urlencode(
            {
                "location.latitude": lat,
                "location.longitude": lon,
                "requiredQuality": "BASE",
                "key": key,
            }
        )
    )
    q, c, d = bi["imageryQuality"], bi["center"], bi["imageryDate"]
    px = 0.5 if q in ("HIGH", "MEDIUM") else 1.0
    dl = get_json(
        SOLAR
        + "dataLayers:get?"
        + urllib.parse.urlencode(
            {
                "location.latitude": c["latitude"],
                "location.longitude": c["longitude"],
                "radiusMeters": radius,
                "view": "DSM_LAYER",
                "requiredQuality": q,
                "pixelSizeMeters": px,
                "key": key,
            }
        )
    )
    urllib.request.urlretrieve(dl["dsmUrl"] + "&key=" + key, tif)
    return {
        "lat": c["latitude"],
        "lon": c["longitude"],
        "quality": q,
        "date": f"{d['year']}-{d['month']:02d}-{d['day']:02d}",
    }


def compass(dx: float, dy: float) -> str:
    ang = math.degrees(math.atan2(dx, dy)) % 360
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int(((ang + 22.5) % 360) // 45)]


def runs(times, flags, step: int) -> str:
    out, start, prev = [], None, None
    for t, f in zip(times, flags):
        if f:
            start = start or t
            prev = t
        elif start:
            out.append((start, prev))
            start = None
    if start:
        out.append((start, prev))
    return ", ".join(f"{s:%H:%M}–{(e + timedelta(minutes=step)):%H:%M}" for s, e in out) or "none"


def analyze(
    address: str,
    date: str | None = None,
    *,
    place_id: str | None = None,
    streets: str | None = None,
    street_dist: float = 20,
    name: str | None = None,
    radius: int = 150,
    eye: float = 1.2,
    offset: float = 1.5,
    step: int = 5,
    table: int = 15,
    progress: Progress | None = None,
) -> dict:
    def note(msg: str) -> None:
        if progress:
            progress(msg)

    os.makedirs(CACHE_DIR, exist_ok=True)
    day = datetime.fromisoformat(date).date() if date else datetime.now(MEL).date()

    note("Finding the pub…")
    lat, lon = _geocode(address, place_id)

    slug = name or re.sub(r"[^a-z0-9]+", "_", address.lower()).strip("_")
    tif = os.path.join(CACHE_DIR, f"{slug}_dsm.tif")
    meta_path = os.path.join(CACHE_DIR, f"{slug}_dsm.json")

    if os.path.exists(tif) and os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
    else:
        key = os.environ.get("GOOGLE_KEY")
        if not key:
            raise AnalyzeError("GOOGLE_KEY is not set on the server.")
        note("Checking the neighbours so nobody steals your sun…")
        meta = fetch_dsm(lat, lon, key, tif, radius)
        with open(meta_path, "w") as f:
            json.dump(meta, f)

    # Keep the geocoded address. Solar's "closest building" can be the neighbour.

    with rasterio.open(tif) as ds:
        dsm = ds.read(1).astype(float)
        if ds.nodata is not None:
            dsm[dsm == ds.nodata] = np.nan
        T, crs, res = ds.transform, ds.crs, ds.res[0]
    H, W = dsm.shape

    note("Walking the beer garden…")
    b, st = _load_osm(lat, lon, radius, slug)
    b = b[b.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].to_crs(crs)
    if b.empty:
        raise AnalyzeError("No building footprints in OSM near that address.")
    bmask = rasterize(
        ((g, 1) for g in b.geometry),
        out_shape=(H, W),
        transform=T,
        fill=0,
        dtype="uint8",
    ).astype(bool)
    occ = np.where(bmask, dsm, np.nan)

    cx, cy = transform("EPSG:4326", crs, [lon], [lat])
    centre = Point(cx[0], cy[0])
    hits = b[b.contains(centre)]
    row = hits.iloc[0] if len(hits) else b.iloc[int(b.distance(centre).argmin())]
    pub = row.geometry
    osm_name = row["name"] if "name" in b.columns and isinstance(row.get("name"), str) else None
    ext = pub.exterior if pub.geom_type == "Polygon" else max(pub.geoms, key=lambda g: g.area).exterior

    note("Picking which footpath gets the afternoon pint…")
    st = st.to_crs(crs)
    st = st[st.geometry.geom_type.isin(["LineString", "MultiLineString"])]
    if "name" not in st.columns or "highway" not in st.columns:
        raise AnalyzeError("OSM returned roads without names near this building.")
    st = st[st["name"].notna() & ~st["highway"].astype(str).isin(NOT_STREETS)]
    groups = {n: unary_union(list(g.geometry)) for n, g in st.groupby(st["name"].astype(str))}
    if streets:
        chosen = {}
        for want in [s.strip() for s in streets.split(",")]:
            m = [n for n in groups if re.match(rf"{re.escape(want)}\b", n, re.I)]
            if not m:
                raise AnalyzeError(f"Couldn't find a street called {want} in OSM near this building.")
            chosen[m[0]] = groups[m[0]]
        street_map = chosen
    else:
        street_map = {n: g for n, g in groups.items() if pub.distance(g) <= street_dist}
        if not street_map:
            raise AnalyzeError(
                f"No named street within {street_dist} m of the building. Try a more specific address."
            )

    wall = [ext.interpolate(d) for d in np.arange(0, ext.length, 1.0)]
    snames = list(street_map)
    D = np.array([[street_map[n].distance(w) for w in wall] for n in snames])
    S = D - D.min(axis=1, keepdims=True)
    best, bestv = S.argmin(axis=0), S.min(axis=0)

    fronts = {}
    for k, n in enumerate(snames):
        idx = [i for i in range(len(wall)) if best[i] == k and bestv[i] < 1.0]
        if len(idx) < 8:
            continue
        P = np.array([[wall[i].x, wall[i].y] for i in idx])
        mid = P.mean(axis=0)
        axis = np.linalg.svd(P - mid)[2][0]
        ang = math.degrees(math.atan2(axis[0], axis[1])) % 360
        if 135 < ang <= 315:
            axis = -axis
        tpos = (P - mid) @ axis
        if tpos.max() - tpos.min() + 1 < 8:
            continue
        xs, ys = [], []
        for i in np.argsort(tpos):
            w = wall[idx[i]]
            q = nearest_points(w, street_map[n])[1]
            vx, vy = q.x - w.x, q.y - w.y
            m = math.hypot(vx, vy) or 1
            xs.append(w.x + vx / m * offset)
            ys.append(w.y + vy / m * offset)
        fronts[n] = dict(
            x=np.array(xs),
            y=np.array(ys),
            length=tpos.max() - tpos.min() + 1,
            start=compass(-axis[0], -axis[1]),
            end=compass(axis[0], axis[1]),
        )
    if not fronts:
        raise AnalyzeError("Found streets, but no wall of the building faces them.")

    allx = np.concatenate([f["x"] for f in fronts.values()])
    ally = np.concatenate([f["y"] for f in fronts.values()])
    cc = np.clip(np.floor((allx - T.c) / T.a).astype(int), 0, W - 1)
    rr = np.clip(np.floor((ally - T.f) / T.e).astype(int), 0, H - 1)
    ground = float(np.nanpercentile(dsm[rr, cc], 10))
    z0 = ground + eye

    dists = np.arange(res, math.hypot(H, W) * res, res / 2)

    def sunny(px, py, az, el):
        dx, dy = math.sin(math.radians(az)), math.cos(math.radians(az))
        t = math.tan(math.radians(el))
        shaded = np.zeros(len(px), bool)
        alive = np.ones(len(px), bool)
        for d in dists:
            c = np.floor((px + dx * d - T.c) / T.a).astype(int)
            r = np.floor((py + dy * d - T.f) / T.e).astype(int)
            alive &= (r >= 0) & (r < H) & (c >= 0) & (c < W)
            if not alive.any():
                break
            h = np.full(len(px), np.nan)
            h[alive] = occ[r[alive], c[alive]]
            with np.errstate(invalid="ignore"):
                hit = alive & (h > z0 + d * t)
            shaded |= hit
            alive &= ~hit
        return ~shaded

    note("Finding the optimal beer-drinking time…")
    start = datetime.combine(day, time(0, 0), MEL).astimezone(timezone.utc)
    times, res_by = [], {n: [] for n in fronts}
    for i in range(0, 24 * 60, step):
        t = start + timedelta(minutes=i)
        az, el = sun_position(t, lat, lon)
        if el <= 0:
            continue
        times.append(t.astimezone(MEL))
        for n, f in fronts.items():
            res_by[n].append(sunny(f["x"], f["y"], az, el))

    def to_ll(xs, ys):
        lons, lats = transform(crs, "EPSG:4326", list(xs), list(ys))
        return [{"lat": float(a), "lon": float(b)} for a, b in zip(lats, lons)]

    bx, by = ext.xy
    outline = to_ll(bx, by)

    result_fronts = []
    for n, f in fronts.items():
        arr = res_by[n]
        keep = set()
        if times:
            keep.add(0)
            keep.add(len(times) - 1)
        for k, t in enumerate(times):
            if t.minute % table == 0:
                keep.add(k)
        rows = [
            {"time": times[k].strftime("%H:%M"), "cells": [bool(s) for s in arr[k]]}
            for k in sorted(keep)
        ]
        result_fronts.append(
            {
                "name": n,
                "lengthM": round(float(f["length"]), 1),
                "start": f["start"],
                "end": f["end"],
                "someSun": runs(times, [s.any() for s in arr], step),
                "wholeFrontage": runs(times, [s.all() for s in arr], step),
                "points": to_ll(f["x"], f["y"]),
                "rows": rows,
            }
        )

    return {
        "building": {
            "name": osm_name or address,
            "lat": lat,
            "lon": lon,
            "quality": meta["quality"],
            "imageryDate": meta["date"],
            "outline": outline,
        },
        "date": day.isoformat(),
        "groundM": round(ground, 1),
        "offsetM": offset,
        "streets": list(snames),
        "fronts": result_fronts,
    }
