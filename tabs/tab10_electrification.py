"""
Electrification scenarios (static analysis).

Native Streamlit port of the standalone `electrification_final.html` tool. The data is a frozen
snapshot (NOT part of the monthly refresh) extracted once by `data/static_tools/extract_from_html.py`:

  * electrification_meta.json         goal (IEA), labels, scenario rules / order / basis
  * electrification_summary.json.gz   nested per rate x scenario results (curves, breakdowns, segments)
  * electrification_picks.parquet     one row per asset x strategy pick (reductions, energy, activity)
  * electrification_assets.parquet    per rate x scenario ordered list of picks + cost
  * electrification_asset_names.parquet

Scaled-integer columns in the parquet files: red_nt_x10 / red_at_x10 (tCO2e/yr x 10),
tjf_x100 / tje_x100 (TJ x 100). They are converted back in ASSET_SQL below.

Terminology: f = fuel energy replaced (TJ), e = electricity added (TJ). "Clean Grid" scenarios use the
reduction at the asset (red_at); "BAU Grid" scenarios use the net reduction after grid emissions (red_nt).
"""
import base64
import gzip
import html as _html
import io
import json
import math

import duckdb
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import CONFIG

# ── Palette ───────────────────────────────────────────────────────────────────
# Sector colours reuse the dashboard's SECTOR_COLORS (buildings / transportation / manufacturing).
_SECTOR_BASE = {
    'buildings': '#03A0E3',
    'transportation': '#FBBA14',
    'manufacturing': '#9554FF',
}
SUB_COLOR = {
    'residential-onsite-fuel-usage': _SECTOR_BASE['buildings'],
    'non-residential-onsite-fuel-usage': '#0B7FB5',   # a deeper shade of the buildings colour
    'road-transportation': _SECTOR_BASE['transportation'],
    'iron-and-steel': _SECTOR_BASE['manufacturing'],
}
SUB_LABEL = {
    'residential-onsite-fuel-usage': 'Residential buildings',
    'non-residential-onsite-fuel-usage': 'Non-residential buildings',
    'road-transportation': 'Road transportation',
    'iron-and-steel': 'Iron and steel',
}
SUB_SHORT = {
    'residential-onsite-fuel-usage': 'Residential',
    'non-residential-onsite-fuel-usage': 'Non-residential',
    'road-transportation': 'Road',
    'iron-and-steel': 'Steel',
}
ACT_UNIT = {
    'residential-onsite-fuel-usage': 'MJ',
    'non-residential-onsite-fuel-usage': 'MJ',
    'road-transportation': 'vehicle-km',
    'iron-and-steel': 't',
}
# one colour per scenario family; a scenario's Clean Grid and BAU Grid versions share it
FAMILY = ['average', 'reductions', 'lowest_cost', 'cost_100', 'cost_150', 'cost_250', 'usd_cost', 'usd_hybrid']
FAMILY_COLORS = ['#1B998B', '#9B59B6', '#2E86C1', '#E67E22', '#A1887F', '#D81B60', '#C9A227', '#7CB342']
COUNTRY_ALL = 'All countries (global)'
SAVING_COLOR, COST_COLOR = '#5cb85c', '#d9534f'   # green = net saving (negative cost), red = net cost; as on the other pages
SECTORS_TEXT = 'iron & steel, buildings and road transportation'
CONT_COLOR = {'Africa': '#E4572E', 'Asia': '#76B041', 'Europe': '#2E86AB', 'North America': '#F29E4C',
              'Oceania': '#9C89B8', 'South America': '#BC4B51', 'Antarctica': '#9A9A9A'}
REGION_COLOR = {'Global North': '#2A6F97', 'Global South': '#E09F3E'}
ANNEX_COLOR = {'Annex 1': '#5B8E7D', 'Non-Annex 1': '#B8860B'}
BASIS_LABEL = {'at_asset': 'Clean Grid', 'net': 'BAU Grid'}
GRAY = '#9A9A9A'

VIEWS = [
    ('strategy', 'By strategy'), ('sector', 'By sector'), ('continent', 'By continent / region'),
    ('country', 'By country (top 15)'), ('top', 'Top 1,000 assets'), ('share', 'Top 10% of reductions'),
    ('goal', 'Goal (35x35)'),
]
CHARTS = [
    ('energy', 'Goal energy vs emissions reduced (share)'),
    ('assets', 'Assets vs emissions reduced (35x35)'),
    ('cost', 'Cost abatement vs emissions reduced (total)'),
]


# ── Loading / caching ─────────────────────────────────────────────────────────

@st.cache_resource(show_spinner="Loading electrification scenarios…")
def _load_static():
    with open(CONFIG['electrification_meta_path'], encoding='utf-8') as f:
        meta = json.load(f)
    with gzip.open(CONFIG['electrification_summary_path'], 'rt', encoding='utf-8') as f:
        summary = json.load(f)
    return meta, summary


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_df(sql):
    con = duckdb.connect()
    try:
        return con.execute(sql).df()
    finally:
        con.close()


def _asset_sql(rate, scen, basis, limit=None):
    """Ordered asset list of one scenario (rows in the scenario's own order)."""
    red_col = 'red_nt_x10' if basis == 'net' else 'red_at_x10'
    lim = f"LIMIT {int(limit)}" if limit else ""
    return f"""
        SELECT a."rank" AS rank, p.asset_id, n.asset_name, p.country, p.subsector, p.strategy,
               p.{red_col} / 10.0 AS red,
               (0.65 * p.tje_x100 + 0.35 * p.tjf_x100) / 100.0 AS tj,
               a.cost AS cost, p.activity AS activity,
               p.red_nt_x10 / 10.0 AS red_nt, p.red_at_x10 / 10.0 AS red_at, a.cp AS cp,
               p.tjf_x100 / 100.0 AS tjf, p.tje_x100 / 100.0 AS tje
        FROM '{CONFIG['electrification_assets_path']}' a
        JOIN '{CONFIG['electrification_picks_path']}' p USING (pick_id)
        LEFT JOIN '{CONFIG['electrification_asset_names_path']}' n ON n.asset_id = p.asset_id
        WHERE a.rate = '{rate}' AND a.scenario = '{scen}'
        ORDER BY a."rank"
        {lim}
    """


def _assets(rate, scen, basis, limit=None):
    df = _cached_df(_asset_sql(rate, scen, basis, limit))
    df['asset_name'] = df['asset_name'].fillna('')
    return df


# ── Formatting helpers (ports of the HTML tool's helpers) ─────────────────────

def _ok(v):
    return v is not None and not (isinstance(v, float) and not math.isfinite(v))


def fmt(v, d=0):
    return f"{v:,.{d}f}" if _ok(v) else "–"


def pct(v, d=1):
    if not _ok(v):
        return "–"
    dd = 2 if (d == 1 and v != 0 and abs(v) < 0.001) else d   # tiny shares get a second decimal
    return f"{v * 100:,.{dd}f}%"


def share(v, tot):
    return pct(v / tot) if tot and tot > 0 else "–"


def ej(tj):
    if abs(tj) < 1e5 and tj != 0:
        return f"{fmt(tj / 1e3, 1)} PJ"
    return f"{fmt(tj / 1e6, 1)} EJ"


def gt(v):
    return f"{fmt(v / 1e9, 2)} GtCO₂e"


def gtmt(v):
    return gt(v) if abs(v) >= 1e8 else f"{fmt(v / 1e6, 1)} MtCO₂e"


def mt(v):
    return fmt(v / 1e6, 3 if (abs(v) < 1e5 and v != 0) else 1)


def money(v):
    if not _ok(v):
        return "–"
    sign = '-$' if v < 0 else '$'
    a = abs(v)
    if a >= 1e9:
        return f"{sign}{a / 1e9:,.2f}B"
    if a >= 1e6:
        return f"{sign}{a / 1e6:,.1f}M"
    return f"{sign}{round(a):,}"


def per_t(cost, red):
    return "–" if (not _ok(cost) or not (red and red > 0)) else money(cost / red)


def big_fmt(v):
    a = abs(v)
    if a >= 1e12:
        return f"{v / 1e12:,.1f}T"
    if a >= 1e9:
        return f"{v / 1e9:,.1f}B"
    if a >= 1e6:
        return f"{v / 1e6:,.1f}M"
    return f"{round(v):,}"


def sum_key(rows, key):
    return sum((r.get(key) or 0) for r in rows)


def sum_cost(rows):
    return sum_key(rows, 'cost')


def sum_cp(rows):
    return sum_key(rows, 'cp')


def share_after(f, e, g):
    """Electricity share of final energy demand after replacing f TJ of fuel with e TJ of electricity."""
    return (g['electricity_ej'] + e / 1e6) / (g['demand_ej'] - (f - e) / 1e6)


def _nan(v):
    return float('nan') if v is None else v


# ── Tiles ─────────────────────────────────────────────────────────────────────

_TILE_CSS = """
<style>
.el-tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 6px 0 14px; }
.el-tile { background: rgba(128,128,128,0.10); border: 1px solid rgba(128,128,128,0.28); color: inherit;
           border-radius: 10px; padding: 12px 14px; }
.el-tile.hl { border-color: var(--el-accent, #1E7F8C); }
.el-tile .k { font-size: 0.82rem; text-transform: uppercase; letter-spacing: .04em; opacity: .75; font-weight: 600; }
.el-tile .v { font-size: 1.45rem; font-weight: 650; margin-top: 3px; }
.el-tile .p { font-size: 0.92rem; opacity: .9; margin-top: 4px; }
.el-tile .p2 { font-size: 0.86rem; opacity: .72; margin-top: 4px; }
.el-tile .of { font-size: 0.9rem; font-weight: 400; opacity: .7; }
.el-tag { font-size: 0.78rem; border: 1px solid rgba(128,128,128,0.5); border-radius: 999px; padding: 0 7px; opacity: .8; }
.el-tiles[style] .el-tile { border-top: 3px solid var(--el-accent); }
[data-testid="stCaptionContainer"] { font-size: 0.92rem; }
.el-legend { margin: 2px 0 10px; line-height: 1.9; }
.el-chip { display: inline-flex; align-items: center; gap: 7px; margin: 0 14px 0 0; font-size: 0.85rem; white-space: nowrap; }
.el-chip i { display: inline-block; width: 24px; height: 0; border-top: 3px solid var(--c); }
.el-chip i.bau { border-top-style: dashed; }
.el-chip.sel { font-weight: 700; }
.el-h { border-left: 6px solid var(--c); padding-left: 10px; margin: 6px 0 2px; font-size: 1.6rem; font-weight: 650; }
.el-tbl-wrap { overflow-x: auto; margin: 4px 0 6px; }
.el-tbl { width: 100%; min-width: 1200px; border-collapse: collapse; font-size: 15px; border: none; }
.el-tbl th, .el-tbl td { border: none; }
.el-tbl th { text-align: right; font-weight: 600; font-size: 13px; line-height: 1.25; padding: 8px 6px; vertical-align: bottom;
             border-bottom: 1px solid rgba(128,128,128,0.4); opacity: .85; min-width: 66px; }
.el-tbl th:first-child, .el-tbl td:first-child { text-align: left; }
.el-tbl th:first-child { min-width: 360px; }
.el-tbl td { padding: 9px 6px; text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums;
             border-bottom: 1px solid rgba(128,128,128,0.16); }
.el-tbl td.el-name { white-space: nowrap; }
.el-tbl td.el-neg { color: #5cb85c; font-weight: 600; }
.el-tbl td.el-pos { color: #d9534f; font-weight: 600; }
.el-note { font-size: 0.92rem; opacity: .85; margin: 2px 0 6px; }
.el-tbl tbody tr:hover { background: rgba(128,128,128,0.08); }
.el-scn { display: inline-flex; align-items: center; gap: 12px; }
.el-scn img { flex: none; }
.el-goalbar { margin: 6px 0 4px; }
.el-goalbar-track { position: relative; height: 30px; border-radius: 8px; background: rgba(128,128,128,0.18); overflow: hidden; }
.el-goalbar-now { position: absolute; left: 0; top: 0; bottom: 0; background: #1E7F8C; }
.el-goalbar-gap { position: absolute; top: 0; bottom: 0; display: flex; align-items: center; justify-content: center;
                  background: repeating-linear-gradient(135deg, rgba(30,127,140,0.50) 0 7px, rgba(30,127,140,0.30) 7px 14px); color: inherit;
                  font-size: 14px; font-weight: 650; white-space: nowrap; }
.el-goalbar-goal { position: absolute; top: 0; bottom: 0; width: 3px; margin-left: -3px; background: currentColor; }
.el-goalbar-labels { position: relative; height: 22px; margin-top: 6px; font-size: 14px; opacity: .9; }
.el-goalbar-labels span { position: absolute; white-space: nowrap; }
@media (max-width: 900px) { .el-tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
"""


def _cost_span(text, v):
    color = SAVING_COLOR if v < 0 else COST_COLOR
    return f'<span style="color:{color}">{text}</span>'


def _total_cost_tile(cost, cp):
    """Tile for the scenario's total cost: says 'Net saving' (green) when negative, 'Net cost' (red) otherwise."""
    if not _ok(cost):
        return ('Total cost', '–', None, None)
    saving = cost < 0
    detail = (f"ERS net present value {money(cost - cp)} + clean power {money(cp)}; " if cp else 'ERS net present value; ')
    return ('Net saving' if saving else 'Net cost', _cost_span(money(abs(cost)), cost), None,
            detail + ('the picked strategies save money overall' if saving else 'the picked strategies cost money overall'))


def _per_t_tile(cost, red, p=None):
    """Cost (or saving) per tonne: a negative cost per tonne is shown as a green 'Saving per tCO₂e'."""
    if not _ok(cost) or not (red and red > 0):
        return ('Cost per tCO₂e', '–', p, 'total cost ÷ emissions reduced per year')
    x = cost / red
    return ('Saving per tCO₂e' if x < 0 else 'Cost per tCO₂e', _cost_span(money(abs(x)), x), p,
            'total saving ÷ emissions reduced per year' if x < 0 else 'total cost ÷ emissions reduced per year')


def _cost_note():
    st.markdown(f'<div class="el-note"><span style="color:{SAVING_COLOR};font-weight:650">Green</span> = net saving '
                f'(a negative cost) · <span style="color:{COST_COLOR};font-weight:650">Red</span> = net cost.</div>',
                unsafe_allow_html=True)


_COST_COLS = ('Total cost ($B)', 'Total cost ($M)', 'Cost per tCO₂e/yr ($)', 'Net present value ($M)', 'Net present value ($)')


def _cost_style(v):
    if v is None or (isinstance(v, float) and not math.isfinite(v)) or v == 0:
        return ''
    return f'color: {SAVING_COLOR if v < 0 else COST_COLOR}; font-weight: 600'


def _tiles(items, accent=None):
    """items: (key, value, p, p2, highlight). p / p2 are optional HTML snippets."""
    cells = []
    for it in items:
        k, v, p, p2, hl = (list(it) + [None, None, False])[:5] if len(it) < 5 else it
        cells.append(
            f'<div class="el-tile{" hl" if hl else ""}"><div class="k">{k}</div><div class="v">{v}</div>'
            + (f'<div class="p">{p}</div>' if p else '')
            + (f'<div class="p2">{p2}</div>' if p2 else '') + '</div>'
        )
    style = f' style="--el-accent:{accent}"' if accent else ''
    st.markdown(f'<div class="el-tiles"{style}>{"".join(cells)}</div>', unsafe_allow_html=True)


# ── Plotly helpers ────────────────────────────────────────────────────────────

def _base_layout(fig, height=480, **kw):
    fig.update_layout(
        height=height, margin=dict(l=60, r=20, t=30, b=60), paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)', font=dict(size=14), **kw,
    )
    fig.update_xaxes(gridcolor='rgba(128,128,128,0.2)', zerolinecolor='rgba(128,128,128,0.5)')
    fig.update_yaxes(gridcolor='rgba(128,128,128,0.2)', zerolinecolor='rgba(128,128,128,0.5)')
    return fig


def _stack_fig(rows, name_of, color_of, height=130):
    """Two 100% stacked horizontal bars: share of assets and share of reductions."""
    fig = go.Figure()
    for r in rows:
        nm = name_of(r)
        fig.add_bar(
            y=['By number of assets', 'By reductions'], x=[max(r['assets'], 0), max(r['red'], 0)], name=nm,
            orientation='h', marker_color=color_of(r), hovertemplate=f'{nm}: %{{x:,.0f}}<extra></extra>',
        )
    fig.update_layout(barmode='stack', barnorm='percent', showlegend=True,
                      legend=dict(orientation='h', yanchor='bottom', y=1.02, x=0))
    _base_layout(fig, height=height + 40)
    fig.update_layout(margin=dict(l=130, r=10, t=30, b=20))
    fig.update_xaxes(ticksuffix='%', range=[0, 100])
    fig.update_yaxes(autorange='reversed')
    return fig


# ── Table builders ────────────────────────────────────────────────────────────

_C = st.column_config


def _cfg_breakdown(first_label, with_activity=False, with_cost=True, extra_cols=None):
    cfg = {
        first_label: _C.TextColumn(first_label),
        'Assets': _C.NumberColumn('Assets', format='localized'),
        '% of assets': _C.NumberColumn('% of assets', format='%.1f'),
        'Reductions (MtCO₂e/yr)': _C.NumberColumn('Reductions (MtCO₂e/yr)', format='%.2f'),
        '% of reductions': _C.NumberColumn('% of reductions', format='%.1f'),
        'Fuel replaced (EJ)': _C.NumberColumn('Fuel replaced (EJ)', format='%.2f'),
        'Electricity added (EJ)': _C.NumberColumn('Electricity added (EJ)', format='%.2f'),
        'Net present value ($M)': _C.NumberColumn('Net present value ($M)', format='%.1f'),
        'Cost per tCO₂e/yr ($)': _C.NumberColumn('Cost per tCO₂e/yr ($)', format='%.0f'),
        '% of reductions at negative cost': _C.NumberColumn('% of reductions at negative cost', format='%.1f'),
    }
    if with_activity:
        cfg['Activity'] = _C.NumberColumn('Activity', format='compact')
    if extra_cols:
        cfg.update(extra_cols)
    return cfg


def _breakdown_df(rows, first_label, name_of, activity_unit=None, total=True):
    """Generic breakdown table (sector / continent / region / annex / strategy / country)."""
    A = sum_key(rows, 'assets')
    R = sum_key(rows, 'red')
    recs = []
    for r in rows:
        rec = {
            first_label: name_of(r), 'Assets': r['assets'],
            '% of assets': (r['assets'] / A * 100) if A else float('nan'),
            'Reductions (MtCO₂e/yr)': r['red'] / 1e6,
            '% of reductions': (r['red'] / R * 100) if R > 0 else float('nan'),
            'Fuel replaced (EJ)': r['tjf'] / 1e6, 'Electricity added (EJ)': r['tje'] / 1e6,
            'Net present value ($M)': _nan(r.get('cost')) / 1e6 if r.get('cost') is not None else float('nan'),
            'Cost per tCO₂e/yr ($)': (r['cost'] / r['red']) if (r.get('cost') is not None and r['red'] > 0) else float('nan'),
            '% of reductions at negative cost': (r['neg'] / r['red'] * 100) if r['red'] > 0 else float('nan'),
        }
        if activity_unit:
            rec['Activity'] = _nan(r.get('act'))
        recs.append(rec)
    if total and recs:
        C = sum_cost(rows)
        tot = {
            first_label: 'Total', 'Assets': A, '% of assets': float('nan'), 'Reductions (MtCO₂e/yr)': R / 1e6,
            '% of reductions': float('nan'), 'Fuel replaced (EJ)': sum_key(rows, 'tjf') / 1e6,
            'Electricity added (EJ)': sum_key(rows, 'tje') / 1e6, 'Net present value ($M)': C / 1e6,
            'Cost per tCO₂e/yr ($)': (C / R) if R > 0 else float('nan'),
            '% of reductions at negative cost': (sum_key(rows, 'neg') / R * 100) if R > 0 else float('nan'),
        }
        if activity_unit:
            tot['Activity'] = float('nan')
        recs.append(tot)
    return pd.DataFrame(recs)


def _show(df, cfg, height=None, key=None):
    cols = [c for c in _COST_COLS if c in df.columns]
    data = df.style.map(_cost_style, subset=cols) if cols else df
    st.dataframe(data, column_config=cfg, hide_index=True, use_container_width=True, height=height, key=key)


def _sector_block(rows, many, with_cost=True):
    rows = [r for r in rows if r['assets'] > 0]
    st.markdown('##### By sector')
    if many and rows:
        st.plotly_chart(_stack_fig(rows, lambda r: SUB_LABEL[r['subsector']], lambda r: SUB_COLOR[r['subsector']]),
                        use_container_width=True, key=f"sec_{id(rows)}_{many}")
    df = _breakdown_df(rows, 'Sector', lambda r: SUB_LABEL[r['subsector']], activity_unit=True)
    # activity is sector specific: show it as text with its unit (blank on the Total row)
    df['Activity'] = [
        (f"{big_fmt(r['act'])} {ACT_UNIT[r['subsector']]}" if _ok(r.get('act')) else '') for r in rows
    ] + [''] * (len(df) - len(rows))
    cfg = _cfg_breakdown('Sector', extra_cols={'Activity': _C.TextColumn('Activity (sector units)')})
    if not with_cost:
        df = df.drop(columns=['Net present value ($M)', 'Cost per tCO₂e/yr ($)', '% of reductions at negative cost'])
    _show(df, cfg)


def _group_block(title, rows, colors, key):
    st.markdown(f'##### {title}')
    if not rows:
        return
    st.plotly_chart(_stack_fig(rows, lambda r: r['name'], lambda r: colors.get(r['name'], GRAY)),
                    use_container_width=True, key=f'grp_{key}')
    label = title.replace('By ', '')
    _show(_breakdown_df(rows, label, lambda r: r['name']), _cfg_breakdown(label))


def _share_blocks(st_set, key):
    _group_block('By continent', st_set['continents'], CONT_COLOR, key + '_c')
    _group_block('By Global North / South', st_set['regions'], REGION_COLOR, key + '_r')
    _group_block('By Annex 1 / Non-Annex 1', st_set['annexes'], ANNEX_COLOR, key + '_a')


def _country_sector_fig(countries, subsectors):
    fig = go.Figure()
    names = [c['name'] for c in countries]
    for i, sub in enumerate(subsectors):
        vals = [max(c['by_sector_red'][i], 0) / 1e6 for c in countries]
        fig.add_bar(y=names, x=vals, name=SUB_LABEL[sub], orientation='h', marker_color=SUB_COLOR[sub],
                    hovertemplate='%{y} · ' + SUB_LABEL[sub] + ': %{x:,.2f} MtCO₂e/yr<extra></extra>')
    fig.update_layout(barmode='stack', legend=dict(orientation='h', yanchor='bottom', y=1.02, x=0))
    _base_layout(fig, height=max(320, 26 * len(countries) + 90))
    fig.update_layout(margin=dict(l=130, r=10, t=40, b=40))
    fig.update_yaxes(autorange='reversed')
    fig.update_xaxes(title='Positive reductions by sector (MtCO₂e/yr)')
    return fig


def _countries_table(countries, set_assets, set_red, many, one_sector, subsectors, key, title=None, total_red=None):
    title = title or f'Top {len(countries)} countries'
    st.markdown(f'##### {title}')
    if not countries:
        st.caption('No countries.')
        return
    if many:
        st.plotly_chart(_country_sector_fig(countries, subsectors), use_container_width=True, key=f'cty_{key}')
    recs = []
    for i, c in enumerate(countries, 1):
        recs.append({
            '#': i, 'Country': c['name'], 'Assets': c['assets'],
            '% of assets': (c['assets'] / set_assets * 100) if set_assets else float('nan'),
            'Reductions (MtCO₂e/yr)': c['red'] / 1e6,
            '% of reductions': (c['red'] / set_red * 100) if set_red and set_red > 0 else float('nan'),
            'Fuel replaced (EJ)': c['tjf'] / 1e6, 'Electricity added (EJ)': c['tje'] / 1e6,
            'Net present value ($M)': (c['cost'] / 1e6) if c.get('cost') is not None else float('nan'),
            'Cost per tCO₂e/yr ($)': (c['cost'] / c['red']) if (c.get('cost') is not None and c['red'] > 0) else float('nan'),
            '% of reductions at negative cost': (c['neg'] / c['red'] * 100) if c['red'] > 0 else float('nan'),
        })
    cfg = _cfg_breakdown('Country', extra_cols={'#': _C.NumberColumn('#', format='%d')})
    _show(pd.DataFrame(recs), cfg, height=min(560, 40 + 35 * len(recs)))


def _asset_table(df, title, key):
    st.markdown(f'##### {title}')
    if df is None or df.empty:
        st.caption('No assets.')
        return
    out = pd.DataFrame({
        '#': df['rank'].astype(int),
        'Asset': [n or f'Asset {i}' for n, i in zip(df['asset_name'], df['asset_id'])],
        'Country': df['country'].astype(str), 'Sector': [SUB_SHORT[s] for s in df['subsector']],
        'Strategy': df['strategy'].astype(str),
        'Reductions (tCO₂e/yr)': df['red'], 'Energy (TJ)': df['tj'],
        'Activity': [('' if pd.isna(a) else f"{big_fmt(a)} {ACT_UNIT[s]}") for a, s in zip(df['activity'], df['subsector'])],
        'Net present value ($)': df['cost'].astype('float64'),
        'Cost per tCO₂e/yr ($)': [(c / r) if (pd.notna(c) and r > 0) else float('nan') for c, r in zip(df['cost'], df['red'])],
    })
    cfg = {
        '#': _C.NumberColumn('#', format='%d', width='small'),
        'Reductions (tCO₂e/yr)': _C.NumberColumn('Reductions (tCO₂e/yr)', format='%.0f'),
        'Energy (TJ)': _C.NumberColumn('Energy (TJ)', format='%.1f'),
        'Net present value ($)': _C.NumberColumn('Net present value ($)', format='%.0f'),
        'Cost per tCO₂e/yr ($)': _C.NumberColumn('Cost per tCO₂e/yr ($)', format='%.0f'),
    }
    _show(out, cfg, height=420, key=f'assets_{key}')


def _line_uri(color, dashed):
    """A small SVG of the scenario's chart line (solid = Clean Grid, dashed = BAU Grid), identical length either way."""
    dash = ' stroke-dasharray="8 6.67"' if dashed else ''
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="56" height="16"><line x1="2" y1="8" x2="54" y2="8" '
           f'stroke="{color}" stroke-width="3.5"{dash}/></svg>')
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode()


def _scenario_table(df, names, colors, is_bau, fmts, selected=None, name_col='Scenario'):
    """HTML table for the scenario comparisons: each row starts with the scenario's chart line (solid = Clean Grid,
    dashed = BAU Grid) drawn inline next to its name, so there is no separate bordered column."""
    head = ''.join(f'<th>{_html.escape(c)}</th>' for c in df.columns)
    rows = []
    for n, (_, r) in zip(names, df.iterrows()):
        tint = f' style="background: color-mix(in srgb, {colors[n]} 13%, transparent)"' if n == selected else ''
        cells = [f'<td class="el-name"><span class="el-scn"><img src="{_line_uri(colors[n], is_bau(n))}" width="56" height="16">'
                 f'<span>{_html.escape(str(r[name_col]))}</span></span></td>']
        for c in df.columns[1:]:
            v = r[c]
            if v is None or (isinstance(v, float) and not math.isfinite(v)):
                cells.append('<td>–</td>')
            else:
                cls = (' class="el-neg"' if v < 0 else (' class="el-pos"' if v > 0 else '')) if c in _COST_COLS else ''
                cells.append(f'<td{cls}>{fmts.get(c, "{:,.1f}").format(v)}</td>')
        rows.append(f'<tr{tint}>{"".join(cells)}</tr>')
    st.markdown(f'<div class="el-tbl-wrap"><table class="el-tbl"><thead><tr>{head}</tr></thead>'
                f'<tbody>{"".join(rows)}</tbody></table></div>', unsafe_allow_html=True)


_GLOBAL_FMTS = {
    'Assets': '{:,.0f}', 'Countries': '{:,.0f}', 'Strategies': '{:,.0f}', 'Fuel replaced (EJ)': '{:,.1f}',
    'Electricity added (EJ)': '{:,.1f}', 'Electricity share (%)': '{:,.1f}', 'Emissions reduced (GtCO₂e)': '{:,.2f}',
    '% of emissions': '{:,.1f}', 'Total cost ($B)': '{:,.1f}', 'Cost per tCO₂e/yr ($)': '{:,.0f}',
    '% at negative cost': '{:,.1f}', 'Reduction % of baseline': '{:,.0f}', 'Cost per tCO₂e % of baseline': '{:,.0f}',
}
_COUNTRY_FMTS = dict(_GLOBAL_FMTS, **{
    'Fuel replaced (EJ)': '{:,.2f}', 'Electricity added (EJ)': '{:,.2f}', 'Emissions reduced (MtCO₂e)': '{:,.2f}',
    'Total cost ($M)': '{:,.1f}',
})


# ── Main ──────────────────────────────────────────────────────────────────────

def show_electrification():
    meta, summary = _load_static()
    st.markdown(_TILE_CSS, unsafe_allow_html=True)

    names = list(meta['scenario_labels'])
    labels = meta['scenario_labels']
    basis_of = meta['scenario_basis']
    subsectors = meta['subsectors']
    G = meta['goal']
    g0 = G['targets'][0]
    gkey = g0['key']
    baseline = meta['baseline_ref']
    colors = {n: FAMILY_COLORS[FAMILY.index(n.split('__')[0])] for n in names}
    is_bau = lambda n: basis_of[n] == 'net'

    # ── The goal ──
    with st.container(border=True):
        st.markdown(f"#### The goal: electrify {pct(G['goal_share'], 0)} of global final energy")
        scale = 1.0   # the bar covers 0-100% of final energy demand
        now_w, goal_w = G['share'] / scale * 100, G['goal_share'] / scale * 100
        st.markdown(
            '<div class="el-goalbar">'
            '<div class="el-goalbar-track">'
            f'<div class="el-goalbar-now" style="width:{now_w:.2f}%"></div>'
            f'<div class="el-goalbar-gap" style="left:{now_w:.2f}%;width:{goal_w - now_w:.2f}%">{fmt(g0["needed_ej"], 1)} EJ to electrify</div>'
            f'<div class="el-goalbar-goal" style="left:{goal_w:.2f}%"></div>'
            '</div>'
            '<div class="el-goalbar-labels">'
            f'<span style="left:{now_w:.2f}%;transform:translateX(-100%)">Electricity today · {pct(G["share"])}</span>'
            f'<span style="left:{goal_w:.2f}%;transform:translateX(-100%)">Goal · {pct(G["goal_share"], 0)}</span>'
            '<span style="right:0">100% of final energy demand</span>'
            '</div></div>', unsafe_allow_html=True)
        _tiles([
            ('Global energy demand', f"{fmt(g0['demand_ej'], 1)} EJ", f"{G['base_year']} final consumption"),
            ('Electricity today', f"{fmt(g0['electricity_ej'], 1)} EJ", f"{pct(G['share'])} of demand"),
            (f"Goal: {pct(G['goal_share'], 0)} of demand", f"{fmt(g0['goal_ej'], 1)} EJ", f"{pct(G['goal_share'], 0)} electrified"),
            ('Gap to the goal', f"{fmt(g0['needed_ej'], 1)} EJ", f"{fmt((G['goal_share'] - G['share']) * 100, 1)} percentage points of demand", None, True),
        ])
        st.caption(f"*Source: {G['source']}.*")

    st.markdown('')
    # ── Controls ──
    rate_keys = list(meta['rate_labels'])
    cc1, cc2 = st.columns([1, 2])
    with cc1:
        rate = st.radio('Discount rate', rate_keys, index=rate_keys.index(meta['default_rate']),
                        format_func=lambda k: meta['rate_labels'][k], key='el_rate',
                        help='Costs are calculated at this rate; the reductions do not depend on it, but scenarios '
                             'that pick or rank by cost can pick differently.')
    with cc2:
        country = st.selectbox(
            'Country', [COUNTRY_ALL] + sorted(meta['countries']), key='el_country',
            help='Restrict the analysis to one country: each scenario keeps its global strategy picks and asset order, '
                 'limited to the assets in that country.')

    # The scenario picker is the main control of the page, so it gets its own highlighted panel. Its outline is a soft
    # teal until a scenario is chosen, then that scenario's chart colour.
    pick_color = colors.get(st.session_state.get('el_scen'), '#1E7F8C')
    st.markdown(
        f"<style>.st-key-el_pick {{ border: 1.5px solid {pick_color}; border-radius: 10px; padding: 14px 18px 10px; "
        f"background: color-mix(in srgb, {pick_color} 5%, transparent); }}"
        f".st-key-el_pick [data-baseweb='select'] > div {{ min-height: 48px; font-size: 1.05rem; "
        f"border: 1.5px solid {pick_color}; }}</style>", unsafe_allow_html=True)
    with st.container(key='el_pick'):
        st.markdown('<div style="font-size:1.15rem;font-weight:700;margin-bottom:2px">Select a scenario to explore</div>',
                    unsafe_allow_html=True)
        st.caption('Pick one of the scenarios to see what it selects and how much it reduces. '
                   'The tables and chart below compare all of them.')
        scen = st.selectbox(
            'Scenario', [None] + names, key='el_scen', label_visibility='collapsed',
            format_func=lambda n: 'Click here to select a scenario…' if n is None else
            f"{labels[n]}{'  (baseline)' if n == baseline else ''}",
        )
    st.caption(
        '**Clean Grid** (solid line): the reduction at the asset itself, without the emissions of the electricity it '
        "adds to the grid. **BAU Grid** (dashed line): the reduction after the emissions that electricity causes on "
        "today's grid, so lower, and negative for some strategies; assets with no positive BAU reduction cannot be picked."
    )

    if country != COUNTRY_ALL:
        _country_view(meta, summary, rate, country, scen, names, labels, colors, is_bau)
        return

    S = summary[rate]
    scen_data = S['scenarios']
    totals = S['totals']
    cost_axis = S['cost_axis']
    rate_label = meta['rate_labels'][rate]
    k_ej = totals['tj_all'] / 1e6   # EJ per unit of "share of energy"
    picked = scen is not None
    cur = scen_data[scen] if picked else None

    def tag(n):
        return ' <span class="el-tag">baseline</span>' if n == baseline else ''

    # ── What is in scope ──
    with st.container(border=True):
        st.markdown(f'##### In scope: {SECTORS_TEXT}')
        st.caption('This analysis covers three sectors: iron & steel, buildings (residential and non-residential) and road '
                   'transportation. Other sectors are not evaluated.')
        _tiles([
            ('Assets with an electrification strategy', f"{fmt(totals['assets'])} <span class='of'>of {fmt(totals['assets_all'])}</span>"),
            ('Strategies (electrification)', f"{fmt(totals['strategies'])} <span class='of'>of {fmt(totals['strategies_all'])}</span>"),
            ('Energy of those assets (EJ)', f"{fmt(totals['tj'] / 1e6, 1)} <span class='of'>of {ej(totals['tj_all'])}</span>"),
            ('Emissions of those assets (Gt)', f"{fmt(totals['emissions'] / 1e9, 2)} <span class='of'>of {gt(totals['emissions_all'])}</span>"),
        ])

    # ── Scenario comparison tables ──
    base_s = scen_data[baseline]

    def vs_base(s):
        B = base_s
        cpt = lambda x: sum_cost(x['strategies']) / x['red'] if x['red'] else float('nan')
        red = (s['red'] / B['red']) if B['red'] > 0 else None
        cost = (cpt(s) / cpt(B)) if (B['red'] > 0 and s['red'] > 0 and sum_cost(B['strategies']) > 0) else None
        return red, cost


    def pctv(x):
        return float('nan') if x is None else x * 100

    with st.container(border=True):
        st.markdown(f'##### All scenarios · costs at the {rate_label}')
        st.caption(f"Baseline = {labels[baseline]}. Electricity share is after taking all of the scenario's assets "
                   f"(goal {pct(g0['goal_ej'] / g0['demand_ej'], 0)}).")
        rows = []
        for n in names:
            s = scen_data[n]
            vr, vc = vs_base(s)
            c = sum_cost(s['strategies'])
            rows.append({
                'Scenario': labels[n] + (' (baseline)' if n == baseline else ''), 'Assets': s['assets'],
                'Countries': s['n_countries'], 'Strategies': len(s['strategies']),
                'Fuel replaced (EJ)': s['end_tjf'] / 1e6, 'Electricity added (EJ)': s['end_tje'] / 1e6,
                'Electricity share (%)': share_after(s['end_tjf'], s['end_tje'], g0) * 100,
                'Emissions reduced (GtCO₂e)': s['red'] / 1e9, '% of emissions': s['end_y'] * 100,
                'Total cost ($B)': c / 1e9, 'Cost per tCO₂e/yr ($)': (c / s['red']) if s['red'] > 0 else float('nan'),
                '% at negative cost': (s['neg'] / s['red'] * 100) if s['red'] > 0 else float('nan'),
                'Reduction % of baseline': pctv(vr), 'Cost per tCO₂e % of baseline': pctv(vc),
            })
        _scenario_table(pd.DataFrame(rows), names, colors, is_bau, _GLOBAL_FMTS, scen)
        _cost_note()

    with st.container(border=True):
        st.markdown(f"##### All scenarios · up to the goal: {g0['label']} · costs at the {rate_label}")
        st.caption(
            f"Only the first assets of each scenario, in its order, until electricity reaches "
            f"{pct(g0['goal_ej'] / g0['demand_ej'], 0)} of final energy demand (the asset that crosses it is included). "
            "A scenario that never reaches the goal shows all of its assets and is flagged. "
            f"Baseline = {labels[baseline]}."
        )
        Bs = base_s
        B = Bs['targets'][gkey]
        Bred = B['red'] if B['reached'] else Bs['red']
        Bcost = sum_cost(B['sectors']) if B['reached'] else sum_cost(Bs['strategies'])
        rows = []
        for n in names:
            s0 = scen_data[n]
            p = s0['targets'][gkey]
            miss = not p['reached']
            A = s0['assets'] if miss else p['assets']
            Cn = s0['n_countries'] if miss else p['n_countries']
            Sn = len(s0['strategies']) if miss else len(p['strategies'])
            TJF = s0['end_tjf'] if miss else p['tjf']
            TJE = s0['end_tje'] if miss else p['tje']
            R = s0['red'] if miss else p['red']
            NEG = s0['neg'] if miss else p['neg']
            cost = sum_cost(s0['strategies']) if miss else sum_cost(p['sectors'])
            vs_red = (R / Bred) if Bred > 0 else None
            vs_cost = ((cost / R) / (Bcost / Bred)) if (R > 0 and Bcost > 0 and Bred > 0) else None
            rows.append({
                'Scenario': labels[n] + (' (baseline)' if n == baseline else '') +
                (f" — goal not reached ({pct(share_after(TJF, TJE, g0))})" if miss else ''),
                'Assets': A, 'Countries': Cn, 'Strategies': Sn,
                'Fuel replaced (EJ)': TJF / 1e6, 'Electricity added (EJ)': TJE / 1e6,
                'Electricity share (%)': share_after(TJF, TJE, g0) * 100,
                'Emissions reduced (GtCO₂e)': R / 1e9, '% of emissions': R / totals['emissions_all'] * 100,
                'Total cost ($B)': cost / 1e9, 'Cost per tCO₂e/yr ($)': (cost / R) if R > 0 else float('nan'),
                '% at negative cost': (NEG / R * 100) if R > 0 else float('nan'),
                'Reduction % of baseline': pctv(vs_red), 'Cost per tCO₂e % of baseline': pctv(vs_cost),
            })
        _scenario_table(pd.DataFrame(rows), names, colors, is_bau, _GLOBAL_FMTS, scen)
        _cost_note()

    # ── Chart ──
    st.markdown('---')
    chart_mode = st.radio('Chart', [c[0] for c in CHARTS], format_func=lambda k: dict(CHARTS)[k], horizontal=True,
                          key='el_chart')
    fig, note = _build_chart(chart_mode, names, labels, colors, is_bau, scen_data, totals, cost_axis, k_ej,
                             G, picked, scen, g0)
    st.plotly_chart(fig, use_container_width=True, key='el_chart_fig')
    if note:
        st.caption(note)

    # ── Selected scenario ──
    if not picked:
        st.info('Select a scenario above to see what it picks and how much it reduces.')
        return

    basis = basis_of[scen]
    accent = colors[scen]
    s = cur
    st.markdown('---')
    st.markdown(f'<div class="el-h" style="--c:{accent}">{labels[scen]}{" (baseline)" if scen == baseline else ""}</div>',
                unsafe_allow_html=True)
    st.caption(f"{SECTORS_TEXT} · reductions = {BASIS_LABEL[basis]} · costs at the {rate_label}")
    st.markdown(f"_{meta['scenario_rules'][scen]}_")

    if not s['assets']:
        st.warning('This scenario selects no assets: none of its strategies meet the rule.')
        return

    vr, vc = vs_base(s)
    st.markdown(
        f"A scenario pathway reduces **{gtmt(s['red'])}** (**{pct(vr, 0)}** of the baseline reduction) at "
        f"**{pct(vc, 0)}** of the baseline's cost abatement (cost per tCO₂e per year)."
    )
    cost_s, cp_s = sum_cost(s['strategies']), sum_cp(s['strategies'])
    _tiles([
        ('Assets', fmt(s['assets']), f"<b>{pct(s['assets'] / totals['assets'])}</b> of {fmt(totals['assets'])} with an electrification strategy"),
        ('Countries', fmt(s['n_countries']), f"<b>{pct(s['n_countries'] / totals['countries'])}</b> of {fmt(totals['countries'])}"),
        ('Strategies', fmt(len(s['strategies'])), f"<b>{pct(len(s['strategies']) / totals['strategies'])}</b> of {fmt(totals['strategies'])}"),
        ('Fuel replaced', ej(s['end_tjf']), f"<b>{pct(s['end_tjf'] / totals['tj_all'])}</b> of {ej(totals['tj_all'])} fuel energy of these sectors"),
        ('Electricity added', ej(s['end_tje']), f"<b>{pct(share_after(s['end_tjf'], s['end_tje'], g0))}</b> of global demand would be electricity if all assets were taken (goal 35%)"),
        ('Emissions reduced', gt(s['red']), f"<b>{pct(s['end_y'])}</b> of {gt(totals['emissions_all'])} total emissions",
         f"{pct(s['neg'] / s['red'])} of the reduction saves money (negative cost)", True),
        _total_cost_tile(cost_s, cp_s),
        _per_t_tile(cost_s, s['red']),
    ], accent=accent)

    order = meta['scenario_order'][scen]
    scope_name = 'the three sectors'

    # ── Detail views ──
    view = st.radio('Breakdown', [v[0] for v in VIEWS], format_func=lambda k: dict(VIEWS)[k], horizontal=True,
                    key='el_view')
    vk = f'{rate}_{scen}_{view}'
    _cost_note()

    def seg_cards(caption, st_set):
        n = st_set['assets'] if 'assets' in st_set else st_set['n']
        tjf = sum_key(st_set['sectors'], 'tjf')
        tje = sum_key(st_set['sectors'], 'tje')
        red = st_set['red']
        st.markdown(f'_{caption}_')
        extra = (f"{pct(red / s['red'])} of this scenario's reductions" if s['red'] > 0 else '') + \
                (f"{' · ' if s['red'] > 0 else ''}{pct(st_set['neg'] / red)} saves money" if red > 0 else '')
        c = sum_cost(st_set['sectors'])
        cp = sum_cp(st_set['sectors'])
        _tiles([
            ('Assets', fmt(n), f"<b>{pct(n / s['assets'])}</b> of {fmt(s['assets'])} assets selected"),
            ('Countries', fmt(st_set['n_countries']), f"<b>{pct(st_set['n_countries'] / s['n_countries'])}</b> of {fmt(s['n_countries'])} in this scenario"),
            ('Fuel replaced', ej(tjf), f"<b>{pct(tjf / totals['tj_all'])}</b> of {ej(totals['tj_all'])}",
             f"{pct(tjf / s['end_tjf'])} of this scenario's fuel replaced"),
            ('Electricity added', ej(tje), f"<b>{pct(tje / s['end_tje'])}</b> of {ej(s['end_tje'])} added by all of the scenario's assets"),
            ('Emissions reduced', gtmt(red), f"<b>{pct(red / totals['emissions_all'])}</b> of {gt(totals['emissions_all'])} total emissions", extra),
            _total_cost_tile(c, cp),
            _per_t_tile(c, red),
        ], accent=accent)

    if view == 'strategy':
        st.markdown(f"The {fmt(len(s['strategies']))} strategies this scenario picks, with the number of assets that take each one.")
        rows = s['strategies']
        df = _breakdown_df(rows, 'Strategy', lambda r: r['name'], activity_unit=True, total=False)
        df.insert(1, 'Sector', [SUB_LABEL[r['subsector']] for r in rows])
        df['Activity'] = [f"{big_fmt(r['act'])} {ACT_UNIT[r['subsector']]}" if _ok(r.get('act')) else '' for r in rows]
        df['Implementation time (years)'] = [
            ('–' if r.get('impl') is None else fmt(r['impl'], 1) + ('' if r['impl_min'] == r['impl_max'] else f" ({fmt(r['impl_min'])}–{fmt(r['impl_max'])})"))
            for r in rows]
        cfg = _cfg_breakdown('Strategy', extra_cols={'Activity': _C.TextColumn('Activity (sector units)')})
        _show(df, cfg, height=min(700, 60 + 35 * len(df)))

    elif view == 'sector':
        st.markdown(f'Everything this scenario picks in {scope_name}, split by sector.')
        _sector_block(s['sectors'], True)

    elif view == 'continent':
        st.markdown("Everything this scenario picks, by continent, by Global North / South (the UN's developed-country "
                    "grouping) and by Annex 1 / Non-Annex 1 (the UNFCCC grouping).")
        _share_blocks(s, vk)

    elif view == 'country':
        st.markdown("The 15 countries with the largest reductions in this scenario. Each bar splits a country's "
                    "reductions by sector; bars show positive reductions only.")
        _countries_table(s['countries'], s['assets'], s['red'], True, None, subsectors, vk, title='Top 15 countries')

    elif view == 'top':
        tp = s['top']
        seg_cards(f"Assets are taken {order}: the first {fmt(tp['n'])} ({scope_name}).", tp)
        _sector_block(tp['sectors'], True, with_cost=False)
        _share_blocks(tp, vk)
        _countries_table(tp['countries'], tp['n'], tp['red'], True, None, subsectors, vk)
        _asset_table(_assets(rate, scen, basis, tp['n']), 'Assets', vk)

    elif view == 'share':
        p = s['top_share']
        if not p['assets']:
            st.info('This scenario has no positive reductions in this scope.')
        else:
            seg_cards(
                "The assets with the largest reductions in this scenario, largest first (whatever order the scenario "
                f"uses), until they add up to 10% of its total reductions ({mt(p['pos_total'])} MtCO₂e per year) in {scope_name}.", p)
            _sector_block(p['sectors'], True)
            _share_blocks(p, vk)
            _countries_table(p['countries'], p['assets'], p['red'], True, None, subsectors, vk)
            rs = pd.DataFrame(s['rows_share'])
            if not rs.empty:
                rs.insert(0, 'rank', range(1, len(rs) + 1))
                rs = rs.rename(columns={'red_selected': 'red'})
                rs['asset_name'] = rs['asset_name'].fillna('')
                _asset_table(rs, f"All {fmt(len(rs))} assets", vk)

    else:  # goal
        p = s['targets'][gkey]
        if not p['reached']:
            st.error(
                f"This scenario never reaches the goal: with all of its assets it replaces {ej(s['end_tjf'])} of fuel "
                f"with {ej(s['end_tje'])} of electricity, which lifts electricity to "
                f"{pct(share_after(s['end_tjf'], s['end_tje'], g0))} of final energy demand, short of the "
                f"{pct(G['goal_share'], 0)} goal ({g0['label']}). All of its assets are shown below."
            )
            q = dict(s)
            seg_cards(f"All of the scenario's assets, {order} (the goal is not reached). The list shows the first 100.", q)
            _sector_block(s['sectors'], True)
            _share_blocks(s, vk)
            _countries_table(s['countries'], s['assets'], s['red'], True, None, subsectors, vk)
            _asset_table(_assets(rate, scen, basis, min(100, s['assets'])), f"Top {fmt(min(100, s['assets']))} assets", vk)
        else:
            seg_cards(
                f"{g0['label']}: assets are taken {order} until electricity reaches {pct(G['goal_share'], 0)} of final "
                f"energy demand (from today's {pct(G['share'])}), including the asset that crosses it. The list shows the first 100.", p)
            _sector_block(p['sectors'], True)
            _share_blocks(p, vk)
            _countries_table(p['countries'], p['assets'], p['red'], True, None, subsectors, vk)
            _asset_table(_assets(rate, scen, basis, min(100, p['assets'])), f"Top {fmt(min(100, p['assets']))} assets", vk)

    # ── Downloads ──
    st.markdown('---')
    _downloads(meta, scen_data, scen, rate, basis, chart_mode, totals, g0, labels, rate_label, order)


# ── Chart ─────────────────────────────────────────────────────────────────────

def _nice_step(rng, steps):
    for t in steps:
        if rng / t <= 8:
            return t
    return steps[-1]


def _build_chart(mode, names, labels, colors, is_bau, scen_data, totals, cost_axis, k_ej, G, picked, scen, g0):
    fig = go.Figure()
    note = None
    tgts = G['targets']
    none = not picked
    order = sorted(names, key=lambda n: (n == scen))   # selected line drawn last

    def line_kw(n):
        on = n == scen
        return dict(
            line=dict(color=colors[n], width=2.5 if none else (4.5 if on else 1.75), dash='dash' if is_bau(n) else 'solid'),
            opacity=1 if (none or on) else 0.3,
        )

    if mode == 'energy':
        for n in order:
            s = scen_data[n]
            fig.add_scatter(x=[x * k_ej for x in s['x']], y=s['y'], mode='lines', name=labels[n], **line_kw(n),
                            hovertemplate='%{x:,.1f} EJ electrified: %{y:.1%}<extra>' + labels[n] + '</extra>')
        for i, g in enumerate(tgts):
            fig.add_vline(x=g['needed_ej'], line_dash='dash' if i == 0 else 'dot', line_color='gray', line_width=1.8,
                          annotation_text=f"{g['label']}: {fmt(g['needed_ej'], 1)} EJ", annotation_position='top left')
        _base_layout(fig, height=760)
        fig.update_xaxes(title='Goal energy (EJ)')
        fig.update_yaxes(title='Share of total emissions reduced', tickformat='.0%')
    elif mode == 'assets':
        miss = []
        for n in order:
            p = scen_data[n]['targets'][g0['key']]
            if not p['reached']:
                miss.append(labels[n])
            cv = p.get('curve')
            if not cv:
                continue
            fig.add_scatter(x=cv['x'], y=cv['y'], mode='lines', name=labels[n], **line_kw(n),
                            hovertemplate='%{x:.0%} of the assets: %{y:,.2f} GtCO₂e<extra>' + labels[n] + '</extra>')
        _base_layout(fig, height=760)
        fig.update_xaxes(title=f"Share of the assets needed to reach the goal ({g0['label']}), each scenario's own assets = 100%",
                         tickformat='.0%', range=[0, 1])
        fig.update_yaxes(title='Emissions reduced (GtCO₂e per year, cumulative)')
        note = ("Each line covers only the assets a scenario needs to reach the goal, in its order, so every line ends at "
                "100% of its own assets and at the emissions those assets reduce."
                + (f" {', '.join(miss)} never reaches the goal: its line covers all of its assets." if miss else ''))
    else:  # cost
        lo, hi, n_pts = cost_axis['lo'], cost_axis['hi'], cost_axis['n']
        xs = [lo + (hi - lo) * j / n_pts for j in range(n_pts + 1)]
        pad = (hi - lo) * 0.1
        for n in order:
            cc = scen_data[n]['cost_curve']
            fig.add_scatter(x=xs, y=[v / 1e9 for v in cc['y']], mode='lines', name=labels[n], **line_kw(n),
                            hovertemplate='Cost abatement ≤ $%{x:,.0f}: %{y:,.2f} GtCO₂e<extra>' + labels[n] + '</extra>')
        fig.add_vrect(x0=hi, x1=hi + pad, fillcolor='gray', opacity=0.15, line_width=0)
        fig.add_vline(x=hi, line_dash='dash', line_color='gray')
        fig.add_vline(x=0, line_color='gray', line_width=1.2,
                      annotation_text='net savings to the left', annotation_position='top right')
        s = scen_data[scen]['cost_curve'] if picked else None
        hi_txt = f"Cut-off ${fmt(hi)}" + (f"<br>{fmt(s['beyond_assets'])} assets<br>{gtmt(s['beyond'])}<br>cost more" if s else '')
        fig.add_annotation(x=hi + pad / 2, y=1, yref='paper', text=hi_txt, showarrow=False, yanchor='top',
                           font=dict(size=12))
        below = s['below_assets'] if s else max(scen_data[n]['cost_curve']['below_assets'] for n in names)
        if below > 0:
            fig.add_vrect(x0=lo - pad, x1=lo, fillcolor='gray', opacity=0.15, line_width=0)
            fig.add_vline(x=lo, line_dash='dash', line_color='gray')
            lo_txt = f"Cut-off {money(lo)}" + (f"<br>{fmt(s['below_assets'])} assets<br>{gtmt(s['below'])}<br>cost less" if s else '')
            fig.add_annotation(x=lo - pad / 2, y=1, yref='paper', text=lo_txt, showarrow=False, yanchor='top',
                               font=dict(size=12))
        _base_layout(fig, height=760)
        fig.update_xaxes(title='Cost abatement of the picked strategy ($ per tCO₂e per year; Clean Grid or BAU Grid cost '
                               'abatement, as the scenario)', range=[lo - pad, hi + pad], tickprefix='$')
        fig.update_yaxes(title='Emissions reduced (GtCO₂e per year, cumulative)')
        note = ('Each point is the cumulative reductions of the picked assets whose strategy costs at most that much. '
                'Costs beyond the dashed cut-off lines are not drawn'
                + (f"; {fmt(s['missing_assets'])} assets ({gtmt(s['missing'])}) have no cost abatement and are left out."
                   if s else '. Select a scenario to see how many assets are beyond the cut-off.'))
    fig.update_layout(legend=dict(orientation='h', yanchor='top', y=-0.14, x=0), hovermode='closest', margin=dict(l=60, r=20, t=30, b=170))
    return fig, note


# ── Downloads ─────────────────────────────────────────────────────────────────

def _chart_csv(rate, scen, basis, mode, labels, totals, g0, scen_data):
    """The assets behind the selected chart, in the order the chart adds them, with running totals."""
    df = _assets(rate, scen, basis).copy()
    p = scen_data[scen]['targets'][g0['key']]
    grid = BASIS_LABEL[basis]
    df['scenario'] = labels[scen]
    df['grid'] = grid
    if mode == 'assets':
        df = df.head(p['assets'] if p['reached'] else len(df))
    if mode == 'cost':   # cost chart adds assets in order of cost abatement; assets without a positive reduction come last
        df['_ca'] = [(c / r) if (pd.notna(c) and r > 0) else float('inf') for c, r in zip(df['cost'], df['red'])]
        df = df.sort_values(['_ca', 'rank'], kind='stable').drop(columns='_ca')
    df['order'] = range(1, len(df) + 1)
    cum_tj, cum_red = df['tj'].cumsum(), df['red'].cumsum()
    out = pd.DataFrame({
        'scenario': df['scenario'], 'grid': df['grid'], 'order': df['order'], 'asset_id': df['asset_id'],
        'asset_name': df['asset_name'], 'country': df['country'], 'sector': df['subsector'], 'strategy': df['strategy'],
        'fuel_replaced_EJ': df['tjf'] / 1e6, 'electricity_added_EJ': df['tje'] / 1e6,
        'reduction_selected_grid_tCO2e_per_year': df['red'], 'reduction_clean_grid_tCO2e_per_year': df['red_at'],
        'reduction_bau_grid_tCO2e_per_year': df['red_nt'], 'net_present_value_usd': df['cost'],
        'cost_abatement_usd_per_tCO2e_per_year': [(c / r) if (pd.notna(c) and r > 0) else None for c, r in zip(df['cost'], df['red'])],
    })
    if mode == 'energy':
        out['cumulative_goal_energy_EJ'] = cum_tj / 1e6
        out['cumulative_goal_energy_share_of_four_sector_fuel_energy'] = cum_tj / totals['tj_all']
        out['cumulative_emissions_reduced_GtCO2e'] = cum_red / 1e9
        out['cumulative_share_of_emissions'] = cum_red / totals['emissions_all']
    elif mode == 'assets':
        out['goal_reached'] = 'yes' if p['reached'] else 'no (all assets of the scenario)'
        out['share_of_goal_set_assets'] = df['order'] / len(df)
        out['cumulative_emissions_reduced_GtCO2e'] = cum_red / 1e9
    else:
        out['cumulative_emissions_reduced_GtCO2e_at_or_below_this_cost'] = cum_red / 1e9
    return out.to_csv(index=False).encode('utf-8')


def _uni_df(kind, rows, first_label):
    """One breakdown sheet for the Excel workbook; both grids shown."""
    R_at, R_nt = sum_key(rows, 'red_at'), sum_key(rows, 'red_nt')
    A = sum_key(rows, 'assets')
    recs = []
    for r in rows:
        c, cp = r.get('cost'), r.get('cp') or 0
        rec = {
            first_label: SUB_LABEL.get(r.get('subsector'), r.get('name')) if kind == 'Sector' else r.get('name'),
            'Assets': r['assets'], '% of assets': r['assets'] / A if A else None,
            'Reductions, Clean Grid (MtCO2e/yr)': r['red_at'] / 1e6, '% of reductions (Clean Grid)': r['red_at'] / R_at if R_at else None,
            'Reductions, BAU Grid (MtCO2e/yr)': r['red_nt'] / 1e6, '% of reductions (BAU Grid)': r['red_nt'] / R_nt if R_nt else None,
            'Fuel replaced (EJ)': r['tjf'] / 1e6, 'Electricity added (EJ)': r['tje'] / 1e6,
            'ERS net present value ($)': None if c is None else c - cp, 'Clean power cost ($)': cp, 'Total cost incl. clean power ($)': c,
            'Cost per tCO2e/yr, Clean Grid ($)': (c / r['red_at']) if (c is not None and r['red_at'] > 0) else None,
            'Cost per tCO2e/yr, BAU Grid ($)': (c / r['red_nt']) if (c is not None and r['red_nt'] > 0) else None,
            '% at negative cost (Clean Grid)': r['neg_at'] / r['red_at'] if r['red_at'] > 0 else None,
            '% at negative cost (BAU Grid)': r['neg_nt'] / r['red_nt'] if r['red_nt'] > 0 else None,
        }
        if kind == 'Strategy':
            rec['Sector'] = SUB_LABEL[r['subsector']]
            rec['Implementation time, average (years)'] = r.get('impl')
        if kind == 'Country':
            rec['Continent'], rec['Global North / South'], rec['Annex 1 / Non-Annex 1'] = r.get('continent'), r.get('region'), r.get('annex')
        recs.append(rec)
    return pd.DataFrame(recs)


def _build_workbook(kind, rate, scen, basis, meta, scen_data, totals, g0, labels, rate_label, order):
    s = scen_data[scen]
    p = s['targets'][g0['key']]
    all_assets = _assets(rate, scen, basis)
    st_set, assets_df = s, all_assets
    title = f"{labels[scen]} · full scenario"
    if kind == 'goal':
        if p['reached']:
            st_set, assets_df = p, all_assets.head(p['assets'])
        title = f"{labels[scen]} · 35x35 data" + ('' if p['reached'] else ' (goal not reached: all assets)')
    elif kind == 'top':
        st_set, assets_df, title = s['top'], all_assets.head(s['top']['n']), f"{labels[scen]} · top {fmt(s['top']['n'])} assets"
    elif kind == 'share':
        st_set, title = s['top_share'], f"{labels[scen]} · top 10% of reductions"
        assets_df = pd.DataFrame(s['rows_share'])
        assets_df.insert(0, 'rank', range(1, len(assets_df) + 1))
        assets_df = assets_df.rename(columns={'red_selected': 'red'})
    countries_all = st_set.get('countries_all') or s['countries_all']

    sec = st_set['sectors']
    summary_rows = [
        ('Scenario', labels[scen]), ('Selection', title), ('Rule', meta['scenario_rules'][scen]),
        ('Reductions defined as', BASIS_LABEL[basis]), ('Costs at the', rate_label), ('Assets are taken', order),
        ('Assets', sum_key(sec, 'assets')), ('Fuel replaced (EJ)', sum_key(sec, 'tjf') / 1e6),
        ('Electricity added (EJ)', sum_key(sec, 'tje') / 1e6),
        ('Emissions reduced, Clean Grid (MtCO2e/yr)', sum_key(sec, 'red_at') / 1e6),
        ('Emissions reduced, BAU Grid (MtCO2e/yr)', sum_key(sec, 'red_nt') / 1e6),
        ('Total cost incl. clean power ($)', sum_cost(sec)), ('Clean power cost ($)', sum_cp(sec)),
    ]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as xw:
        pd.DataFrame(summary_rows, columns=['Item', 'Value']).to_excel(xw, sheet_name='Summary', index=False)
        sheets = [
            ('By strategy', _uni_df('Strategy', st_set['strategies'], 'Strategy')),
            ('By sector', _uni_df('Sector', st_set['sectors'], 'Sector')),
            ('By continent', _uni_df('Continent', st_set['continents'], 'Continent')),
            ('By Global North-South', _uni_df('Region', st_set['regions'], 'Global North / South')),
            ('By Annex 1', _uni_df('Annex', st_set['annexes'], 'Annex 1 / Non-Annex 1')),
            ('By country', _uni_df('Country', countries_all, 'Country')),
        ]
        for nm, d in sheets:
            d.to_excel(xw, sheet_name=nm, index=False)
            xw.sheets[nm].freeze_panes(1, 0)
        a = assets_df.copy()
        gd, ge = g0['demand_ej'], g0['electricity_ej']
        d_run = gd - ((a['tjf'] - a['tje']) / 1e6).cumsum()
        e_run = ge + (a['tje'] / 1e6).cumsum()
        out = pd.DataFrame({
            '#': range(1, len(a) + 1), 'Asset ID': a['asset_id'], 'Asset': a['asset_name'], 'Country': a['country'].astype(str),
            'Sector': [SUB_LABEL[x] for x in a['subsector']], 'Strategy': a['strategy'].astype(str),
            'Reductions, Clean Grid (tCO2e/yr)': a['red_at'], 'Reductions, BAU Grid (tCO2e/yr)': a['red_nt'],
            'Fuel replaced (TJ)': a['tjf'], 'Electricity added (TJ)': a['tje'], 'Activity': a['activity'],
            'ERS net present value ($)': a['cost'] - a['cp'], 'Clean power cost ($)': a['cp'], 'Total cost incl. clean power ($)': a['cost'],
            'Total energy demand after this asset (EJ)': d_run.values, 'Electricity after this asset (EJ)': e_run.values,
            'Electricity share after this asset (35x35 target)': (e_run / d_run).values,
        })
        out.to_excel(xw, sheet_name='Assets', index=False)
        xw.sheets['Assets'].freeze_panes(1, 0)
        for nm in xw.sheets:
            xw.sheets[nm].set_column(0, 25, 18)
    return buf.getvalue()


def _downloads(meta, scen_data, scen, rate, basis, chart_mode, totals, g0, labels, rate_label, order):
    st.markdown('#### Downloads')
    c1, c2 = st.columns(2)
    with c1:
        kind = st.selectbox('Excel workbook', ['full', 'goal', 'top', 'share'], key='el_xl_kind',
                            format_func={'full': 'Full scenario', 'goal': '35x35 data', 'top': 'Top 1,000 assets',
                                         'share': 'Top 10% of reductions'}.get)
        key = f'el_xl_{rate}_{scen}_{kind}'
        if st.button('Prepare Excel workbook', key=f'btn_{key}'):
            with st.spinner('Building the workbook…'):
                st.session_state[key] = _build_workbook(kind, rate, scen, basis, meta, scen_data, totals, g0, labels,
                                                        rate_label, order)
        if key in st.session_state:
            st.download_button('Download Excel', st.session_state[key], file_name=f"{labels[scen]} ({rate_label}) - {kind}.xlsx".replace('/', '-'),
                               mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', key=f'dl_{key}')
    with c2:
        st.markdown(f"**Assets behind the selected chart** ({dict(CHARTS)[chart_mode]})")
        key = f'el_csv_{rate}_{scen}_{chart_mode}'
        if st.button('Prepare chart CSV', key=f'btn_{key}'):
            with st.spinner('Preparing the file…'):
                st.session_state[key] = _chart_csv(rate, scen, basis, chart_mode, labels, totals, g0, scen_data)
        if key in st.session_state:
            st.download_button('Download CSV', st.session_state[key], file_name=f'chart_assets_{chart_mode}_all_{rate}_{scen}.csv',
                               mime='text/csv', key=f'dl_{key}')


# ── Country view ──────────────────────────────────────────────────────────────
# A country scope is the GLOBAL scenario restricted to the assets in that country: every asset keeps the strategy the
# scenario picked for it and the scenario's own ordering. Everything is re-aggregated from the asset parquet files
# (the aggregation was checked against the HTML tool's global numbers for all rate x scenario combinations).
# Not shown at country level because they are global quantities: the 35x35 goal / IEA energy figures and
# "share of total emissions" (the data has no per-country emissions totals).

_ASSET_COLS = ['scenario', 'rank', 'asset_id', 'asset_name', 'subsector', 'strategy', 'red_nt', 'red_at', 'tj', 'cost',
               'activity', 'cp', 'tjf', 'tje']


@st.cache_data(ttl=3600, show_spinner="Loading country…")
def _country_data(rate, country, basis_items):
    basis_of = dict(basis_items)
    safe = country.replace("'", "''")
    sql = f"""
        SELECT a.scenario AS scenario, a."rank" AS rank, p.asset_id, n.asset_name, p.subsector, p.strategy,
               p.red_nt_x10 / 10.0 AS red_nt, p.red_at_x10 / 10.0 AS red_at,
               (0.65 * p.tje_x100 + 0.35 * p.tjf_x100) / 100.0 AS tj,
               a.cost AS cost, p.activity AS activity, a.cp AS cp,
               p.tjf_x100 / 100.0 AS tjf, p.tje_x100 / 100.0 AS tje
        FROM '{CONFIG['electrification_assets_path']}' a
        JOIN '{CONFIG['electrification_picks_path']}' p USING (pick_id)
        LEFT JOIN '{CONFIG['electrification_asset_names_path']}' n ON n.asset_id = p.asset_id
        WHERE a.rate = '{rate}' AND p.country = '{safe}'
    """
    df = _cached_df(sql)
    out = {}
    for scen in basis_of:
        g = df[df['scenario'] == scen].sort_values('rank').reset_index(drop=True) if len(df) else \
            pd.DataFrame({c: [] for c in _ASSET_COLS})
        for c in ('cost', 'cp', 'activity', 'red_nt', 'red_at', 'tj', 'tjf', 'tje'):
            g[c] = pd.to_numeric(g[c], errors='coerce').astype('float64')   # plain floats: nullable ints make masks ambiguous
        g['asset_name'] = g['asset_name'].fillna('')
        g['red'] = g['red_nt'] if basis_of[scen] == 'net' else g['red_at']
        g['country'] = country
        g['rank'] = np.arange(1, len(g) + 1)   # the scenario's order, re-numbered within the country
        out[scen] = g
    return out


def _grp(g, keys):
    """Per-group sums in the same shape as the HTML tool's strategy / sector rows."""
    if g.empty:
        return []
    neg = g['cost'] < 0
    h = g.assign(neg=np.where(neg, g['red'], 0.0), neg_at=np.where(neg, g['red_at'], 0.0),
                 neg_nt=np.where(neg, g['red_nt'], 0.0))
    agg = h.groupby(keys, sort=False).agg(
        assets=('asset_id', 'size'), red=('red', 'sum'), red_at=('red_at', 'sum'), red_nt=('red_nt', 'sum'),
        neg=('neg', 'sum'), neg_at=('neg_at', 'sum'), neg_nt=('neg_nt', 'sum'), tj=('tj', 'sum'), tjf=('tjf', 'sum'),
        tje=('tje', 'sum'), act=('activity', 'sum'), cost=('cost', 'sum'), cp=('cp', 'sum')).reset_index()
    return agg.sort_values('red', ascending=False).to_dict('records')


def _tot(g):
    neg = g['cost'] < 0
    return dict(assets=len(g), red=float(g['red'].sum()), tjf=float(g['tjf'].sum()), tje=float(g['tje'].sum()),
                tj=float(g['tj'].sum()), cost=float(g['cost'].sum()), cp=float(g['cp'].sum()),
                neg=float(g['red'].where(neg, 0.0).sum()), n_strat=int(g[['subsector', 'strategy']].drop_duplicates().shape[0]))


def _energy_curve(g, max_pts=1500):
    x = np.cumsum(g['tj'].values) / 1e6
    y = np.cumsum(g['red'].values) / 1e6
    if len(x) > max_pts:
        idx = np.unique(np.r_[np.arange(0, len(x), len(x) // max_pts), len(x) - 1])
        x, y = x[idx], y[idx]
    return np.r_[0.0, x], np.r_[0.0, y]


def _cost_curve(g, lo, hi, n):
    """Cumulative reductions (MtCO2e/yr) of the picks whose cost abatement (NPV / reductions) is at most x."""
    xs = lo + (hi - lo) * np.arange(n + 1) / n
    ok = ((g['red'] > 0) & g['cost'].notna()).values
    if not ok.any():
        return xs, np.zeros(n + 1), 0
    ca = (g['cost'].values[ok] / g['red'].values[ok])
    order = np.argsort(ca, kind='stable')
    cs, cum = ca[order], np.cumsum(g['red'].values[ok][order])
    idx = np.searchsorted(cs, xs, side='right')
    y = np.where(idx > 0, cum[np.maximum(idx - 1, 0)], 0.0) / 1e6
    return xs, y, int((~ok).sum())


def _country_view(meta, summary, rate, country, scen, names, labels, colors, is_bau):
    basis_of = meta['scenario_basis']
    baseline = meta['baseline_ref']
    data = _country_data(rate, country, tuple(sorted(basis_of.items())))
    union = pd.concat([g[['asset_id']] for g in data.values()]).drop_duplicates() if data else pd.DataFrame()
    st.markdown(f'### {country}')
    if union.empty:
        st.info(f'No electrification assets found in {country}.')
        return
    st.info(
        f"**Country view.** Each scenario keeps its global strategy picks and asset order, limited to the assets in "
        f"{country}. The 35x35 goal and the share-of-total-emissions figures are global, so they are not shown here; "
        f"comparisons are against the baseline scenario ({labels[baseline]}) in {country}.")

    rate_label = meta['rate_labels'][rate]
    tots = {n: _tot(data[n]) for n in names}
    tb = tots[baseline]
    n_assets = len(union)
    n_strat_all = int(pd.concat([g[['subsector', 'strategy']] for g in data.values()]).drop_duplicates().shape[0])

    with st.container(border=True):
        st.markdown(f'##### In scope: {country}')
        st.caption('This analysis covers iron & steel, buildings (residential and non-residential) and road transportation only.')
        _tiles([
            ('Assets with an electrification strategy', fmt(n_assets)),
            ('Strategies (electrification)', fmt(n_strat_all)),
            ('Sectors', fmt(len({s_ for g in data.values() for s_ in g['subsector']}))),
        ])

    # ── all scenarios in the country ──
    rows = []
    for n in names:
        t = tots[n]
        vr = (t['red'] / tb['red']) if tb['red'] > 0 else None
        cpt = lambda x: (x['cost'] / x['red']) if x['red'] > 0 else None
        vc = (cpt(t) / cpt(tb)) if (cpt(t) is not None and cpt(tb) not in (None, 0) and cpt(tb) > 0) else None
        rows.append({
            'Scenario': labels[n] + (' (baseline)' if n == baseline else ''),
            'Assets': t['assets'], 'Strategies': t['n_strat'],
            'Fuel replaced (EJ)': t['tjf'] / 1e6, 'Electricity added (EJ)': t['tje'] / 1e6,
            'Emissions reduced (MtCO₂e)': t['red'] / 1e6, 'Total cost ($M)': t['cost'] / 1e6,
            'Cost per tCO₂e/yr ($)': (t['cost'] / t['red']) if t['red'] > 0 else float('nan'),
            '% at negative cost': (t['neg'] / t['red'] * 100) if t['red'] > 0 else float('nan'),
            'Reduction % of baseline': float('nan') if vr is None else vr * 100,
            'Cost per tCO₂e % of baseline': float('nan') if vc is None else vc * 100,
        })
    cmp_df = pd.DataFrame(rows)
    with st.container(border=True):
        st.markdown(f'##### All scenarios · {country} · costs at the {rate_label}')
        st.caption(f'Baseline = {labels[baseline]}. Every asset of the scenario in {country} is included.')
        _scenario_table(cmp_df, names, colors, is_bau, _COUNTRY_FMTS, scen)
        _cost_note()

    # ── chart ──
    st.markdown('---')
    mode = st.radio('Chart', ['energy', 'cost'], horizontal=True, key='el_c_chart', format_func=lambda k: {
        'energy': 'Goal energy vs emissions reduced', 'cost': 'Cost abatement vs emissions reduced'}[k])
    ax = summary[rate]['cost_axis']
    fig = go.Figure()
    for n in sorted(names, key=lambda x: x == scen):   # selected line drawn last
        on, none = n == scen, scen is None
        kw = dict(line=dict(color=colors[n], width=2.5 if none else (4.5 if on else 1.75),
                            dash='dash' if is_bau(n) else 'solid'), opacity=1 if (none or on) else 0.3, name=labels[n])
        g = data[n]
        if g.empty:
            continue
        if mode == 'energy':
            x, y = _energy_curve(g)
            fig.add_scatter(x=x, y=y, mode='lines', hovertemplate='%{x:,.2f} EJ electrified: %{y:,.2f} MtCO₂e<extra>' + labels[n] + '</extra>', **kw)
        else:
            x, y, _missing = _cost_curve(g, ax['lo'], ax['hi'], ax['n'])
            fig.add_scatter(x=x, y=y, mode='lines', hovertemplate='Cost abatement ≤ $%{x:,.0f}: %{y:,.2f} MtCO₂e<extra>' + labels[n] + '</extra>', **kw)
    _base_layout(fig, height=760)
    if mode == 'energy':
        fig.update_xaxes(title=f'Goal energy electrified in {country} (EJ, cumulative in the scenario order)')
        fig.update_yaxes(title='Emissions reduced (MtCO₂e per year, cumulative)')
        note = ('Each point adds the next asset in the scenario order. Goal energy = 0.65 × electricity added + 0.35 × fuel replaced.')
    else:
        fig.update_xaxes(title='Cost abatement of the picked strategy ($ per tCO₂e per year)', tickprefix='$')
        fig.update_yaxes(title='Emissions reduced (MtCO₂e per year, cumulative)')
        note = (f"Each point is the cumulative reductions of {country}'s picked assets whose cost abatement (net present value ÷ "
                f"annual reductions) is at most that much; the axis covers ${fmt(ax['lo'])} to ${fmt(ax['hi'])}. "
                'Assets without a positive reduction have no cost abatement and are left out.')
    fig.update_layout(legend=dict(orientation='h', yanchor='top', y=-0.14, x=0), hovermode='closest', margin=dict(l=60, r=20, t=30, b=170))
    st.plotly_chart(fig, use_container_width=True, key='el_c_chart_fig')
    st.caption(note)

    if scen is None:
        st.info('Select a scenario above to see what it picks in ' + country + '.')
        return

    # ── selected scenario ──
    g, t = data[scen], tots[scen]
    accent = colors[scen]
    st.markdown('---')
    st.markdown(f'<div class="el-h" style="--c:{accent}">{labels[scen]}{" (baseline)" if scen == baseline else ""}</div>',
                unsafe_allow_html=True)
    st.caption(f"{country} · reductions = {BASIS_LABEL[basis_of[scen]]} · costs at the {rate_label}")
    st.markdown(f"_{meta['scenario_rules'][scen]}_")
    if g.empty:
        st.warning(f'This scenario selects no assets in {country}: none of its strategies meet the rule there.')
        return
    vr = (t['red'] / tb['red']) if tb['red'] > 0 else None
    cpt_s = (t['cost'] / t['red']) if t['red'] > 0 else None
    cpt_b = (tb['cost'] / tb['red']) if tb['red'] > 0 else None
    _tiles([
        ('Assets', fmt(t['assets']), f"<b>{pct(t['assets'] / n_assets)}</b> of {fmt(n_assets)} with an electrification strategy"),
        ('Strategies', fmt(t['n_strat']), f"of {fmt(n_strat_all)} electrification strategies in {country}"),
        ('Fuel replaced', ej(t['tjf']), None, 'fuel energy the picked strategies replace'),
        ('Electricity added', ej(t['tje']), None, 'electricity the picked strategies use'),
        ('Emissions reduced', gtmt(t['red']), f"<b>{pct(vr, 0)}</b> of the baseline reduction",
         f"{pct(t['neg'] / t['red'])} of the reduction saves money (negative cost)" if t['red'] > 0 else None, True),
        _total_cost_tile(t['cost'], t['cp']),
        _per_t_tile(t['cost'], t['red'], (f"<b>{pct(cpt_s / cpt_b, 0)}</b> of the baseline's" if (cpt_s is not None and cpt_b and cpt_b > 0) else None)),
    ], accent=accent)

    view = st.radio('Breakdown', ['strategy', 'sector', 'top'], horizontal=True, key='el_c_view',
                    format_func={'strategy': 'By strategy', 'sector': 'By sector', 'top': 'Assets'}.get)
    vk = f'c_{rate}_{country}_{scen}_{view}'
    _cost_note()
    if view == 'strategy':
        rows_s = _grp(g, ['subsector', 'strategy'])
        impl = {(r['subsector'], r['name']): r for r in summary[rate]['scenarios'][scen]['strategies']}
        df = _breakdown_df(rows_s, 'Strategy', lambda r: r['strategy'], activity_unit=True, total=False)
        df.insert(1, 'Sector', [SUB_LABEL[r['subsector']] for r in rows_s])
        df['Activity'] = [f"{big_fmt(r['act'])} {ACT_UNIT[r['subsector']]}" if _ok(r.get('act')) else '' for r in rows_s]
        def _impl(r):
            i = impl.get((r['subsector'], r['strategy']))
            if not i or i.get('impl') is None:
                return '–'
            return fmt(i['impl'], 1) + ('' if i['impl_min'] == i['impl_max'] else f" ({fmt(i['impl_min'])}–{fmt(i['impl_max'])})")
        df['Implementation time (years, global)'] = [_impl(r) for r in rows_s]
        _show(df, _cfg_breakdown('Strategy', extra_cols={'Activity': _C.TextColumn('Activity (sector units)')}),
              height=min(700, 60 + 35 * len(df)))
    elif view == 'sector':
        _sector_block(_grp(g, ['subsector']), True)
    else:
        n_show = int(st.number_input('Assets to show', min_value=1, max_value=len(g), value=min(100, len(g)), step=50,
                                     key='el_c_n'))
        _asset_table(g.head(n_show), f"First {fmt(n_show)} of {fmt(len(g))} assets, {meta['scenario_order'][scen]}", vk)

    # ── downloads ──
    st.markdown('---')
    st.markdown('#### Downloads')
    d1, d2 = st.columns(2)
    out = g.copy()
    out['cumulative_goal_energy_EJ'] = out['tj'].cumsum() / 1e6
    out['cumulative_emissions_reduced_MtCO2e'] = out['red'].cumsum() / 1e6
    out['cost_abatement_usd_per_tCO2e_per_year'] = np.where((out['red'] > 0) & out['cost'].notna(), out['cost'] / out['red'], np.nan)
    d1.download_button(f'Download {country} assets for this scenario (CSV)',
                       out.drop(columns=['scenario']).to_csv(index=False).encode('utf-8'),
                       file_name=f'{country}_{scen}_{rate}_assets.csv'.replace(' ', '_'), mime='text/csv')
    d2.download_button(f'Download the {country} scenario comparison (CSV)', cmp_df.to_csv(index=False).encode('utf-8'),
                       file_name=f'{country}_scenario_comparison_{rate}.csv'.replace(' ', '_'), mime='text/csv')
