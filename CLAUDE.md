# CLAUDE.md — multiplier_viz

## Project Overview
A standalone browser-based visualisation tool for **LUTO** (Land-Use Trade-Offs model) input yield multiplier data. It exposes two interactive views:

1. **Productivity Trend** — time-series multipliers by land management type and product (BAU through VERY_HIGH scenarios, 2022–2050)
2. **Climate Change Impact (CCI)** — spatial maps and mean time-series of per-cell CCI multipliers across four RCP scenarios (SSP1-2.6 → SSP5-8.5) and two CO₂ fertilisation settings (ON/OFF)

## Architecture

```
multiplier_viz/
├── index.html          # Single-page app (Bootstrap 5 + Apache ECharts)
├── generate_data.py    # One-off ETL: reads LUTO source files → writes data/
└── data/
    ├── productivity.js            # window['PRODUCTIVITY_DATA']
    ├── cci_means.js               # window['CCI_MEANS']
    └── cci_layers_{rcp}_{co2}.js  # window['CCI_LAYERS'] (8 files, one per RCP×CO₂)
```

**Data flow:** `generate_data.py` (Python/LUTO env) → JS data files → `index.html` reads them as `<script>` tags, no server required.

## Key Files
- [index.html](index.html) — all UI logic (vanilla JS, no build step)
- [generate_data.py](generate_data.py) — ETL script; must be run from the LUTO repo root inside the `luto` conda env
- [data/](data/) — generated data files (`.gitignore`d if large)

## Running generate_data.py
From the LUTO **repo root** (two levels above this directory):
```bash
conda run -n luto python jinzhu_inspect_code/multiplier_viz/generate_data.py
```
This reads:
- `INPUT_DIR/yieldincreases_bau2022.csv`
- `INPUT_DIR/yieldincreases_ag_2050.xlsx` (sheets: low, medium, high, very_high)
- `INPUT_DIR/climate_change_impacts_{rcp}_CO2_FERT_{co2}.h5` (8 files)

Outputs ~8 JS files into `data/`. Parallel map rendering via `joblib`.

## Data Globals
| JS global | Set by | Contents |
|---|---|---|
| `window.PRODUCTIVITY_DATA` | `productivity.js` | trends, lms, products, years, nested data dict |
| `window.CCI_MEANS` | `cci_means.js` | rcps, co2_ferts, lms, lus, lm_lu_combos, spatial means |
| `window.CCI_LAYERS` | `cci_layers_*.js` (8) | base64 JPEG maps keyed by `rcp__co2` → `lm__lu` → year |

## Coding Conventions
- `index.html` uses ES5-compatible vanilla JS (no transpiler, no bundler)
- ECharts for charts, Bootstrap 5 for layout
- No backend required — open `index.html` directly in a browser
- Map images are base64 JPEG embedded in JS (RdBu_r colormap centred at 1.0; grey = non-agricultural land)
