#!/usr/bin/env python3
"""Debug script to see what columns galah returns."""

import galah

galah.galah_config(email="m3untold@gmail.com")

# Test query
print("Fetching sample fauna...")
fauna = galah.atlas_species(
    taxa="Aves",  # Just birds for quick test
    filters=[
        "decimalLatitude>=-34",
        "decimalLatitude<=-33.5",
        "decimalLongitude>=151",
        "decimalLongitude<=151.3"
    ]
)

print(f"\nColumns returned: {list(fauna.columns)}")
print(f"\nFirst 5 rows:")
print(fauna.head())

print("\n\nSample row as dict:")
if len(fauna) > 0:
    print(fauna.iloc[0].to_dict())
