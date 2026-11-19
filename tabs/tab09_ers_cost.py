"""ERS Cost & Reduction Analysis (static data, not part of the monthly refresh).

Native Streamlit port of CT_ERS_Cost_Interactive_Dashboard_v75.html. Data lives in
data/ers_cost/ (see data/static_tools/extract_from_html.py).
"""
import json
import math
import re

import duckdb
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import CONFIG

# Same palette as the other tabs (tab08); 'fluorinated-gas' is the key used in this dataset.
SECTOR_COLORS = {
    'power':                  '#56979F',
    'transportation':         '#FBBA14',
    'fossil-fuel-operations': '#FF6F42',
    'agriculture':            '#E8516C',
    'manufacturing':          '#9554FF',
    'buildings':              '#03A0E3',
    'waste':                  '#BBD421',
    'mineral-extraction':     '#4380F5',
    'fluorinated-gas':        '#B6B4B4',
    'fluorinated-gases':      '#B6B4B4',
    'forestry-and-land-use':  '#779608',
}
FALLBACK_COLOR = '#667085'
LOW_COLOR = '#2fbf9b'    # low-cost scenario markers (lighter than the HTML's green so it reads on dark)
HIGH_COLOR = '#ff6b5e'   # high-cost scenario markers
GRID = 'rgba(128,128,128,0.25)'

FILTERS = ['sector', 'subsector', 'asset_type', 'ers_key', 'Continent']
FILTER_LABELS = {'sector': 'Sector', 'subsector': 'Subsector', 'asset_type': 'Asset type',
                 'ers_key': 'ERS', 'Continent': 'Continent'}
GROUP_OPTIONS = {
    'ers_combined': 'ERS ID + name', 'sector': 'Sector', 'subsector': 'Subsector',
    'subsector_continent': 'Subsector + Continent', 'continent_ers': 'Continent + ERS ID + name',
    'asset_type': 'Asset type', 'Continent': 'Continent', '__row__': 'No grouping / lowest-level data',
}
SORT_OPTIONS = {
    'individual': 'Sort individually', 'npv': 'NPV Cost / tCO₂e (low → high)',
    'red': 'Reductions (high → low)', 'em': 'Emissions (high → low)',
    'ratio': 'Reduction / emissions (high → low)',
}
SIM_CONTINENTS = ['Global Average', 'Asia', 'Africa', 'Europe', 'North America', 'South America', 'Oceania']
CSV_COLS = [
    'sector', 'subsector', 'asset_type', 'ers_id', 'strategy_name', 'Continent',
    'NPV_Cost_Avg_5', 'NPV_Cost_Avg_10', 'PV_low_lifetime_5', 'PV_high_lifetime_5',
    'PV_low_lifetime_10', 'PV_high_lifetime_10', 'Reductions', 'Reduction_asset', 'Emissions',
    'implementation_year', 'lifetime_year', 'CAPEX_low', 'CAPEX_high', 'OPEX_low', 'OPEX_high',
    'data source considered', 'additional technology assumptions needed for these costs',
    'general cost assessment',
]
P = 'ersc_'   # session-state key prefix


# ── DuckDB caching ────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_df(sql):
    con = duckdb.connect()
    result = con.execute(sql).df()
    con.close()
    return result


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_meta(path):
    with open(path) as f:
        return json.load(f)


def _load_data():
    df = _cached_df(f"SELECT * FROM '{CONFIG['ers_cost_path']}'").reset_index(drop=True)
    df['ers_key'] = [f'{_s(i)} — {_s(n)}' for i, n in zip(df['ers_id'], df['strategy_name'])]
    return df


# ── Pure helpers (ports of the HTML tool's JS) ────────────────────────────────

def _s(v):
    """JS String(v ?? '')."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ''
    if isinstance(v, (float, np.floating)) and float(v).is_integer():
        return str(int(v))
    return str(v)


def _natural_key(s):
    return [(0, int(t)) if t.isdigit() else (1, t.lower()) for t in re.split(r'(\d+)', str(s))]


def _uniq(values):
    return sorted({v for v in values if v not in ('', None) and not (isinstance(v, float) and math.isnan(v))},
                  key=_natural_key)


def _finite(v):
    return v is not None and isinstance(v, (int, float, np.floating, np.integer)) and math.isfinite(v)


def _fmt(v, d=1):
    """JS fmt(): K/M/B/T abbreviations."""
    if not _finite(v):
        return '—'
    a = abs(v)
    if a >= 1e12:
        return f'{v / 1e12:.{d}f}T'
    if a >= 1e9:
        return f'{v / 1e9:.{d}f}B'
    if a >= 1e6:
        return f'{v / 1e6:.{d}f}M'
    if a >= 1e3:
        return f'{v / 1e3:.{d}f}K'
    out = f'{v:,.2f}'.rstrip('0').rstrip('.')
    return out if out not in ('-0', '') else '0'


def _short_label(s, n=22):
    s = _s(s)
    if len(s) <= n:
        return s
    words = re.split(r'\s+', re.sub(r'[_-]+', ' ', s).strip())
    out = ''
    for w in words:
        if len((out + ' ' + w).strip()) > n:
            break
        out = (out + ' ' + w).strip()
    return (out or s[:n - 1]) + '…'


def _signed_log(v):
    return math.copysign(math.log10(1 + abs(v)), v) if _finite(v) else None


def _signed_log_ticks(values):
    finite = [v for v in values if _finite(v)]
    if not finite:
        return {'tickmode': 'auto'}
    lo, hi = min(0, min(finite)), max(0, max(finite))
    ticks = [0]
    top = math.ceil(math.log10(1 + max(abs(lo), abs(hi))))
    for p in range(top + 1):
        val = 10 ** p
        if val <= hi * 1.1:
            ticks.append(val)
        if -val >= lo * 1.1:
            ticks.append(-val)
    ticks = sorted(set(ticks))
    return {'tickmode': 'array', 'tickvals': [_signed_log(t) for t in ticks],
            'ticktext': [_usd(t, 0) for t in ticks]}


def _cash_format(v):
    """Plain number (quantities): thousands separators, no decimals unless the value is fractional."""
    if not _finite(v):
        return '—'
    if float(v).is_integer() or abs(v) >= 1000:
        return f'{v:,.0f}'
    digits = 4 if round(v, 2) == 0 and v != 0 else 2
    return f'{v:,.{digits}f}'


def _usd(v, d=None):
    """Dollar amount: $1,234 (no decimals) for large values, 2 decimals only below $100, 4 for tiny values."""
    if not _finite(v):
        return '—'
    if d is None:
        a = abs(v)
        d = 0 if a >= 100 or v == 0 else (4 if round(a, 2) == 0 else 2)
    return f"{'-' if v < 0 else ''}${abs(v):,.{d}f}"


def _usd_short(v, d=1):
    """Dollar amount with K/M/B/T abbreviations."""
    if not _finite(v):
        return '—'
    s_ = _fmt(abs(v), d)
    return f"{'-' if v < 0 else ''}${s_}"


def _cash_summary(v, money=False):
    if not _finite(v):
        return '—'
    m = abs(v)
    scale = 1e9 if money and m >= 1e9 else 1e6 if money and m >= 1e6 else 1
    suffix = 'B' if scale == 1e9 else 'M' if scale == 1e6 else ''
    return f"{'-' if v < 0 else ''}${abs(v) / scale:,.1f}{suffix}" if money else f'{v / scale:,.1f}{suffix}'


def _plain(v):
    """Editable-text representation of a number (no thousands separators, no sci notation)."""
    if v is None or not math.isfinite(v):
        return ''
    if float(v).is_integer():
        return str(int(v))
    return f'{v:.6f}'.rstrip('0').rstrip('.')


def _parse(text):
    try:
        v = float(str(text).replace(',', '').strip())
        return v if math.isfinite(v) else None
    except ValueError:
        return None


# ── Cost / reduction aggregation ──────────────────────────────────────────────

def _prep(df, rate, red_col):
    """Per-row NPV cost per tCO2e (avg/low/high) using the selected reduction denominator, plus weights."""
    d = df.copy()
    choice = d['Unit Choice'].astype(str).str.strip().str.lower()
    base = np.where(choice == 'capacity', d['Capacity'], d['Activity']) * d['Scaling Factor']
    red = d[red_col].astype(float)
    base_ok = pd.notna(base) & (base != 0)
    for tag, col in (('avg', f'NPV_Cost_Avg_{rate}'), ('low', f'PV_low_lifetime_{rate}'), ('high', f'PV_high_lifetime_{rate}')):
        uc = d[col].astype(float)
        ok = (red > 0) & base_ok & uc.notna()
        # unitCost / (reduction / base)
        d['v_' + tag] = np.where(ok, uc * base / red.where(red > 0, np.nan), np.nan)
        valid = ok & (red > 0)
        d['vw_' + tag] = np.where(valid, d['v_' + tag] * red, 0.0)
        d['w_' + tag] = np.where(valid, red, 0.0)
    d['red_s'] = d['Reductions'].fillna(0.0)
    d['ra_s'] = d['Reduction_asset'].fillna(0.0)
    d['em_s'] = d['Emissions'].fillna(0.0)
    return d


def _wavg(group, tag):
    sw = group['w_' + tag].sum()
    return group['vw_' + tag].sum() / sw if sw > 0 else None


def _single_meta(values):
    vals = _uniq([_s(v) for v in values])
    return vals[0] if len(vals) == 1 else ''


def _dominant_sector(g):
    m = {}
    for sec, red, em in zip(g['sector'], g['Reductions'], g['Emissions']):
        w = abs(red) if _finite(red) and red != 0 else abs(em) if _finite(em) and em != 0 else 1
        m[_s(sec)] = m.get(_s(sec), 0) + w
    return max(m.items(), key=lambda kv: kv[1])[0] if m else ''


def _aggregate(d, group, red_col):
    """d: prepared rows. Returns a list of group dicts (the JS aggregate())."""
    out = []
    use_ra = red_col == 'Reduction_asset'

    def ratio(red, ra, em):
        num = ra if use_ra else red
        return num / em if _finite(em) and em != 0 and _finite(num) else None

    if group == '__row__':
        for i, (_, r) in enumerate(d.iterrows()):
            parts = [x for x in (_s(r['ers_key']), _s(r['asset_type']), _s(r['Continent'])) if x]
            label = ' | '.join(parts) or f'Row {i + 1}'
            red, ra, em = (None if pd.isna(r[c]) else float(r[c]) for c in ('Reductions', 'Reduction_asset', 'Emissions'))
            out.append({
                'k': f'{label} ␟ {i}', 'label': label, 'short': _short_label(label), 'sector': _s(r['sector']),
                'subsector': _s(r['subsector']), 'asset_type': _s(r['asset_type']), 'continent': _s(r['Continent']),
                'npv': None if pd.isna(r['v_avg']) else float(r['v_avg']),
                'npvLow': None if pd.isna(r['v_low']) else float(r['v_low']),
                'npvHigh': None if pd.isna(r['v_high']) else float(r['v_high']),
                'red': red, 'ra': ra, 'em': em, 'ratio': ratio(red, ra, em)})
        return out

    if group == 'subsector_continent':
        keys = [f"{_s(a) or '(blank)'} | {_s(b) or '(blank)'}" for a, b in zip(d['subsector'], d['Continent'])]
    elif group == 'continent_ers':
        keys = [f"{_s(a) or '(blank)'} | {_s(b) or '(blank)'}" for a, b in zip(d['Continent'], d['ers_key'])]
    elif group == 'ers_combined':
        keys = [_s(v) or '(blank)' for v in d['ers_key']]
    else:
        keys = [_s(v) or '(blank)' for v in d[group]]
    for k, g in d.groupby(pd.Series(keys, index=d.index), sort=False):
        red, ra, em = g['red_s'].sum(), g['ra_s'].sum(), g['em_s'].sum()
        out.append({
            'k': k, 'label': k, 'short': _short_label(k),
            'sector': _single_meta(g['sector']) or _dominant_sector(g),
            'subsector': _single_meta(g['subsector']), 'asset_type': _single_meta(g['asset_type']),
            'continent': _single_meta(g['Continent']),
            'npv': _wavg(g, 'avg'), 'npvLow': _wavg(g, 'low'), 'npvHigh': _wavg(g, 'high'),
            'red': red, 'ra': ra, 'em': em, 'ratio': ratio(red, ra, em)})
    return out


# ── Charts ────────────────────────────────────────────────────────────────────

def _hover(x, value_label, value, money=False):
    parts = [f"<b>{x['label']}</b>"]
    for lab, key in (('Sector', 'sector'), ('Subsector', 'subsector'), ('Asset type', 'asset_type'), ('Continent', 'continent')):
        if x.get(key):
            parts.append(f'{lab}: {x[key]}')
    if money:
        parts.append(f"{value_label}: {_usd(value, 2)}")
    else:
        parts.append(f"{value_label}: {f'{value:,.2f}'.rstrip('0').rstrip('.') if _finite(value) else '—'}")
    return '<br>'.join(parts)


def _bar_chart(agg, field, title, ytitle, shared_order, log_scale, red_col):
    if shared_order is not None:
        by_k = {x['k']: x for x in agg}
        a = [by_k[k] for k in shared_order if k in by_k]
    else:
        a = sorted((x for x in agg if _finite(x[field])), key=lambda x: x[field] if field == 'npv' else -x[field])
    xvals = list(range(len(a)))
    ys = [x[field] for x in a]
    colors = [SECTOR_COLORS.get(x['sector'], FALLBACK_COLOR) for x in a]
    is_log = field == 'npv' and log_scale == 'log'
    tf = (lambda v: _signed_log(v)) if is_log else (lambda v: v)

    fig = go.Figure()
    fig.add_bar(x=xvals, y=[tf(v) for v in ys], width=0.8, name='Weighted average' if field == 'npv' else title,
                customdata=[_hover(x, title, x[field], field == 'npv') for x in a], marker_color=colors,
                hovertemplate='%{customdata}<extra></extra>', showlegend=False)
    marker_line = dict(color='rgba(255,255,255,0.7)', width=1)
    if field == 'npv':
        for name, key, color, lab in (('Low', 'npvLow', LOW_COLOR, 'NPV Cost / tCO₂e — Low'),
                                      ('High', 'npvHigh', HIGH_COLOR, 'NPV Cost / tCO₂e — High')):
            fig.add_scatter(x=xvals, y=[tf(x[key]) for x in a], mode='markers', name=name,
                            customdata=[_hover(x, lab, x[key], True) for x in a],
                            marker=dict(symbol='circle', size=8, color=color, line=marker_line),
                            hovertemplate='%{customdata}<extra></extra>')
    if field == 'ratio':
        pass
    if field == 'red':
        fig.add_scatter(x=xvals, y=[x['ra'] for x in a], mode='markers', name='Reduction asset',
                        customdata=[_hover(x, 'Reduction asset', x['ra']) for x in a],
                        marker=dict(symbol='circle', size=8, color='#98a2b3', line=marker_line),
                        hovertemplate='%{customdata}<extra></extra>')

    yaxis = dict(title=dict(text=ytitle, standoff=18), gridcolor=GRID, zerolinecolor='rgba(152,162,179,0.8)',
                 automargin=False, autorange=True)
    if is_log:
        yaxis.update(_signed_log_ticks([v for x in a for v in (x['npv'], x['npvLow'], x['npvHigh'])]))
    elif field == 'npv':
        yaxis.update(tickprefix='$', tickformat=',.0f', exponentformat='none')
    fig.update_layout(
        title=dict(text=title, font=dict(size=18), y=0.93, yanchor='top'),
        margin=dict(l=125, r=30, t=82, b=85), height=520, bargap=0.2, dragmode='zoom',
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(size=13),
        showlegend=field in ('npv', 'red'), legend=dict(orientation='h', x=0, y=1, yanchor='bottom'),
        yaxis=yaxis,
        xaxis=dict(range=[-0.5, max(0.5, len(xvals) - 0.5)], type='linear', dtick=1, tickmode='array',
                   tickvals=xvals, ticktext=[x['short'] for x in a], tickangle=-35, gridcolor=GRID,
                   automargin=False, rangeslider=dict(visible=True, thickness=0.055)))
    return fig


def _cash_axis(traces_y):
    vals = [v for ys in traces_y for v in ys if _finite(v)]
    mx = max([0] + [abs(v) for v in vals])
    return dict(tickprefix='$', tickformat=',.4f' if 0 < mx < 0.005 else (',.2f' if 0 < mx < 10 else ',.0f'),
                exponentformat='none', separatethousands=True)


# ── Simulator math (exact port) ───────────────────────────────────────────────

def _build_cash_flows(cap, op, r, impl, life, revenue=0.0, inflation=0.0, growth=0.0):
    impl_years = max(0, impl)
    total = impl_years + life
    years, annual, discounted, cumulative, operating, sales = [0], [-cap], [-cap], [-cap], [0.0], [0.0]
    cum = -cap
    for y in range(1, int(total) + 1):
        active = y > impl_years
        op_cash = -op * (1 + inflation) ** y if active else 0.0
        rev_cash = revenue * (1 + growth) ** y if active else 0.0
        cf = op_cash + rev_cash
        dcf = cf / (1 + r) ** y
        years.append(y)
        operating.append(op_cash)
        sales.append(rev_cash)
        annual.append(cf)
        discounted.append(dcf)
        cum += dcf
        cumulative.append(cum)
    return dict(years=years, annual=annual, discounted=discounted, cumulative=cumulative,
                operating=operating, sales=sales)


def _break_even(flow):
    c, y = flow['cumulative'], flow['years']
    if not c or c[0] >= 0:
        return y[0] if y else 0
    for i in range(1, len(c)):
        if c[i] >= 0 and c[i - 1] < 0:
            gain = c[i] - c[i - 1]
            return y[i] if gain == 0 else y[i - 1] + (-c[i - 1] / gain) * (y[i] - y[i - 1])
    return None


def _quantity_basis(choice, cost_unit, product):
    basis = str(choice or '').strip().lower()
    name = 'Activity' if basis == 'activity' else 'Capacity' if basis == 'capacity' else 'Quantity'
    raw = re.sub(r'^\s*USD\s+(?:per\s+|/\s*)', '', str(cost_unit or ''), flags=re.I).strip() or 'units'
    unit = {'tonne': 'tonnes', 'barrel': 'barrels', 'hectare': 'hectares', 'head': 'head', 'm2': 'm²'}.get(raw, raw)
    ref = str(product or '').strip()
    if ref:
        if raw in ('tonne', 'barrel', 'head') and not re.match(r'^kg\b', ref, re.I):
            unit += f' of {ref}'
        else:
            unit += f' · {ref}'
    else:
        unit += ' · reference not specified'
    return name, unit


def _simulate(cap_low, cap_high, op_low, op_high, rate_pct, impl, life, quantity, revenue, inflation_pct, growth_pct):
    """Inputs are the sign-flipped 'cash-flow' fields as typed in the UI (negative = cost)."""
    r = max(0.0, min(20.0, rate_pct)) / 100
    impl = max(0, round(impl))
    life = max(1, round(life))
    cl, ch, ol, oh = -cap_low, -cap_high, -op_low, -op_high
    quantity = max(0.0, quantity)
    revenue = max(0.0, revenue)
    inflation = max(-100.0, inflation_pct) / 100
    growth = max(-100.0, growth_pct) / 100
    cl, ch, ol, oh = cl * quantity, ch * quantity, ol * quantity, oh * quantity
    ca, oa = (cl + ch) / 2, (ol + oh) / 2
    low = _build_cash_flows(cl, ol, r, impl, life, revenue, inflation, growth)
    avg = _build_cash_flows(ca, oa, r, impl, life, revenue, inflation, growth)
    high = _build_cash_flows(ch, oh, r, impl, life, revenue, inflation, growth)
    return dict(low=low, avg=avg, high=high, ca=ca, impl=impl, life=life, quantity=quantity, revenue=revenue,
                be_low=_break_even(low), be_avg=_break_even(avg), be_high=_break_even(high))


# ── Streamlit UI ──────────────────────────────────────────────────────────────

def _css():
    # Colours are translucent greys so the tiles read on BOTH Streamlit's light and dark themes
    # (the first version hard-coded #262730, which made the text unreadable on the light theme).
    st.markdown(
        """
        <style>
        .ersc-kpi { background:rgba(128,128,128,0.10); border:1px solid rgba(128,128,128,0.28); border-radius:10px;
                    padding:10px 14px; height:100%; color:inherit; }
        .ersc-kpi .lab { font-size:13px; opacity:.7; text-transform:uppercase; font-weight:700; letter-spacing:.03em; }
        .ersc-kpi .val { font-size:24px; font-weight:700; margin-top:2px; }
        .ersc-kpi .sub { font-size:13px; opacity:.65; margin-top:2px; line-height:1.25; }
        .ersc-mini { background:rgba(128,128,128,0.10); border:1px solid rgba(128,128,128,0.28); border-radius:8px;
                     padding:6px 8px; text-align:center; color:inherit; margin-bottom:8px; }
        .ersc-mini span { display:block; font-size:13.5px; opacity:.7; }
        .ersc-mini b { font-size:18px; }
        /* chart controls: compact, sitting inside the Summary charts card */
        .st-key-ersc_charts [data-testid="stSelectbox"] label p { font-size:0.82rem; opacity:.75; text-transform:uppercase;
                    letter-spacing:.03em; font-weight:600; }
        .st-key-ersc_charts [data-baseweb="select"] > div { min-height:34px; font-size:0.92rem; }
        .st-key-ersc_charts [data-testid="stSelectbox"] { margin-bottom:-0.4rem; }
        /* ── simulator (modelled on the original HTML tool) ── */
        .st-key-ersc_sim { padding: 6px 10px 10px; }
        /* parameter panel: one quiet panel, plain outlined inputs, tight spacing */
        .st-key-ersc_params { background:rgba(128,128,128,0.07); border:1px solid rgba(128,128,128,0.30);
                              border-radius:8px; padding:16px; }
        .st-key-ersc_params hr { margin:0.1rem 0; }
        .st-key-ersc_params [data-testid="stVerticalBlock"] { gap:0.55rem; }
        .st-key-ersc_params label p, .st-key-ersc_params [data-testid="stWidgetLabel"] p {
            font-size:14px; font-weight:600; line-height:1.3; }
        .st-key-ersc_params [data-baseweb="input"], .st-key-ersc_params [data-baseweb="base-input"],
        .st-key-ersc_params [data-baseweb="select"] > div { background:transparent !important;
            border:1px solid rgba(128,128,128,0.45); border-radius:5px; min-height:36px; }
        .st-key-ersc_params input { font-size:14.5px; padding:8px 10px; font-variant-numeric:tabular-nums; }
        .st-key-ersc_params [data-baseweb="select"] > div { font-size:14.5px; }
        .st-key-ersc_params [data-testid="stCaptionContainer"] { font-size:12.5px; margin-top:-0.2rem; }
        .st-key-ersc_params { box-sizing:border-box; overflow:hidden; }
        .st-key-ersc_params > [data-testid="stElementContainer"] { width:auto !important; max-width:100% !important; min-width:0; }
        .st-key-ersc_params .stButton { width:100% !important; max-width:100%; }
        .st-key-ersc_params .stButton > button { width:100% !important; max-width:100%; box-sizing:border-box; }
        .st-key-ersc_params .stButton button { min-height:38px; font-size:14px; padding:0.35rem 0.5rem; height:auto; }
        .st-key-ersc_params .stButton button p { white-space:normal; overflow-wrap:anywhere; line-height:1.25; }
        [data-testid="stCaptionContainer"] { font-size: 0.92rem; }
        .ersc-h3 { font-size:15px; font-weight:600; margin:2px 0 6px; opacity:.9; }
        /* expanders inside the simulator: flat, divider lines only (no boxes) */
        .st-key-ersc_sim [data-testid="stExpander"] details { border:none; border-bottom:1px solid rgba(128,128,128,0.28);
            border-radius:0; background:transparent; }
        .st-key-ersc_sim [data-testid="stExpander"] summary { padding:6px 2px; }
        .st-key-ersc_sim [data-testid="stExpander"] summary p { font-size:14.5px; font-weight:600; }
        </style>
        """,
        unsafe_allow_html=True)


def _kpi(col, label, value, sub):
    col.markdown(f'<div class="ersc-kpi"><div class="lab">{label}</div><div class="val">{value}</div>'
                 f'<div class="sub">{sub}</div></div>', unsafe_allow_html=True)


def _clear_filters():
    for k in FILTERS:
        st.session_state[P + 'f_' + k] = []


def _filtered_options(df):
    """Cascading filters: options for each filter depend only on selections to its left."""
    sel = {}
    for k in FILTERS:
        mask = pd.Series(True, index=df.index)
        for left in FILTERS[:FILTERS.index(k)]:
            if sel[left]:
                mask &= df[left].map(_s).isin(sel[left])
        options = _uniq(df.loc[mask, k].map(_s))
        key = P + 'f_' + k
        st.session_state[key] = [v for v in st.session_state.get(key, []) if v in options]
        sel[k] = st.session_state[key]
        yield k, options


def _apply_filters(df):
    mask = pd.Series(True, index=df.index)
    for k in FILTERS:
        chosen = st.session_state.get(P + 'f_' + k, [])
        if chosen:
            mask &= df[k].map(_s).isin(chosen)
    return df[mask]


def _simulator(all_df, rows):
    with st.container(border=True, key='ersc_sim'):
        _simulator_body(all_df, rows)


def _simulator_body(all_df, rows):
    st.markdown('### ERS cash-flow simulator')
    sub_vals = _uniq(rows['subsector'].map(_s))
    if not sub_vals:
        st.info('No matching ERS for the current filters.')
        return

    left, right = st.columns([1, 1.6], gap='large')
    with left:
        params = st.container(border=False, key='ersc_params')
        with params:
            k_sub = P + 'sim_sub'
            if st.session_state.get(k_sub) not in sub_vals:
                st.session_state[k_sub] = sub_vals[0]
            sub = st.selectbox('Subsector', sub_vals, key=k_sub)
            ers_vals = _uniq(rows.loc[rows['subsector'].map(_s) == sub, 'ers_key'])
            k_ers = P + 'sim_ers'
            if st.session_state.get(k_ers) not in ers_vals:
                st.session_state[k_ers] = ers_vals[0]
            ers = st.selectbox('ERS', ers_vals, key=k_ers)

            ers_rows = all_df[(all_df['subsector'].map(_s) == sub) & (all_df['ers_key'] == ers)]
            k_cont = P + 'sim_cont'
            cont = st.session_state.get(k_cont, 'Global Average')
            if cont != 'Global Average' and not (ers_rows['Continent'] == cont).any():
                st.session_state[k_cont] = 'Global Average'
            cont = st.selectbox('Continent', SIM_CONTINENTS, key=k_cont)
            sim_rows = ers_rows if cont == 'Global Average' else ers_rows[ers_rows['Continent'] == cont]

            def avg(c):
                v = sim_rows[c].dropna()
                return float(v.mean()) if len(v) else None

            def first(c, clean=lambda v: True):
                vals = _uniq([_s(v) for v in sim_rows[c] if clean(_s(v))])
                return vals[0] if vals else ''

            defaults = dict(
                impl=round(avg('implementation_year') or 0), life=round(avg('lifetime_year') or 20),
                cap_low=avg('CAPEX_low') or 0.0, cap_high=avg('CAPEX_high') or 0.0,
                op_low=avg('OPEX_low') or 0.0, op_high=avg('OPEX_high') or 0.0,
                unit=first('Unit'), choice=first('Unit Choice'),
                product=' / '.join(_uniq([_s(v) for v in sim_rows['Final Product']
                                          if _s(v) and not re.match(r'^(none|null|n/a)$', _s(v).strip(), re.I)])),
                name=first('strategy_name'), sector=first('sector'))

            sim_key = f'{sub}|{ers}|{cont}'
            if st.session_state.get(P + 'sim_key') != sim_key:
                st.session_state[P + 'sim_key'] = sim_key
                st.session_state.update({
                    P + 'qty': '1000000', P + 'rev': '0', P + 'infl': '0', P + 'growth': '0', P + 'rate': 5.0,
                    P + 'impl': _plain(defaults['impl']), P + 'life': _plain(defaults['life']),
                    P + 'cap_low': _plain(round(-defaults['cap_low'], 2)), P + 'cap_high': _plain(round(-defaults['cap_high'], 2)),
                    P + 'op_low': _plain(round(-defaults['op_low'], 2)), P + 'op_high': _plain(round(-defaults['op_high'], 2)),
                })

            name, unit = _quantity_basis(defaults['choice'], defaults['unit'], defaults['product'])
            qty_label = f"{name}{'' if name == 'Quantity' else ' quantity'} ({unit})"

            c1, c2 = st.columns(2)
            qty_t = c1.text_input(qty_label, key=P + 'qty')
            rev_t = c2.text_input('Annual business sales revenue (USD)', key=P + 'rev')
            c1, c2 = st.columns(2)
            infl_t = c1.text_input('Inflation rate (%) for cost', key=P + 'infl')
            growth_t = c2.text_input('Growth rate (%) for revenue', key=P + 'growth')
            st.caption('Annual rates compound from Year 0. Inflation applies to OPEX and growth applies to revenue.')
            rate = st.slider('Discount rate (%)', 0.0, 20.0, step=0.25, key=P + 'rate')
            c1, c2 = st.columns(2)
            impl_t = c1.text_input('Implementation years', key=P + 'impl')
            life_t = c2.text_input('Lifetime years', key=P + 'life')
            cl_t = c1.text_input('CAPEX low USD / unit', key=P + 'cap_low')
            ch_t = c2.text_input('CAPEX high USD / unit', key=P + 'cap_high')
            ol_t = c1.text_input('OPEX low USD / unit / year', key=P + 'op_low')
            oh_t = c2.text_input('OPEX high USD / unit / year', key=P + 'op_high')
            st.caption('CAPEX and OPEX: negative = cost; positive = saving.')
            st.button('Reset to selected ERS defaults', use_container_width=True,
                      on_click=lambda: st.session_state.__setitem__(P + 'sim_key', None))


    def num(text, fallback):
        v = _parse(text)
        return fallback if v is None else v

    def num_exact(text, exact):
        """Inputs show defaults rounded to 2 decimals; while the shown text is untouched, calculate with the exact default."""
        v = _parse(text)
        if v is None or abs(v - round(exact, 2)) < 1e-9:
            return exact
        return v

    sim = _simulate(
        num_exact(cl_t, -defaults['cap_low']), num_exact(ch_t, -defaults['cap_high']), num_exact(ol_t, -defaults['op_low']),
        num_exact(oh_t, -defaults['op_high']), rate, num(impl_t, 0), num(life_t, 1), num(qty_t, 1000000.0),
        num(rev_t, 0.0), num(infl_t, 0.0), num(growth_t, 0.0))
    low, avg_f, high = sim['low'], sim['avg'], sim['high']
    impl = sim['impl']
    color = SECTOR_COLORS.get(defaults['sector'], FALLBACK_COLOR)

    with params:
        st.divider()
        st.markdown('<div class="ersc-h3">Net Present Value (NPV)</div>', unsafe_allow_html=True)
        m = st.columns(3)
        for c, lab, v in zip(m, ('Low', 'Average', 'High'), (low['cumulative'][-1], avg_f['cumulative'][-1], high['cumulative'][-1])):
            c.markdown(f'<div class="ersc-mini"><span>{lab}</span><b>{_cash_summary(v, True)}</b></div>', unsafe_allow_html=True)
        st.caption('negative = cost; positive = saving.')
        st.markdown('<div class="ersc-h3">Break-even years</div>', unsafe_allow_html=True)
        m = st.columns(3)
        for c, lab, b in zip(m, ('Low', 'Average', 'High'), (sim['be_low'], sim['be_avg'], sim['be_high'])):
            c.markdown(f"<div class=\"ersc-mini\"><span>{lab}</span><b>{'N/A' if b is None else _cash_summary(b) + ' years'}</b></div>",
                       unsafe_allow_html=True)
        start = (f'Years 1–{impl} are implementation/development years with zero operating cash flow, and operations begin in Year {impl + 1}'
                 if impl > 0 else 'there is no implementation delay, and operations begin in Year 1')
        with st.expander('NPV calculation & break-even method'):
            st.markdown(
                'Net project NPV (USD) = quantity × CAPEX per unit + Σ [(annual sales revenue × (1+g)^year + quantity × annual OPEX '
                'per unit × (1+i)^year) / (1+r)^year]. CAPEX is paid at Year 0. Revenue and OPEX begin in the year after '
                'implementation and continue for the selected operating lifetime. Revenue is a total annual USD amount at Year 0 '
                'prices. The annual OPEX inflation rate i and revenue growth rate g compound from Year 0, including the '
                'implementation period. Inflation does not change upfront CAPEX. Positive OPEX savings also escalate at the cost '
                'inflation rate. Rates must be at least −100%. CAPEX and OPEX inputs use cash-flow signs: negative values are costs '
                'and positive values are savings or inflows. The final cumulative discounted cash flow equals net NPV. '
                'Break-even is its first zero-crossing.')
            st.markdown(f'**Break-even method:** first zero-crossing of cumulative discounted cash flow from project start; '
                        f'100% of CAPEX is paid at Year 0, {start}.')


    with right:
        st.markdown(f"#### {defaults['name']}")
        descs = _uniq([_s(v).strip() for v in sim_rows['strategy_description']])
        st.write('  \n'.join(descs) or 'Not provided in source data.')
        for col, label in (('data source considered', 'Data source considered'),
                           ('additional technology assumptions needed for these costs',
                            'Additional technology assumptions for ERS Cost'),
                           ('general cost assessment', 'General cost assessment')):
            with st.expander(label):
                vals = _uniq([_s(v).strip() for v in sim_rows[col]])
                for v in vals or ['Not provided in source data.']:
                    st.write(v)


        years = low['years']
        qty_txt = f"{name}: {_cash_format(sim['quantity'])} {unit}"
        base_layout = dict(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                           margin=dict(l=125, r=30, t=82, b=100), legend=dict(orientation='h', y=1, yanchor='bottom'),
                           height=440, showlegend=True, font=dict(size=13))

        # cumulative discounted cash flow
        cum_traces = [
            ('Average cumulative', avg_f['cumulative'], dict(mode='lines', line=dict(width=4, color=color)), 'Average cumulative discounted CF'),
            ('Low cost cumulative', low['cumulative'], dict(mode='lines+markers', line=dict(width=1.5, dash='dot', color=LOW_COLOR), marker=dict(size=5)), 'Low cumulative discounted CF'),
            ('High cost cumulative', high['cumulative'], dict(mode='lines+markers', line=dict(width=1.5, dash='dash', color=HIGH_COLOR), marker=dict(size=5)), 'High cumulative discounted CF'),
        ]
        fig = go.Figure()
        for nm, ys, kw, hl in cum_traces:
            fig.add_scatter(x=years, y=ys, name=nm, customdata=[_usd(v) for v in ys],
                            hovertemplate=f'Year %{{x}}<br>{hl}: %{{customdata}}<extra></extra>', **kw)
        shapes = [dict(type='line', x0=0, x1=years[-1], y0=0, y1=0, line=dict(width=1, color='#98a2b3')),
                  dict(type='line', x0=impl + 0.5, x1=impl + 0.5, xref='x', yref='paper', y0=0, y1=1,
                       line=dict(dash='dot', width=1, color='#98a2b3'))]
        anns = []
        for b, t, c, ypos in ((sim['be_low'], 'Low break-even', LOW_COLOR, 0.96), (sim['be_avg'], 'Avg break-even', color, 0.89),
                              (sim['be_high'], 'High break-even', HIGH_COLOR, 0.82)):
            if b is not None:
                shapes.append(dict(type='line', x0=b, x1=b, yref='paper', y0=0, y1=1, line=dict(dash='dash', width=1.5, color=c)))
                anns.append(dict(x=b, y=ypos, yref='paper', text=t, showarrow=False, font=dict(size=12, color=c)))
        fig.update_layout(
            **base_layout, shapes=shapes, annotations=anns,
            title=dict(text=f'Net cumulative discounted cash flow · {qty_txt}', font=dict(size=18), y=0.93, yanchor='top'),
            xaxis=dict(title=dict(text='Project year', standoff=18), gridcolor=GRID, automargin=True),
            yaxis=dict(title=dict(text='Cumulative discounted cash flow (USD)', standoff=20), gridcolor=GRID,
                       zerolinecolor='rgba(152,162,179,0.8)', automargin=True,
                       **_cash_axis([avg_f['cumulative'], low['cumulative'], high['cumulative']])))
        st.plotly_chart(fig, use_container_width=True, key=P + 'fig_cum')

        # annual cash flow
        capex_opex = [-sim['ca'] if y == 0 else avg_f['operating'][i] for i, y in enumerate(years)]
        fig = go.Figure()
        fig.add_bar(x=years, y=capex_opex, name='CAPEX / average OPEX', marker_color=color, opacity=0.72,
                    customdata=[_usd(v) for v in capex_opex],
                    hovertemplate='Year %{x}<br>CAPEX / OPEX: %{customdata}<extra></extra>')
        if sim['revenue'] != 0:
            fig.add_bar(x=years, y=avg_f['sales'], name='Business sales revenue', marker_color=LOW_COLOR,
                        customdata=[_usd(v) for v in avg_f['sales']],
                        hovertemplate='Year %{x}<br>Revenue: %{customdata}<extra></extra>')
        fig.add_scatter(x=years, y=low['annual'], mode='markers', name='Low cost net',
                        marker=dict(size=8, symbol='circle-open', color=LOW_COLOR, line=dict(width=1.5)),
                        customdata=[_usd(v) for v in low['annual']],
                        hovertemplate='Year %{x}<br>Low: %{customdata}<extra></extra>')
        fig.add_scatter(x=years, y=high['annual'], mode='markers', name='High cost net',
                        marker=dict(size=8, symbol='diamond-open', color=HIGH_COLOR, line=dict(width=1.5)),
                        customdata=[_usd(v) for v in high['annual']],
                        hovertemplate='Year %{x}<br>High: %{customdata}<extra></extra>')
        fig.update_layout(
            **base_layout, barmode='group',
            shapes=[dict(type='line', x0=impl + 0.5, x1=impl + 0.5, yref='paper', y0=0, y1=1,
                         line=dict(dash='dot', width=1, color='#98a2b3'))],
            annotations=[dict(x=impl + 0.5, y=0.025, yref='paper', yanchor='bottom', text='Operations begin',
                              showarrow=False, font=dict(size=12, color='#475467'), bgcolor='rgba(255,255,255,0.9)', borderpad=3)],
            title=dict(text=f'Annual cash flow · {qty_txt}', font=dict(size=18), y=0.93, yanchor='top'),
            xaxis=dict(title=dict(text='Project year', standoff=18), gridcolor=GRID, automargin=True),
            yaxis=dict(title=dict(text='Annual cash flow (USD)', standoff=20), gridcolor=GRID,
                       zerolinecolor='rgba(152,162,179,0.8)', automargin=True,
                       **_cash_axis([capex_opex, low['annual'], high['annual']])))
        st.plotly_chart(fig, use_container_width=True, key=P + 'fig_cash')


def show_ers_cost():
    _css()
    df = _load_data()
    meta = _cached_meta(CONFIG['ers_cost_meta_path'])

    st.markdown('### ERS Cost & Reduction Analysis')
    st.caption(f"Interactive summary of cost-effectiveness and marginal cost abatement curve. "
               f"Last updated {meta.get('last_updated')} and the data version is {meta.get('data_version')}. "
               f"This tool uses a fixed snapshot and is not refreshed monthly.")

    # ── Filters ───────────────────────────────────────────────────────────────
    with st.container(border=True):
        head_l, head_r = st.columns([4, 1])
        head_l.markdown('**Filters**')
        head_r.button('Clear filters', on_click=_clear_filters, use_container_width=True)
        cols = st.columns(5)
        for col, (k, options) in zip(cols, _filtered_options(df)):
            col.multiselect(FILTER_LABELS[k], options, key=P + 'f_' + k)
        st.caption('Select from left to right: each filter shows options available under the selections to its left. '
                   'Selections on the right never change options on the left. An empty filter applies no restriction.')

    rows = _apply_filters(df)
    st.caption(f'{len(rows):,} of {len(df):,} rows selected')

    # KPI tiles sit above the charts card but depend on the controls inside it, so reserve their spot first.
    kpi_box = st.container()

    st.markdown('<div style="height:14px"></div>', unsafe_allow_html=True)

    # ── Summary charts card: controls live in the card, like the original ─────
    with st.container(border=True, key='ersc_charts'):
        # title on the left; the five controls are a compact group aligned to the right
        c = st.columns([3.0, 1, 1.45, 0.95, 1.7, 1.15], gap='small')
        c[0].markdown('#### Summary charts')
        rate = c[1].selectbox('Discount rate', ['5', '10'], format_func=lambda v: f'{v}%', key=P + 'rate_sel',
                              help='Marginal cost abatement discount rate')
        red_col = c[2].selectbox('NPV weight', ['Reductions', 'Reduction_asset'],
                                 format_func=lambda v: 'Reductions' if v == 'Reductions' else 'Reduction asset',
                                 key=P + 'weight')
        scale = c[3].selectbox('Y-axis scale', ['linear', 'log'],
                               format_func=lambda v: 'Original' if v == 'linear' else 'Log scale', key=P + 'scale')
        sort_field = c[4].selectbox('Sort charts by', list(SORT_OPTIONS), format_func=SORT_OPTIONS.get, key=P + 'sort')
        group = c[5].selectbox('Group by', list(GROUP_OPTIONS), index=list(GROUP_OPTIONS).index('subsector'),
                               format_func=GROUP_OPTIONS.get, key=P + 'group')

        prepared = _prep(rows, rate, red_col)
        w_label = 'Reduction asset' if red_col == 'Reduction_asset' else 'Reductions'

        all_groups = _aggregate(prepared, group, red_col)
        agg = [x for x in all_groups if _finite(x['npv']) and _finite(x['ratio'])]
        if not agg:
            st.info('No comparable groups for the current selection.')
        else:
            shared = None
            if sort_field != 'individual':
                shared = [x['k'] for x in sorted((x for x in agg if _finite(x[sort_field])),
                                                 key=lambda x: x[sort_field] if sort_field == 'npv' else -x[sort_field])]
            st.plotly_chart(_bar_chart(agg, 'npv', 'Marginal Cost Abatement (USD / tCO2e)', 'Abatement cost (USD / tCO₂e)',
                                       shared, scale, red_col), use_container_width=True, key=P + 'fig_npv')
            st.plotly_chart(_bar_chart(agg, 'ratio', f'{w_label.replace("Reductions", "Reduction")} / Emissions',
                                       'Reduction / emissions ratio', shared, scale, red_col),
                            use_container_width=True, key=P + 'fig_ratio')
            if len(agg) != len(all_groups):
                st.caption(f'{len(agg):,} comparable groups shown in both charts; {len(all_groups) - len(agg):,} groups '
                           f'omitted because cost or reduction/emissions data are unavailable.')

    # ── KPIs (filled in now that the controls have been read) ─────────────────
    with kpi_box:
        k = st.columns(5)
        _kpi(k[0], 'NPV cost / tCO₂e', _usd_short(_wavg(prepared, 'avg')),
             f'{rate}% discount rate · {w_label}')
        _kpi(k[1], 'ERS cost assumptions', f"{len(_uniq([_s(v) for v in rows['cost_id']])):,}", 'Distinct cost IDs in selection')
        _kpi(k[2], 'Subsectors', f"{len(_uniq([_s(v) for v in rows['subsector']])):,}", 'Distinct subsectors in selection')
        _kpi(k[3], 'Asset types', f"{len(_uniq([_s(v) for v in rows['asset_type']])):,}", 'Distinct asset types in selection')
        _kpi(k[4], 'ERS strategies', f"{len(_uniq([_s(v) for v in rows['ers_id']])):,}", 'Unique ERS IDs in selection')

    # ── Data table ────────────────────────────────────────────────────────────
    t_l, t_r = st.columns([4, 1])
    t_l.markdown('### Filtered data table')
    t_r.download_button('Download filtered CSV', rows[[c_ for c_ in CSV_COLS if c_ in rows.columns]].to_csv(index=False).encode('utf-8'),
                        file_name='filtered_ers_cost_data.csv', mime='text/csv', use_container_width=True)
    st.caption('One row per sector / subsector / asset type / ERS / continent combination. NPV cost/tCO₂e uses the selected '
               'weighting basis above. Top 1,000 rows by absolute reductions.')
    keys = ['sector', 'subsector', 'asset_type', 'ers_id', 'strategy_name', 'Continent']
    table = []
    if len(prepared):
        gk = pd.DataFrame({k_: prepared[k_].map(_s) for k_ in keys})
        for _, g in prepared.groupby([gk[k_] for k_ in keys], sort=False):
            first = gk.loc[g.index[0]]
            table.append({**{k_: first[k_] for k_ in keys}, 'npv': _wavg(g, 'avg'), 'red': g['red_s'].sum(),
                          'ra': g['ra_s'].sum(), 'em': g['em_s'].sum()})
    table.sort(key=lambda x: -abs(x['red']))
    tdf = pd.DataFrame([{
        'Sector': t['sector'], 'Subsector': t['subsector'], 'Asset type': t['asset_type'], 'ERS ID': t['ers_id'],
        'ERS name': t['strategy_name'], 'Continent': t['Continent'],
        'NPV Cost/tCO₂e': _usd_short(t['npv']), 'Reductions': _fmt(t['red']), 'Reduction asset': _fmt(t['ra']),
        'Emissions': _fmt(t['em'])} for t in table[:1000]])
    st.dataframe(tdf, use_container_width=True, hide_index=True, height=420)

    # ── Simulator ─────────────────────────────────────────────────────────────
    _simulator(df, rows)
