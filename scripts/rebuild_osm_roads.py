import json
import math
import os
import pyproj
from pathlib import Path

def generate_city_roads(city_name: str, raw_geojson_path: str, utm_crs: str, out_path: str, full_out_path: str):
    print(f"\n==================================================")
    print(f" Rebuilding OpenStreetMap Road Network: {city_name.upper()}")
    print(f"==================================================")
    
    with open(raw_geojson_path, "r", encoding="utf-8") as f:
        geojson = json.load(f)

    transformer = pyproj.Transformer.from_crs("EPSG:4326", utm_crs, always_xy=True)

    allowed_fclasses = {
        "motorway", "trunk", "primary", "secondary", "tertiary",
        "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
        "residential", "living_street", "unclassified", "service"
    }

    speed_map = {
        "motorway": 80.0, "trunk": 65.0, "primary": 50.0,
        "secondary": 40.0, "tertiary": 30.0,
        "motorway_link": 50.0, "trunk_link": 45.0, "primary_link": 35.0, "secondary_link": 30.0, "tertiary_link": 25.0,
        "residential": 25.0, "living_street": 20.0, "unclassified": 25.0, "service": 15.0
    }

    nodes = {}
    edges = []

    features = geojson.get("features", [])
    print(f"Loaded {len(features)} raw features from {raw_geojson_path}")

    for idx, feat in enumerate(features):
        props = feat.get("properties", {})
        fclass = props.get("fclass") or props.get("highway") or "residential"
        if fclass not in allowed_fclasses:
            continue

        geom = feat.get("geometry", {})
        coords = geom.get("coordinates", [])
        geom_type = geom.get("type")

        if geom_type == "LineString" and len(coords) >= 2:
            lines = [coords]
        elif geom_type == "MultiLineString":
            lines = coords
        else:
            continue

        raw_name = props.get("name") or props.get("ref") or fclass.replace("_", " ").title()
        speed_kmh = speed_map.get(fclass, 25.0)

        for line_idx, line in enumerate(lines):
            if len(line) < 2:
                continue

            utm_coords = []
            for pt in line:
                ux, uy = transformer.transform(pt[0], pt[1])
                utm_coords.append([round(ux, 2), round(uy, 2)])

            start_pt = utm_coords[0]
            end_pt = utm_coords[-1]
            start_id = f"N_{int(start_pt[0])}_{int(start_pt[1])}"
            end_id = f"N_{int(end_pt[0])}_{int(end_pt[1])}"

            if start_id not in nodes:
                nodes[start_id] = {"id": start_id, "x": start_pt[0], "y": start_pt[1]}
            if end_id not in nodes:
                nodes[end_id] = {"id": end_id, "x": end_pt[0], "y": end_pt[1]}

            length_m = sum(
                math.hypot(utm_coords[i][0] - utm_coords[i-1][0], utm_coords[i][1] - utm_coords[i-1][1])
                for i in range(1, len(utm_coords))
            )

            edge_id = f"{city_name[:3].upper()}_{props.get('osm_id', idx)}_{line_idx}"
            edges.append({
                "edge_id": edge_id,
                "from_node": start_id,
                "to_node": end_id,
                "highway": fclass,
                "name": raw_name,
                "length_m": round(length_m, 1),
                "baseline_speed_kmh": speed_kmh,
                "geometry": utm_coords,
                "osm_id": props.get("osm_id", str(idx)),
            })

    print(f"Processed {len(edges)} total OpenStreetMap road corridors across {len(nodes)} intersection nodes")
    
    out_data = {
        "city": city_name,
        "crs": utm_crs,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges
    }
    
    # Write full road_graph.json
    with open(full_out_path, "w", encoding="utf-8") as f:
        json.dump(out_data, f)
    full_mb = os.path.getsize(full_out_path) / (1024 * 1024)
    print(f"Saved full road graph to {full_out_path} ({full_mb:.2f} MB)")

    # For filtered graph, retain up to 30,000 corridors
    filtered_edges = edges[:30000]
    filt_data = {
        "city": city_name,
        "crs": utm_crs,
        "node_count": len(nodes),
        "edge_count": len(filtered_edges),
        "nodes": nodes,
        "edges": filtered_edges
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(filt_data, f)
    filt_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"Saved filtered road graph to {out_path} ({filt_mb:.2f} MB)")

if __name__ == "__main__":
    generate_city_roads(
        "mumbai",
        "data/raw/mumbai/mumbai_roads.geojson",
        "EPSG:32643",
        "data/processed/mumbai/road_graph_filtered.json",
        "data/processed/mumbai/road_graph.json"
    )
    generate_city_roads(
        "vijayawada",
        "data/raw/vijayawada/vijayawada_roads.geojson",
        "EPSG:32644",
        "data/processed/vijayawada/road_graph_filtered.json",
        "data/processed/vijayawada/road_graph.json"
    )
    print("\nAll OpenStreetMap city road networks successfully rebuilt and written!")
