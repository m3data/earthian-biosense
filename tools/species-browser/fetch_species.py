#!/usr/bin/env python3
"""
Fetch species from Atlas of Living Australia for a given bioregion.
Saves to species.json for the browser UI.

Usage:
    python fetch_species.py --email your@email.com

Requires: pip install galah-python
"""

import argparse
import json
from pathlib import Path

try:
    import galah
except ImportError:
    print("Please install galah: pip install galah-python")
    exit(1)


# Sydney Basin / Bidjigal Country approximate bounds
SYDNEY_BASIN_BOUNDS = {
    "lat_min": -34.2,
    "lat_max": -33.4,
    "lon_min": 150.5,
    "lon_max": 151.5
}


def fetch_species_for_region(email: str, bounds: dict, limit: int = 500) -> list:
    """Fetch fauna and flora species for a geographic region."""

    galah.galah_config(email=email)

    filters = [
        f"decimalLatitude>={bounds['lat_min']}",
        f"decimalLatitude<={bounds['lat_max']}",
        f"decimalLongitude>={bounds['lon_min']}",
        f"decimalLongitude<={bounds['lon_max']}"
    ]

    species_list = []

    # Helper to extract row data with galah's column names
    def extract_species(row, taxon_group):
        return {
            "scientific_name": str(row.get("Species Name", "")),
            "common_name": str(row.get("Vernacular Name", "")),
            "taxon_group": taxon_group,
            "class": str(row.get("Class", "")),
            "family": str(row.get("Family", "")),
            "genus": str(row.get("Genus", "")),
            "order": str(row.get("Order", ""))
        }

    # Fetch fauna (animals)
    print("Fetching fauna...")
    try:
        fauna = galah.atlas_species(taxa="Animalia", filters=filters)
        print(f"  Found {len(fauna)} fauna species")

        for _, row in fauna.head(limit // 2).iterrows():
            species_list.append(extract_species(row, "fauna"))
    except Exception as e:
        print(f"  Error fetching fauna: {e}")

    # Fetch flora (plants)
    print("Fetching flora...")
    try:
        flora = galah.atlas_species(taxa="Plantae", filters=filters)
        print(f"  Found {len(flora)} flora species")

        for _, row in flora.head(limit // 2).iterrows():
            species_list.append(extract_species(row, "flora"))
    except Exception as e:
        print(f"  Error fetching flora: {e}")

    # Fetch fungi
    print("Fetching fungi...")
    try:
        fungi = galah.atlas_species(taxa="Fungi", filters=filters)
        print(f"  Found {len(fungi)} fungi species")

        for _, row in fungi.head(100).iterrows():
            species_list.append(extract_species(row, "fungi"))
    except Exception as e:
        print(f"  Error fetching fungi: {e}")

    return species_list


def fetch_species_images(species_list: list) -> list:
    """Fetch thumbnail images for species from ALA BIE search API."""
    import urllib.request
    import urllib.parse
    import time

    print("Fetching images from ALA...")
    images_found = 0

    for i, species in enumerate(species_list):
        if not species["scientific_name"]:
            continue

        try:
            # Use BIE search API which returns image URLs
            name = urllib.parse.quote(species["scientific_name"])
            url = f"https://bie.ala.org.au/ws/search?q={name}&fq=rank:species"

            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode())
                results = data.get("searchResults", {}).get("results", [])

                if results:
                    result = results[0]
                    # Try different image URL fields
                    image_url = (
                        result.get("smallImageUrl") or
                        result.get("thumbnailUrl") or
                        result.get("imageUrl")
                    )
                    if image_url:
                        species["image_url"] = image_url
                        images_found += 1

                    # Also grab common name if we don't have one
                    if not species.get("common_name") or species["common_name"] == "nan":
                        common = result.get("commonNameSingle") or result.get("commonName")
                        if common:
                            species["common_name"] = common

            # Be nice to the API
            time.sleep(0.1)

        except Exception as e:
            pass

        if (i + 1) % 25 == 0:
            print(f"  Processed {i + 1}/{len(species_list)} species ({images_found} images found)")

    print(f"  Found images for {images_found}/{len(species_list)} species")
    return species_list


def main():
    parser = argparse.ArgumentParser(description="Fetch species from ALA")
    parser.add_argument("--email", required=True, help="Your ALA registered email")
    parser.add_argument("--no-images", action="store_true", help="Skip fetching thumbnail images")
    parser.add_argument("--limit", type=int, default=500, help="Max species to fetch")
    parser.add_argument("--output", default="species.json", help="Output file")

    args = parser.parse_args()

    print(f"Fetching species for Sydney Basin region...")
    print(f"Bounds: {SYDNEY_BASIN_BOUNDS}")
    print()

    species_list = fetch_species_for_region(args.email, SYDNEY_BASIN_BOUNDS, args.limit)

    if not args.no_images:
        species_list = fetch_species_images(species_list)

    # Clean up None values and empty strings
    for species in species_list:
        for key, value in list(species.items()):
            if value == "nan" or value == "None" or value is None:
                species[key] = ""

    # Sort by common name (with fallback to scientific name)
    species_list.sort(key=lambda s: s.get("common_name") or s.get("scientific_name") or "")

    output_path = Path(__file__).parent / args.output
    with open(output_path, "w") as f:
        json.dump({
            "region": {
                "name": "Bidjigal Country / Sydney Basin",
                "bounds": SYDNEY_BASIN_BOUNDS,
                "acknowledgment": "This tool operates on Bidjigal Country. We acknowledge the Traditional Custodians and their continuing connection to land, waters, and community."
            },
            "fetched_at": str(__import__("datetime").datetime.now().isoformat()),
            "species": species_list
        }, f, indent=2)

    print()
    print(f"Saved {len(species_list)} species to {output_path}")
    print(f"Run 'python -m http.server 8000' in this directory and open http://localhost:8000")


if __name__ == "__main__":
    main()
