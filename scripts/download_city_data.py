#!/usr/bin/env python3
"""Download all real city data for Mumbai and Vijayawada.

Downloads:
  - Digital Elevation Models (DEMs) via OpenTopography Copernicus GLO-30 API
  - Stormwater Drain Networks via Overpass API (OSM waterways)
  - Road Networks via Overpass API (OSM highways)

Outputs:
  data/raw/mumbai/mumbai_dem.tif
  data/raw/mumbai/mumbai_drains.geojson
  data/raw/mumbai/mumbai_roads.geojson
  data/raw/vijayawada/vijayawada_dem.tif
  data/raw/vijayawada/vijayawada_drains.geojson
  data/raw/vijayawada/vijayawada_roads.geojson

Usage:
    python scripts/download_city_data.py
    python scripts/download_city_data.py --city mumbai
    python scripts/download_city_data.py --only dem
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"

OPENTOPO_API_KEY = "b3a926c9fadf4d5794c50d24588f59a6"
OPENTOPO_BASE = "https://portal.opentopography.org/API/globaldem"
# Overpass mirrors — tried in order, first success wins
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
# Correct headers for Overpass POST (GET with [out:json] in URL causes 406)
OVERPASS_HEADERS = {
    "User-Agent": "UFNS-SIH26085/1.0 (Urban Flood Nowcasting System; research use)",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json",
}

CITIES: dict[str, dict] = {
    "mumbai": {
        "bbox": {"west": 72.75, "south": 18.88, "east": 72.98, "north": 19.28},
        "epsg": 32643,
        "out_dir": RAW_DIR / "mumbai",
        "dem_file":    "mumbai_dem.tif",
        "drains_file": "mumbai_drains.geojson",
        "roads_file":  "mumbai_roads.geojson",
    },
    "vijayawada": {
        "bbox": {"west": 80.55, "south": 16.45, "east": 80.72, "north": 16.58},
        "epsg": 32644,
        "out_dir": RAW_DIR / "vijayawada",
        "dem_file":    "vijayawada_dem.tif",
        "drains_file": "vijayawada_drains.geojson",
        "roads_file":  "vijayawada_roads.geojson",
    },
}


def _sha256(path: Path) -> str:
    """Execute  Sha256 operation and return result."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _save(data: bytes, path: Path) -> None:
    """Execute  Save operation and return result."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    size_kb = len(data) / 1024
    sha = _sha256(path)
    print(f"    OK  Saved  {path.relative_to(REPO_ROOT)}  ({size_kb:.1f} KB)  sha256:{sha[:16]}...")


def download_dem(city: str, cfg: dict) -> bool:
    """Execute Download Dem operation and return result."""
    bbox = cfg["bbox"]
    out_path = cfg["out_dir"] / cfg["dem_file"]
    if out_path.exists():
        print(f"  [DEM] {city}: already exists -> {out_path.relative_to(REPO_ROOT)}")
        return True
    params = urllib.parse.urlencode({
        "demtype": "COP30", "south": bbox["south"], "north": bbox["north"],
        "west": bbox["west"], "east": bbox["east"],
        "outputFormat": "GTiff", "API_Key": OPENTOPO_API_KEY,
    })
    url = f"{OPENTOPO_BASE}?{params}"
    print(f"  [DEM] {city}: fetching Copernicus GLO-30 ...")
    print(f"        {url}")
    for attempt in range(1, 4):
        try:
            data = urllib.request.urlopen(url, timeout=300).read()
            if data[:4] not in (b"II*\x00", b"MM\x00*"):
                print(f"  [DEM] {city}: WARNING - Not a TIFF. Response: {data[:200].decode(errors='replace')}")
                return False
            _save(data, out_path)
            return True
        except Exception as exc:
            print(f"  [DEM] {city}: attempt {attempt} FAILED - {exc}")
            if attempt < 3:
                wait = 20 * attempt
                print(f"  [DEM] {city}: waiting {wait}s before retry ...")
                time.sleep(wait)
    return False



def _overpass_drain_query(bbox: dict) -> str:
    """Execute  Overpass Drain Query operation and return result."""
    s, w, n, e = bbox["south"], bbox["west"], bbox["north"], bbox["east"]
    tags = ["drain","ditch","canal","stream","river","culvert"]
    lines = "\n".join(f'  way["waterway"="{t}"]({s},{w},{n},{e});' for t in tags)
    return f"[out:json][timeout:120];\n(\n{lines}\n);\nout body;\n>;\nout skel qt;"


def _overpass_road_query(bbox: dict) -> str:
    """Execute  Overpass Road Query operation and return result."""
    s, w, n, e = bbox["south"], bbox["west"], bbox["north"], bbox["east"]
    rtypes = ["motorway","trunk","primary","secondary","tertiary","residential",
              "service","unclassified","living_street","motorway_link","trunk_link",
              "primary_link","secondary_link"]
    lines = "\n".join(f'  way["highway"="{rt}"]({s},{w},{n},{e});' for rt in rtypes)
    return f"[out:json][timeout:120];\n(\n{lines}\n);\nout body;\n>;\nout skel qt;"


def _osm_to_geojson(osm_json: dict) -> dict:
    """Execute  Osm To Geojson operation and return result."""
    nodes: dict[int, tuple] = {
        e["id"]: (e["lon"], e["lat"])
        for e in osm_json.get("elements", []) if e["type"] == "node"
    }
    features = []
    for elem in osm_json.get("elements", []):
        if elem["type"] != "way":
            continue
        coords = [nodes[nid] for nid in elem.get("nodes", []) if nid in nodes]
        if len(coords) < 2:
            continue
        features.append({
            "type": "Feature",
            "id": elem["id"],
            "properties": {"osm_id": elem["id"], **elem.get("tags", {})},
            "geometry": {"type": "LineString", "coordinates": coords},
        })
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "source": "OpenStreetMap via Overpass API",
            "license": "ODbL 1.0 (c) OpenStreetMap contributors",
            "feature_count": len(features),
        },
    }


def _run_overpass(query: str, label: str, retries: int = 3) -> dict | None:
    """POST form-data to Overpass with User-Agent header, trying each mirror.

    Root cause of 406: GET with ?data=... URL-encodes [ ] as %5B %5D which
    Overpass rejects. Correct protocol is POST with Content-Type:
    application/x-www-form-urlencoded and a proper User-Agent header.
    """
    post_data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    for mirror in OVERPASS_MIRRORS:
        for attempt in range(1, retries + 1):
            try:
                req = urllib.request.Request(
                    mirror, data=post_data, headers=OVERPASS_HEADERS, method="POST"
                )
                with urllib.request.urlopen(req, timeout=150) as resp:
                    raw = resp.read()
                result = json.loads(raw)
                print(f"        [{label}] success via {mirror}")
                return result
            except urllib.error.HTTPError as exc:
                body = exc.read().decode(errors="replace")[:150]
                print(f"    [{label}] {mirror} attempt {attempt}: HTTP {exc.code}")
                if attempt < retries:
                    time.sleep(10 * attempt)
            except Exception as exc:
                print(f"    [{label}] {mirror} attempt {attempt}: {exc}")
                if attempt < retries:
                    time.sleep(10 * attempt)
        print(f"    [{label}] mirror {mirror} exhausted, trying next ...")
    return None


def download_drains(city: str, cfg: dict) -> bool:
    """Execute Download Drains operation and return result."""
    out_path = cfg["out_dir"] / cfg["drains_file"]
    if out_path.exists():
        print(f"  [DRN] {city}: already exists -> {out_path.relative_to(REPO_ROOT)}")
        return True
    print(f"  [DRN] {city}: querying Overpass for waterways ...")
    osm = _run_overpass(_overpass_drain_query(cfg["bbox"]), f"DRN/{city}")
    if osm is None:
        return False
    geojson = _osm_to_geojson(osm)
    print(f"        {len(geojson['features'])} drain/canal features retrieved")
    _save(json.dumps(geojson, ensure_ascii=False, indent=2).encode(), out_path)
    return True


def download_roads(city: str, cfg: dict) -> bool:
    """Execute Download Roads operation and return result."""
    out_path = cfg["out_dir"] / cfg["roads_file"]
    if out_path.exists():
        print(f"  [RDS] {city}: already exists -> {out_path.relative_to(REPO_ROOT)}")
        return True
    print(f"  [RDS] {city}: querying Overpass for road network ...")
    osm = _run_overpass(_overpass_road_query(cfg["bbox"]), f"RDS/{city}")
    if osm is None:
        return False
    geojson = _osm_to_geojson(osm)
    print(f"        {len(geojson['features'])} road features retrieved")
    _save(json.dumps(geojson, ensure_ascii=False, indent=2).encode(), out_path)
    return True


def write_manifest(city: str, cfg: dict) -> None:
    """Execute Write Manifest operation and return result."""
    manifest = {"city": city, "bbox": cfg["bbox"], "epsg": cfg["epsg"], "files": {}}
    for key in ("dem_file", "drains_file", "roads_file"):
        p = cfg["out_dir"] / cfg[key]
        if p.exists():
            manifest["files"][cfg[key]] = {"size_bytes": p.stat().st_size, "sha256": _sha256(p)}
    mf = cfg["out_dir"] / "manifest.json"
    mf.write_text(json.dumps(manifest, indent=2))
    print(f"  [MF]  Manifest -> {mf.relative_to(REPO_ROOT)}")


def main() -> None:
    """Execute Main operation and return result."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", choices=list(CITIES) + ["all"], default="all")
    parser.add_argument("--only", choices=["dem", "drains", "roads", "all"], default="all")
    args = parser.parse_args()

    target_cities = list(CITIES) if args.city == "all" else [args.city]
    do_dem    = args.only in ("dem",    "all")
    do_drains = args.only in ("drains", "all")
    do_roads  = args.only in ("roads",  "all")

    overall_ok = True
    for city in target_cities:
        cfg = CITIES[city]
        cfg["out_dir"].mkdir(parents=True, exist_ok=True)
        print(f"\n{'='*60}")
        print(f"  CITY: {city.upper()}")
        print(f"  BBox: W={cfg['bbox']['west']} S={cfg['bbox']['south']} E={cfg['bbox']['east']} N={cfg['bbox']['north']}")
        print(f"{'='*60}")
        results = []
        if do_dem:    results.append(download_dem(city, cfg))
        if do_drains: results.append(download_drains(city, cfg))
        if do_roads:  results.append(download_roads(city, cfg))
        write_manifest(city, cfg)
        if not all(results):
            overall_ok = False

    print("\n" + "="*60)
    if overall_ok:
        print("  ALL DOWNLOADS COMPLETE")
        print("  Next: python scripts/run_dashboard.py  ->  http://127.0.0.1:8000")
    else:
        print("  SOME DOWNLOADS FAILED - check output above")
    print("="*60)
    sys.exit(0 if overall_ok else 1)


if __name__ == "__main__":
    main()
