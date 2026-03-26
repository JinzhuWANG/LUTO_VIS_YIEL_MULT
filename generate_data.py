"""
generate_data.py
================
Run once to produce all JS data files consumed by index.html.

Output: multiplier_viz/data/
  productivity.js          window['PRODUCTIVITY_DATA']
  cci_means.js             window['CCI_MEANS']
  cci_layers_{rcp}_{co2}.js  (8 files)  window['CCI_LAYERS']['{rcp}__{co2}']

Usage (from repo root):
  conda run -n luto python jinzhu_inspect_code/multiplier_viz/generate_data.py
"""

import os, sys, io, json, base64, warnings
import numpy as np
import pandas as pd
import xarray as xr
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path
from joblib import Parallel, delayed

warnings.filterwarnings('ignore')

# ── Paths ──────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
os.chdir(REPO_ROOT)
sys.path.insert(0, str(REPO_ROOT))

import luto.settings as settings
import luto.simulation as sim

OUT_DIR = Path(__file__).parent / 'data'
OUT_DIR.mkdir(exist_ok=True)

# ── Config ─────────────────────────────────────────────────────────────────
RCP_LIST      = ['rcp2p6', 'rcp4p5', 'rcp6p0', 'rcp8p5']
CO2_FERT_LIST = ['ON', 'OFF']
PROD_TRENDS   = ['BAU', 'LOW', 'MEDIUM', 'HIGH', 'VERY_HIGH']
YEAR_CLIP     = 2050
N_JOBS        = -1     # -1 = all cores
FIG_W, FIG_H  = 6.0, 4.2
DPI           = 150
JPEG_QUALITY  = 75
VMIN_OVERRIDE = None   # set to float to override auto-detected range
VMAX_OVERRIDE = None


# ═══════════════════════════════════════════════════════════════════════════
# Module-level render worker  (must be top-level for loky pickling)
# ═══════════════════════════════════════════════════════════════════════════
def _render_map_job(arr_1d, vmin, vmax, lumap_2d, coord_r, coord_c, nodata):
    """Convert a 1-D spatial array → base64 JPEG string.
    - NaN (ocean / outside Australia) : white background
    - -1  (public / non-agricultural) : light grey
    - CCI values                       : RdBu_r centred at 1.0
    All arguments are plain numpy arrays — no LUTO objects needed.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as _plt
    import matplotlib.colors as _mc
    import io as _io, base64 as _b64, numpy as _np

    # ── Build 2-D array ──────────────────────────────────────────────────
    arr_2d = lumap_2d.copy().astype(_np.float32)
    arr_2d[coord_r, coord_c] = arr_1d                    # place CCI values
    arr_2d = _np.where(arr_2d == nodata, _np.nan, arr_2d)  # ocean → NaN

    # ── Masks ─────────────────────────────────────────────────────────────
    public_mask = (arr_2d == -1)                          # non-ag land
    data_arr    = _np.where(public_mask, _np.nan, arr_2d) # hide -1 from cmap

    # ── Plot ──────────────────────────────────────────────────────────────
    fig, ax = _plt.subplots(figsize=(FIG_W, FIG_H))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')

    # Layer 1: light grey for public / non-ag land
    grey_rgba = _np.zeros((*arr_2d.shape, 4), dtype=_np.float32)
    grey_rgba[public_mask] = [0.82, 0.82, 0.82, 1.0]
    ax.imshow(grey_rgba, aspect='auto', interpolation='nearest')

    # Layer 2: CCI data (NaN → transparent, so ocean stays white)
    cmap = _plt.cm.RdBu_r.copy()
    cmap.set_bad(alpha=0.0)
    norm = _mc.Normalize(vmin=vmin, vmax=vmax)
    im = ax.imshow(data_arr, cmap=cmap, norm=norm,
                   aspect='auto', interpolation='nearest')

    _plt.colorbar(im, ax=ax, shrink=0.72, pad=0.02, fraction=0.03)
    ax.axis('off')
    _plt.tight_layout(pad=0.3)

    buf = _io.BytesIO()
    fig.savefig(buf, format='jpeg', dpi=DPI, bbox_inches='tight',
                pil_kwargs={'quality': JPEG_QUALITY})
    _plt.close(fig)
    buf.seek(0)
    return 'data:image/jpeg;base64,' + _b64.b64encode(buf.read()).decode()


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':

    # ── 1. Load LUTO data (for MASK + spatial metadata) ────────────────────
    print('Loading LUTO data ...')
    settings.SIM_YEARS  = [2010, 2020, 2030, 2040, 2050]
    settings.RESFACTOR  = 5
    data = sim.load_data()
    print(f'  NCELLS={data.NCELLS}, RESFACTOR={settings.RESFACTOR}')

    # Extract spatial metadata as plain arrays for worker pickling
    lumap_2d = data.LUMAP_2D_RESFACTORED.copy()
    coord_r  = data.COORD_ROW_COL_RESFACTORED[0]
    coord_c  = data.COORD_ROW_COL_RESFACTORED[1]
    nodata   = float(data.NODATA)

    # ── 2. Productivity trend multipliers ──────────────────────────────────
    print('\nExtracting productivity trend data ...')

    def _load_prod_xr(trend):
        if trend == 'BAU':
            df = pd.read_csv(
                os.path.join(settings.INPUT_DIR, 'yieldincreases_bau2022.csv'),
                header=[0, 1]).astype(np.float32)
            df.index = df.index + data.YR_CAL_BASE
            df.index.name = 'Year'
            return (xr.DataArray(df)
                    .unstack('dim_1')
                    .rename({'Year': 'year', 'dim_1_level_0': 'lm', 'dim_1_level_1': 'product'}))
        else:
            df = pd.read_excel(
                os.path.join(settings.INPUT_DIR, 'yieldincreases_ag_2050.xlsx'),
                sheet_name=trend.lower(), header=[0, 1], index_col=0).astype(np.float32)
            return (xr.DataArray(df)
                    .unstack('dim_1')
                    .rename({'Year': 'lm', 'dim_1_level_1': 'product', 'dim_0': 'year'}))

    prod_data = {}
    ref_xr = _load_prod_xr('BAU')
    all_lms  = ref_xr.coords['lm'].values.tolist()
    all_prods = ref_xr.coords['product'].values.tolist()

    for trend in PROD_TRENDS:
        xr_t  = _load_prod_xr(trend)
        years = [int(y) for y in xr_t.coords['year'].values if int(y) <= YEAR_CLIP]
        prod_data[trend] = {}
        for lm in all_lms:
            prod_data[trend][lm] = {}
            for prod in all_prods:
                vals = xr_t.sel(lm=lm, product=prod).values
                prod_data[trend][lm][prod] = {
                    int(y): round(float(v), 6)
                    for y, v in zip(xr_t.coords['year'].values, vals)
                    if int(y) <= YEAR_CLIP
                }

    prod_js_obj = {
        'trends': PROD_TRENDS,
        'lms': all_lms,
        'products': all_prods,
        'years': [int(y) for y in ref_xr.coords['year'].values if int(y) <= YEAR_CLIP],
        'data': prod_data,
    }
    with open(OUT_DIR / 'productivity.js', 'w') as f:
        f.write("window['PRODUCTIVITY_DATA'] = ")
        json.dump(prod_js_obj, f, separators=(',', ':'))
        f.write(';')
    sz = (OUT_DIR / 'productivity.js').stat().st_size / 1024
    print(f'  Saved productivity.js  ({sz:.0f} KB, {len(all_prods)} products)')


    # ── 3. CCI: load all data, compute means, collect map jobs ─────────────
    print('\nLoading CCI files and collecting map jobs ...')

    def _load_cci_df(rcp, co2_fert):
        fpath = os.path.join(
            settings.INPUT_DIR,
            f'climate_change_impacts_{rcp}_CO2_FERT_{co2_fert}.h5')
        return pd.read_hdf(fpath, where=data.MASK)

    # Metadata from reference file
    ref_df        = _load_cci_df('rcp4p5', 'ON')
    lm_lu_year    = ref_df.columns.tolist()
    lm_lu_year_set = set(lm_lu_year)
    lm_lu_combos  = sorted({(lm, lu) for lm, lu, _ in lm_lu_year})
    cci_lms       = sorted({lm for lm, _ in lm_lu_combos})
    cci_lus       = sorted({lu for _, lu in lm_lu_combos})

    # Global colormap range from reference file (non-baseline years)
    sample = ref_df.values.ravel()
    sample = sample[~np.isnan(sample)]
    p1, p99 = np.nanpercentile(sample, 1), np.nanpercentile(sample, 99)
    spread = max(abs(1.0 - p1), abs(p99 - 1.0))
    VMIN = VMIN_OVERRIDE if VMIN_OVERRIDE else round(1.0 - spread, 3)
    VMAX = VMAX_OVERRIDE if VMAX_OVERRIDE else round(1.0 + spread, 3)
    print(f'  {len(lm_lu_combos)} valid (lm,lu) combos | plot range [{VMIN:.3f}, {VMAX:.3f}]')
    del ref_df

    # Initialise means structure
    cci_means = {
        co2: {lm: {lu: {} for lu in cci_lus} for lm in cci_lms}
        for co2 in CO2_FERT_LIST
    }

    # Collect all map jobs: (job_key, arr_1d)
    map_jobs = []   # (key, arr)

    for co2_fert in CO2_FERT_LIST:
        for rcp in RCP_LIST:
            print(f'  Loading {rcp} CO2={co2_fert} ...', flush=True)
            df = _load_cci_df(rcp, co2_fert)

            for lm, lu in lm_lu_combos:
                lmlu = f'{lm}__{lu}'
                cci_means[co2_fert][lm][lu].setdefault(rcp, {})[2010] = 1.0

                for yr in [2020, 2050]:
                    if (lm, lu, yr) not in lm_lu_year_set:
                        continue
                    arr = df[(lm, lu, yr)].fillna(1.0).values.astype(np.float32)
                    cci_means[co2_fert][lm][lu][rcp][yr] = round(float(np.nanmean(arr)), 6)
                    map_jobs.append((f'{rcp}__{co2_fert}__{lmlu}__{yr}', arr))

            del df

    print(f'\n  Total map jobs: {len(map_jobs)}')


    # ── 4. Parallel render all maps ─────────────────────────────────────────
    print(f'\nRendering {len(map_jobs)} maps in parallel (n_jobs={N_JOBS}) ...')

    b64_list = Parallel(n_jobs=N_JOBS, backend='loky', verbose=5)(
        delayed(_render_map_job)(arr, VMIN, VMAX, lumap_2d, coord_r, coord_c, nodata)
        for _, arr in map_jobs
    )

    rendered = {key: b64 for (key, _), b64 in zip(map_jobs, b64_list)}
    print('  Rendering complete.')


    # ── 5. Assemble per-(rcp, co2_fert) layer dicts and save JS ────────────
    print('\nAssembling and saving JS layer files ...')

    for co2_fert in CO2_FERT_LIST:
        for rcp in RCP_LIST:
            layers = {}
            for lm, lu in lm_lu_combos:
                lmlu = f'{lm}__{lu}'
                layers[lmlu] = {}

                for yr in [2020, 2050]:
                    k = f'{rcp}__{co2_fert}__{lmlu}__{yr}'
                    if k in rendered:
                        layers[lmlu][yr] = rendered[k]

            js_key   = f'{rcp}__{co2_fert}'
            js_fname = OUT_DIR / f'cci_layers_{rcp}_{co2_fert}.js'
            with open(js_fname, 'w') as f:
                f.write("window['CCI_LAYERS'] = window['CCI_LAYERS'] || {};\n")
                f.write(f"window['CCI_LAYERS']['{js_key}'] = ")
                json.dump(layers, f, separators=(',', ':'))
                f.write(';')
            sz = js_fname.stat().st_size / 1e6
            print(f'  {js_fname.name}  ({sz:.1f} MB)')


    # ── 6. Save cci_means.js ───────────────────────────────────────────────
    cci_means_obj = {
        'rcps':       RCP_LIST,
        'co2_ferts':  CO2_FERT_LIST,
        'lms':        cci_lms,
        'lus':        cci_lus,
        'lm_lu_combos': [[lm, lu] for lm, lu in lm_lu_combos],
        'years':      [2020, 2050],
        'vmin':       VMIN,
        'vmax':       VMAX,
        'data':       cci_means,
    }
    with open(OUT_DIR / 'cci_means.js', 'w') as f:
        f.write("window['CCI_MEANS'] = ")
        json.dump(cci_means_obj, f, separators=(',', ':'))
        f.write(';')
    sz = (OUT_DIR / 'cci_means.js').stat().st_size / 1024
    print(f'\nSaved cci_means.js  ({sz:.0f} KB)')
    print('\nAll done!  Open index.html to explore.')
