# Species Browser — Chimera Seed Vocabulary

A tool for curating a place-based species vocabulary for the Chimera ecology system.

Browse species from the Atlas of Living Australia (ALA) and flag those that feel like meaningful kin. The exported vocabulary becomes the foundation for chimeric archetypes grounded in local ecology.

## Why Place-Based

Chimeras can't be universal archetypes. They need to be composed of kin from the land your body is actually on. This tool helps you build a personal seed vocabulary from species that occur in your bioregion and that have felt meaning to you.

## Quick Start

### 1. Install dependencies

```bash
pip install galah-python
```

### 2. Fetch species for your region

```bash
python fetch_species.py --email your@email.com
```

This queries ALA for fauna, flora, and fungi in the Sydney Basin region and saves to `species.json`.

Options:
- `--limit N` — Max species to fetch (default: 500)
- `--with-images` — Also fetch thumbnail images (slower)
- `--output FILE` — Output filename (default: species.json)

### 3. Run the browser

```bash
python -m http.server 8000
```

Then open http://localhost:8000

### 4. Browse and flag

- **Meaningful Kin** — Species that have felt relationship to you
- **Maybe** — Worth revisiting
- **Skip** — Not meaningful (for now)

Add notes about qualities, felt sense, or relationships.

### 5. Export

Click "Export Seed Vocabulary" to download a JSON file with your flagged species, ready for the Chimera system.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1` or `k` | Flag as Meaningful Kin |
| `2` or `m` | Flag as Maybe |
| `3` or `s` | Skip |
| `←` or `h` | Previous species |
| `→` or `l` | Next species |

## Customizing Region

Edit `fetch_species.py` to change the geographic bounds:

```python
SYDNEY_BASIN_BOUNDS = {
    "lat_min": -34.2,
    "lat_max": -33.4,
    "lon_min": 150.5,
    "lon_max": 151.5
}
```

Use [bboxfinder.com](http://bboxfinder.com/) to find bounds for your area.

## Output Format

The exported `seed_vocabulary_YYYY-MM-DD.json` contains:

```json
{
  "country": "Bidjigal Country / Sydney Basin",
  "meaningful_kin": [
    {
      "common_name": "Laughing Kookaburra",
      "scientific_name": "Dacelo novaeguineae",
      "taxon_group": "fauna",
      "family": "Alcedinidae",
      "notes": "dawn caller, patient hunter",
      "niche_affinities": [],
      "qualities": []
    }
  ],
  "maybe_kin": [...],
  "summary": {...}
}
```

The `niche_affinities` and `qualities` fields are placeholders for manual enrichment — mapping species to chimera niches (grip/predator, flow/migratory, etc.) and relational qualities.

## Data Source

Species data from [Atlas of Living Australia](https://www.ala.org.au/) via the [galah Python package](https://galah.ala.org.au/Python/).

## Acknowledgment

This tool operates on Bidjigal Country. We acknowledge the Traditional Custodians and their continuing connection to land, waters, and community.

---

Part of [Earthian-BioSense](https://github.com/...) — biosignal acquisition for the Earthian Ecological Coherence Protocol.
