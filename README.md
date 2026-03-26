# LUTO Multiplier Explorer

A lightweight, browser-based visualisation tool for LUTO (Land-Use Trade-Offs model) input yield multiplier data. No server or build step required — open `index.html` directly in any modern browser.

## Features

- **Productivity Trend tab** — interactive line chart of yield-increase multipliers by land management type and agricultural product across five productivity scenarios (BAU, LOW, MEDIUM, HIGH, VERY_HIGH) from 2022 to 2050.
- **Climate Change Impact (CCI) tab** — side-by-side spatial maps for all four RCP/SSP scenarios plus a mean-CCI time-series chart, filterable by CO₂ fertilisation setting (ON/OFF), land management type, land use, and map year.

## Quick Start

### 1. Generate the data files

Run once from the **LUTO repo root**, inside the `luto` conda environment:

```bash
conda run -n luto python jinzhu_inspect_code/multiplier_viz/generate_data.py
```

This reads raw LUTO input files and writes pre-processed JavaScript data files into `data/`. It uses all available CPU cores for parallel map rendering and may take several minutes.

**Required LUTO input files:**
- `yieldincreases_bau2022.csv`
- `yieldincreases_ag_2050.xlsx`
- `climate_change_impacts_{rcp}_CO2_FERT_{co2}.h5` (8 files, one per RCP × CO₂ setting)

### 2. Open the visualisation

```bash
# Simply open in your browser — no server needed
open index.html        # macOS
start index.html       # Windows
xdg-open index.html    # Linux
```

## Project Structure

```
multiplier_viz/
├── index.html              # Single-page application (Bootstrap 5 + Apache ECharts)
├── generate_data.py        # ETL script — run once to produce data files
├── README.md
└── data/
    ├── productivity.js                 # Productivity trend data
    ├── cci_means.js                    # CCI spatial means
    ├── cci_layers_rcp2p6_ON.js         # CCI map images (SSP1-2.6, CO₂ ON)
    ├── cci_layers_rcp2p6_OFF.js        # CCI map images (SSP1-2.6, CO₂ OFF)
    ├── cci_layers_rcp4p5_ON.js         # CCI map images (SSP2-4.5, CO₂ ON)
    ├── cci_layers_rcp4p5_OFF.js        # ... and so on for rcp6p0, rcp8p5
    └── ...
```

## RCP / SSP Scenarios

| Key | Label | Colour |
|---|---|---|
| rcp2p6 | SSP1-2.6 | Blue |
| rcp4p5 | SSP2-4.5 | Green |
| rcp6p0 | SSP3-6.0 | Orange |
| rcp8p5 | SSP5-8.5 | Red |

## Map Legend

CCI maps use the **RdBu_r** diverging colormap centred at **1.0** (no change):
- **Blue** — climate benefit (multiplier > 1)
- **Red** — climate-driven yield loss (multiplier < 1)
- **Grey** — public / non-agricultural land
- **White** — ocean / outside Australia

## Dependencies

`index.html` loads from CDN — no local install needed:
- [Bootstrap 5.3.3](https://getbootstrap.com/)
- [Apache ECharts 5.5.0](https://echarts.apache.org/)

`generate_data.py` requires the `luto` conda environment with:
`numpy`, `pandas`, `xarray`, `matplotlib`, `joblib`, and the LUTO package itself.
