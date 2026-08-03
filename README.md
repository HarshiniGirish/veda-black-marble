# VEDA Black Marble

Nighttime lights processing pipeline for NASA VEDA, combining VIIRS nighttime lights with Landsat data to create urban-focused imagery.

This fork adds **MAAP DPS / OGC packaging**. Upstream science code: [NASA-IMPACT/veda-black-marble](https://github.com/NASA-IMPACT/veda-black-marble).

## Installation

Requires Python 3.11+.

```bash
git clone https://github.com/HarshiniGirish/veda-black-marble.git
cd veda-black-marble
pip install -e .
# or with uv
uv pip install -e .
```

## Authentication

**Do not pass an Earthdata token as a DPS job or CLI argument** — it appears in job logs in plain text.

| Environment | How auth works |
|-------------|----------------|
| **MAAP ADE / DPS** | Injected `MAAP_PGT` + `maap-py` inside `blackmarble/acquire/viirs.py` (no token job input) |
| **Local / non-MAAP** | Optional `EARTHDATA_TOKEN` env var or `~/.netrc` for the earthaccess fallback |

Authorize needed Earthdata apps on your [URS profile](https://urs.earthdata.nasa.gov/) (e.g. LAADS for VNP46A2).

## Quick Start 

```bash
# Optional for local earthaccess fallback only — not used as a DPS job arg
export EARTHDATA_TOKEN="your-token-here"

blackmarble \
  --bbox "-122.55,37.69,-122.32,37.81" \
  --date 2023-06-15 \
  --output-path san_francisco_lights.tif
```

Run `blackmarble --help` for full CLI options.

## MAAP DPS

Packaging files: `run.sh`, `build.sh`, `environment.yml`, `algorithm_config.yml`, `maap_dps_algorithm_config.yml`.

### DPS inputs

| Name | Example | Notes |
|------|---------|--------|
| `bbox` | `-122.55,37.69,-122.32,37.81` | required; lat span ≥ 0.05° |
| `date` | `2023-06-15` | required |
| `config` | `fast` | `default` / `high_quality` / `fast` |
| `osm_source` | `overpass` | or `layercake` |
| `wgs84` | `false` | also write EPSG:4326 |
| `basename` | `san_francisco_lights` | see below |

There is **no** `earthdata_token` (or similar) job input.

### `basename` vs `--output-path`

| | Meaning |
|---|---------|
| `--output-path` / `-o` | Full COG path for the science CLI (e.g. `san_francisco_lights.tif`) |
| `basename` (DPS) | Filename **stem** only |

`run.sh` maps:

```text
basename=san_francisco_lights  →  --output-path output/san_francisco_lights.tif
```

### Example local DPS entrypoint

```bash
./run.sh \
  --bbox "-122.55,37.69,-122.32,37.81" \
  --date 2023-06-15 \
  --config fast \
  --basename san_francisco_lights
```

### Submit a job (ADE)

```python
from maap.maap import MAAP

maap = MAAP()
job = maap.submitJob(
    identifier="black-marble-smoke",
    algo_id="veda-black-marble",
    version="main",
    queue="maap-dps-worker-16gb",
    bbox="-122.55,37.69,-122.32,37.81",
    date="2023-06-15",
    config="fast",
    osm_source="overpass",
    wgs84="false",
    basename="san_francisco_lights",
)
print(job)
```

## OSM Sources

Road data can be fetched from either:

- `overpass` (default): Overpass API queries via OSMnx
- `layercake`: OpenStreetMap US [Layercake parquet](https://openstreetmap.us/our-work/layercake/) source

Layercake can be faster over large or dense areas, but is experimental and may not be as fresh.

## Example

```bash
blackmarble \
  --bbox "2.08,48.80,2.42,48.92" \
  --date 2023-08-01 \
  --config high_quality \
  --wgs84 \
  --output-path paris_lights_hq.tif
```

## Documentation

For detailed algorithm documentation (QA masking, temporal compositing, urban field enhancement), see [`docs/pipeline-steps/`](docs/pipeline-steps/). Start with [`README.md`](docs/pipeline-steps/README.md).

## Python API

```python
from blackmarble.pipeline import pipeline
from datetime import datetime

result = pipeline(
    bbox=(-122.55, 37.69, -122.32, 37.81),  # (min_lon, min_lat, max_lon, max_lat)
    date=datetime(2023, 6, 15),
    output_path="san_francisco.tif",
)
```

## Module Organization

```
blackmarble/
├── acquire/          # Downloads: Landsat, VIIRS, OSM roads
│   ├── landsat.py
│   ├── viirs.py      # VNP46A2 (maap-py on MAAP; earthaccess locally)
│   └── osm.py
├── prepare/          # QA and spatial prep
├── analyze/          # Indices, temporal composite, urban fields
├── enhance/          # Contrast / visualization
└── export/           # COG + metadata
```

## Output

- Cloud-Optimized GeoTIFF with embedded metadata
- RGB visualization (inferno colormap)
- Optional EPSG:4326 export (`--wgs84` / DPS `wgs84=true`)
- Optional diagnostics (`--save-diagnostics`)

## Requirements

- Python 3.11+
- NASA Earthdata account (free) for VIIRS; on MAAP, use ADE login + authorized apps
- ~8GB RAM for typical ~100×100 km regions
- On MAAP DPS: `maap-py` (see `environment.yml`)

## License

[Apache License 2.0](LICENSE) — National Aeronautics and Space Administration (NASA)

Originally created by NASA Goddard Earth Sciences

## Contributing

Issues and pull requests welcome. Upstream: https://github.com/NASA-IMPACT/veda-black-marble/issues
