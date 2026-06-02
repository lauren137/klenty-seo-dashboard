"""Klenty SEO Live Tracking Dashboard."""
import hmac
import json
import os
import time
from datetime import datetime, date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from styles import ASANA_CSS
import data_store as ds
import google_clients as gc

st.set_page_config(
    page_title="Klenty SEO Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(ASANA_CSS, unsafe_allow_html=True)


# ---------------- Password gate ----------------
def _expected_password() -> str | None:
    try:
        if "app_password" in st.secrets:
            return st.secrets["app_password"]
    except Exception:
        pass
    return os.environ.get("APP_PASSWORD")


def check_password() -> bool:
    expected = _expected_password()
    if not expected:
        # No password configured = open access (dev mode)
        return True
    if st.session_state.get("authed"):
        return True

    # Centered login card
    st.markdown(
        """
        <div style="max-width: 380px; margin: 6rem auto 1rem; text-align: center;">
          <div style="
              width: 56px; height: 56px;
              background: linear-gradient(135deg, #F06A6A 0%, #F89A9A 100%);
              border-radius: 14px;
              display: inline-flex; align-items: center; justify-content: center;
              color: white; font-weight: 700; font-size: 1.5rem;
              margin-bottom: 1.25rem;
          ">K</div>
          <h2 style="margin: 0; font-weight: 600; letter-spacing: -0.02em;">Klenty SEO Dashboard</h2>
          <div style="color: #6F7782; font-size: 0.9rem; margin-top: 0.4rem;">
            Enter the password to continue
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns([1, 2, 1])
    with cols[1]:
        with st.form("login", clear_on_submit=False):
            pw = st.text_input("Password", type="password", label_visibility="collapsed", placeholder="Password")
            submitted = st.form_submit_button("Sign in", use_container_width=True, type="primary")
        if submitted:
            if hmac.compare_digest(pw, expected):
                st.session_state["authed"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    return False


if not check_password():
    st.stop()

ds.init_db()

# ---------------- Time ranges ----------------
RANGES = {
    "24h": 1,
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "6mo": 180,
    "1y": 365,
    "Custom": None,
}


def get_dates(label: str, custom_start: date | None, custom_end: date | None):
    if label == "Custom" and custom_start and custom_end:
        return custom_start.isoformat(), custom_end.isoformat(), (custom_end - custom_start).days + 1
    days = RANGES[label]
    start, end = gc.date_range(days)
    return start, end, days


def prior_dates(days: int):
    start, end = gc.prior_range(days)
    return start, end


# ---------------- Data layer w/ cache ----------------

@st.cache_data(ttl=900, show_spinner=False)
def fetch_metrics(urls: tuple, start: str, end: str):
    """Returns merged dict of {url: {clicks, impressions, ctr, position, views, sessions, users, bounce}}."""
    urls = list(urls)
    gsc = gc.gsc_page_metrics(urls, start, end)
    ga4 = gc.ga4_page_metrics(urls, start, end)
    out = {}
    for u in urls:
        g = gsc.get(u, {})
        a = ga4.get(u, {})
        out[u] = {
            "clicks": g.get("clicks", 0),
            "impressions": g.get("impressions", 0),
            "ctr": g.get("ctr", 0.0),
            "position": g.get("position"),
            "views": a.get("views", 0),
            "sessions": a.get("sessions", 0),
            "users": a.get("users", 0),
            "bounce": a.get("bounce", 0.0),
            "organic": a.get("organic", 0),
            "organic_users": a.get("organic_users", 0),
        }
    return out


@st.cache_data(ttl=900, show_spinner=False)
def fetch_overview(start: str, end: str):
    return {
        "gsc": gc.gsc_overview(start, end),
        "ga4": gc.ga4_overview(start, end),
        "ga4_organic": gc.ga4_organic_overview(start, end),
    }


@st.cache_data(ttl=900, show_spinner=False)
def fetch_daily(start: str, end: str):
    gsc = gc.gsc_overview_daily(start, end)
    ga4 = gc.ga4_overview_daily(start, end)
    by_date = {}
    for r in gsc:
        by_date.setdefault(r["date"], {"date": r["date"]}).update({
            "clicks": r["clicks"], "impressions": r["impressions"],
            "ctr": r["ctr"], "position": r["position"],
        })
    for r in ga4:
        by_date.setdefault(r["date"], {"date": r["date"]}).update({
            "sessions": r["sessions"], "users": r["users"], "views": r["views"],
        })
    return sorted(by_date.values(), key=lambda x: x["date"])


@st.cache_data(ttl=900, show_spinner=False)
def fetch_trend(page: str, start: str, end: str):
    gsc = gc.gsc_page_trend(page, start, end)
    ga4 = gc.ga4_page_trend(page, start, end)
    by_date = {}
    for r in gsc:
        by_date.setdefault(r["date"], {})["clicks"] = r["clicks"]
        by_date[r["date"]]["impressions"] = r["impressions"]
        by_date[r["date"]]["position"] = r["position"]
    for r in ga4:
        by_date.setdefault(r["date"], {})["views"] = r["views"]
        by_date[r["date"]]["sessions"] = r["sessions"]
        by_date[r["date"]]["users"] = r["users"]
    return sorted(
        [{"date": d, **v} for d, v in by_date.items()],
        key=lambda x: x["date"],
    )


# ---------------- Header ----------------
hdr_left, hdr_right = st.columns([3, 1])
with hdr_left:
    st.markdown(
        """
        <div class="dash-title">
            <span class="dash-logo">K</span>
            <div>
                Klenty SEO Dashboard
                <div class="dash-subtitle">Live tracking · GSC + GA4 · klenty.com</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with hdr_right:
    c1, c2 = st.columns(2)
    with c1:
        if st.button("⟳ Refresh", use_container_width=True):
            st.cache_data.clear()
            ds.cache_clear()
            st.rerun()
    with c2:
        if st.button("+ Add URL", type="primary", use_container_width=True):
            st.session_state["show_add"] = True

st.markdown("<hr style='margin: 0.5rem 0 1.5rem; border: 0; border-top: 1px solid #EDEDED;'>", unsafe_allow_html=True)

# ---------------- Sidebar ----------------
with st.sidebar:
    st.markdown("### Filters")
    range_label = st.radio(
        "Time range",
        list(RANGES.keys()),
        index=2,
        label_visibility="collapsed",
    )

    custom_start = custom_end = None
    if range_label == "Custom":
        today = date.today()
        custom_start = st.date_input("Start", value=today - timedelta(days=30), max_value=today)
        custom_end = st.date_input("End", value=today, max_value=today)

    st.markdown("---")
    st.markdown("### Sort by")
    sort_col = st.selectbox(
        "Sort",
        ["Clicks ↓", "Impressions ↓", "Position ↑", "CTR ↓", "Organic Traffic ↓", "Users ↓", "Sessions ↓", "Views ↓", "Page A→Z"],
        label_visibility="collapsed",
    )

    st.markdown("### Search")
    search = st.text_input("Search URLs", placeholder="filter URLs...", label_visibility="collapsed")

    st.markdown("---")
    st.markdown("### Tracked URLs")
    all_urls = ds.list_urls()
    st.markdown(f"<div style='color:#6F7782; font-size:0.85rem'>{len(all_urls)} pages tracked</div>", unsafe_allow_html=True)

    if _expected_password() and st.session_state.get("authed"):
        if st.button("Sign out", type="secondary", use_container_width=True):
            st.session_state["authed"] = False
            st.rerun()
        st.markdown("---")

    with st.expander("Manage list"):
        for u in all_urls:
            cc1, cc2 = st.columns([6, 1])
            cc1.markdown(f"<div style='font-size:0.8rem; padding: 2px 0'>{u}</div>", unsafe_allow_html=True)
            if cc2.button("✕", key=f"del_{u}", help="Remove"):
                ds.remove_url(u)
                st.cache_data.clear()
                st.rerun()


# ---------------- Add URL dialog ----------------
if st.session_state.get("show_add"):
    with st.container():
        st.markdown("### Add a URL to track")
        new_url = st.text_input("Paste path or full URL", placeholder="/blog/your-page/ or https://www.klenty.com/blog/your-page/")
        col_a, col_b, _ = st.columns([1, 1, 4])
        if col_a.button("Add", type="primary"):
            if new_url.strip():
                path = new_url.strip()
                if path.startswith("http"):
                    from urllib.parse import urlparse
                    path = urlparse(path).path
                if ds.add_url(path):
                    st.success(f"Added {path}")
                    st.session_state["show_add"] = False
                    st.cache_data.clear()
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.warning("Already tracked.")
        if col_b.button("Cancel", type="secondary"):
            st.session_state["show_add"] = False
            st.rerun()
        st.markdown("---")


# ---------------- Resolve dates + fetch ----------------
start, end, days = get_dates(range_label, custom_start, custom_end)
p_start, p_end = prior_dates(days)

st.markdown(
    f"<div style='color:#6F7782; font-size:0.85rem; margin-bottom:1rem;'>"
    f"Showing data from <b style='color:#1E1F21'>{start}</b> to <b style='color:#1E1F21'>{end}</b> "
    f"({days} day{'s' if days != 1 else ''}) · auto-refresh every 15 min · last fetch {datetime.now().strftime('%H:%M')}"
    f"</div>",
    unsafe_allow_html=True,
)

if not all_urls:
    st.info("No URLs tracked yet. Click **+ Add URL** to start.")
    st.stop()

# Warn on 24h — GSC data lags by ~2 days
if days <= 1:
    st.warning("⚠ GSC data has a ~2-day lag — recent 24h numbers may be incomplete. GA4 data is fresher.")

# ---------------- Overview cards ----------------
with st.spinner("Loading metrics..."):
    overview = fetch_overview(start, end)
    prior = fetch_overview(p_start, p_end)
    metrics = fetch_metrics(tuple(all_urls), start, end)


def delta_str(curr, prev, fmt="{:+.1f}%", inverse=False):
    if prev in (0, None) or curr is None:
        return '<span class="delta-flat">—</span>'
    pct = (curr - prev) / prev * 100
    cls = "delta-flat"
    if pct > 0.5:
        cls = "delta-down" if inverse else "delta-up"
    elif pct < -0.5:
        cls = "delta-up" if inverse else "delta-down"
    arrow = "▲" if pct > 0 else ("▼" if pct < 0 else "•")
    return f'<span class="{cls}">{arrow} {abs(pct):.1f}% vs prior</span>'


def card(label, value, delta_html=""):
    return f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        <div class="metric-delta">{delta_html}</div>
    </div>
    """


g = overview["gsc"]; pg = prior["gsc"]
a = overview["ga4"]; pa = prior["ga4"]
ao = overview["ga4_organic"]; pao = prior["ga4_organic"]

# Row 1: Google Search Console (site-wide)
st.markdown('<div class="section-title">Klenty · Search Console</div>', unsafe_allow_html=True)
c1, c2, c3, c4 = st.columns(4)
c1.markdown(card("Clicks", f"{g['clicks']:,}", delta_str(g['clicks'], pg['clicks'])), unsafe_allow_html=True)
c2.markdown(card("Impressions", f"{g['impressions']:,}", delta_str(g['impressions'], pg['impressions'])), unsafe_allow_html=True)
c3.markdown(card("Avg Position", f"{g['position']:.1f}", delta_str(g['position'], pg['position'], inverse=True)), unsafe_allow_html=True)
c4.markdown(card("CTR", f"{g['ctr']:.2f}%", delta_str(g['ctr'], pg['ctr'])), unsafe_allow_html=True)

# Row 2: Site-wide traffic — Overall + Organic
st.markdown('<div class="section-title" style="margin-top:1.5rem;">Klenty · Site Traffic (GA4)</div>', unsafe_allow_html=True)
c5, c6, c7, c8 = st.columns(4)
c5.markdown(card("Overall Users", f"{a['users']:,}", delta_str(a['users'], pa['users'])), unsafe_allow_html=True)
c6.markdown(card("Overall Sessions", f"{a['sessions']:,}", delta_str(a['sessions'], pa['sessions'])), unsafe_allow_html=True)
c7.markdown(card("Organic Users", f"{ao['users']:,}", delta_str(ao['users'], pao['users'])), unsafe_allow_html=True)
c8.markdown(card("Organic Sessions", f"{ao['sessions']:,}", delta_str(ao['sessions'], pao['sessions'])), unsafe_allow_html=True)

# ---------------- Build dataframe ----------------
rows = []
for u in all_urls:
    if search and search.lower() not in u.lower():
        continue
    m = metrics[u]
    rows.append({
        "URL": u,
        "Position": m["position"] if m["position"] is not None else None,
        "Clicks": m["clicks"],
        "Impressions": m["impressions"],
        "CTR %": round(m["ctr"], 2),
        "Organic Traffic": m["organic"],
        "Organic Users": m["organic_users"],
        "Views": m["views"],
        "Sessions": m["sessions"],
        "Users": m["users"],
        "Bounce %": round(m["bounce"], 1),
    })
df = pd.DataFrame(rows)

# Sort
sort_map = {
    "Clicks ↓": ("Clicks", False),
    "Impressions ↓": ("Impressions", False),
    "Position ↑": ("Position", True),
    "CTR ↓": ("CTR %", False),
    "Organic Traffic ↓": ("Organic Traffic", False),
    "Users ↓": ("Users", False),
    "Sessions ↓": ("Sessions", False),
    "Views ↓": ("Views", False),
    "Page A→Z": ("URL", True),
}
col, asc = sort_map[sort_col]
df = df.sort_values(col, ascending=asc, na_position="last")

st.markdown('<div class="section-title">Tracked URLs · Performance</div>', unsafe_allow_html=True)

# ---- Custom HTML table with sticky header + sticky TOTAL row ----
import numpy as np

def _fmt_int(v):
    if pd.isna(v) or v is None: return "—"
    return f"{int(v):,}"

def _fmt_float1(v):
    if pd.isna(v) or v is None: return "—"
    return f"{v:.1f}"

def _fmt_pct(v):
    if pd.isna(v) or v is None: return "—"
    return f"{v:.2f}%"

def _fmt_pct1(v):
    if pd.isna(v) or v is None: return "—"
    return f"{v:.1f}%"

# Build display rows (URL rows + TOTAL row)
def render_cell(value, formatter):
    return f"<td class='num'>{formatter(value)}</td>"

rows_html = []
for _, r in df.iterrows():
    rows_html.append(
        "<tr>"
        f"<td class='url'>{r['URL']}</td>"
        f"<td class='num'>{_fmt_float1(r['Position'])}</td>"
        f"<td class='num'>{_fmt_int(r['Clicks'])}</td>"
        f"<td class='num'>{_fmt_int(r['Impressions'])}</td>"
        f"<td class='num'>{_fmt_pct(r['CTR %'])}</td>"
        f"<td class='num'>{_fmt_int(r['Organic Traffic'])}</td>"
        f"<td class='num'>{_fmt_int(r['Organic Users'])}</td>"
        f"<td class='num'>{_fmt_int(r['Views'])}</td>"
        f"<td class='num'>{_fmt_int(r['Sessions'])}</td>"
        f"<td class='num'>{_fmt_int(r['Users'])}</td>"
        f"<td class='num'>{_fmt_pct1(r['Bounce %'])}</td>"
        "</tr>"
    )

# TOTAL row — only for columns the user requested
total_row_html = ""
if len(df) > 0:
    total_row_html = (
        "<tr class='total-row'>"
        f"<td class='url'>TOTAL · {len(df)} URLs</td>"
        "<td class='num'>—</td>"
        f"<td class='num'>{int(df['Clicks'].sum()):,}</td>"
        f"<td class='num'>{int(df['Impressions'].sum()):,}</td>"
        "<td class='num'>—</td>"
        f"<td class='num'>{int(df['Organic Traffic'].sum()):,}</td>"
        f"<td class='num'>{int(df['Organic Users'].sum()):,}</td>"
        f"<td class='num'>{int(df['Views'].sum()):,}</td>"
        f"<td class='num'>{int(df['Sessions'].sum()):,}</td>"
        f"<td class='num'>{int(df['Users'].sum()):,}</td>"
        "<td class='num'>—</td>"
        "</tr>"
    )

table_html = f"""
<style>
  .seo-table-wrap {{
    max-height: 560px;
    overflow-y: auto;
    border: 1px solid #EDEDED;
    border-radius: 10px;
    background: white;
    position: relative;
  }}
  table.seo-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.875rem;
    color: #1E1F21;
  }}
  table.seo-table thead th {{
    background: #FAFAFB;
    color: #1E1F21;
    font-weight: 700;
    font-size: 0.75rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    padding: 0.75rem 0.75rem;
    text-align: right;
    border-bottom: 1px solid #D8D9DC;
    position: sticky;
    top: 0;
    z-index: 5;
    white-space: nowrap;
  }}
  table.seo-table thead th:first-child {{ text-align: left; }}
  table.seo-table tbody td {{
    padding: 0.55rem 0.75rem;
    border-bottom: 1px solid #F4F5F6;
    white-space: nowrap;
  }}
  table.seo-table tbody td.url {{ text-align: left; color: #1E1F21; }}
  table.seo-table tbody td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  table.seo-table tbody tr:hover td {{ background: #FAFAFB; }}
  /* Sticky TOTAL row pinned to the bottom of the scroll viewport */
  table.seo-table tbody tr.total-row td {{
    position: sticky;
    bottom: 0;
    background: #F0F1F3 !important;
    font-weight: 700;
    border-top: 2px solid #D8D9DC;
    border-bottom: none;
    z-index: 4;
    color: #1E1F21;
  }}
</style>

<div class="seo-table-wrap">
  <table class="seo-table">
    <thead>
      <tr>
        <th>URL</th>
        <th>Position</th>
        <th>Clicks</th>
        <th>Impressions</th>
        <th>CTR %</th>
        <th>Organic Traffic</th>
        <th>Organic Users</th>
        <th>Views</th>
        <th>Sessions</th>
        <th>Users</th>
        <th>Bounce %</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html)}
      {total_row_html}
    </tbody>
  </table>
</div>
"""
st.markdown(table_html, unsafe_allow_html=True)

# Action row
act1, act2, _ = st.columns([1, 1, 6])
with act1:
    csv = df.to_csv(index=False).encode()
    st.download_button("⬇ Export CSV", csv, file_name=f"klenty-seo-{start}-to-{end}.csv", mime="text/csv", use_container_width=True)
with act2:
    if st.button("📋 Generate Summary", use_container_width=True, type="primary"):
        st.session_state["show_summary"] = True


# ---------------- Summary section ----------------
def pct(curr, prev):
    if prev in (0, None) or curr is None:
        return None
    return (curr - prev) / prev * 100


def fmt_pct(p):
    if p is None:
        return "—"
    arrow = "▲" if p > 0 else ("▼" if p < 0 else "•")
    return f"{arrow} {abs(p):.1f}%"


def diagnose(url: str, m: dict, prior: dict) -> list[dict]:
    """Return a list of {severity, label, fix} issues for this URL."""
    issues = []
    pos = m.get("position")
    clicks = m.get("clicks", 0)
    impr = m.get("impressions", 0)
    ctr = m.get("ctr", 0)
    organic = m.get("organic", 0)
    sessions = m.get("sessions", 0)
    bounce = m.get("bounce", 0)
    prev_clicks = prior.get("clicks", 0) if prior else 0
    prev_pos = prior.get("position") if prior else None

    # Indexing / not ranking
    if (pos is None or pos == 0) and impr == 0 and clicks == 0:
        issues.append({
            "severity": "high",
            "label": "Not ranking / not indexed",
            "fix": "Page shows 0 impressions — likely not indexed or not relevant for any tracked query. Check GSC URL Inspection, confirm it's in sitemap.xml, request indexing, audit internal links pointing to it.",
        })
        return issues

    # Top-position low CTR
    if pos and pos < 10 and impr >= 200 and ctr < 2.0:
        issues.append({
            "severity": "high",
            "label": f"Low CTR at pos {pos:.1f}",
            "fix": f"Ranking on page 1 ({pos:.1f}) with {impr:,} impressions but only {ctr:.2f}% CTR. Rewrite the meta title to lead with the keyword + a benefit/number/year. Tighten the meta description to 150 chars with a clear hook. Aim for 3–5% CTR.",
        })

    # Striking distance (pos 11-20)
    if pos and 10 <= pos <= 20 and impr >= 500:
        issues.append({
            "severity": "medium",
            "label": f"Striking distance (pos {pos:.1f})",
            "fix": f"Pos {pos:.1f} with {impr:,} impressions — high-leverage URL. Push to page 1 with: a stronger H1 matching exact query, FAQ schema, expand content to cover related sub-queries, build 3–5 contextual internal links from authority pages, refresh publish date.",
        })

    # Mid-page (21-50)
    if pos and 20 < pos <= 50:
        issues.append({
            "severity": "medium",
            "label": f"Mid-page ranking (pos {pos:.1f})",
            "fix": f"Pos {pos:.1f} — content depth / freshness gap. Refresh with 2026 data, add primary source quotes, target the exact head term in H1 + URL slug, strengthen E-E-A-T (author bio, sources, dates). Add an FAQ block targeting PAA questions.",
        })

    # Deep (50+)
    if pos and pos > 50 and impr >= 200:
        issues.append({
            "severity": "low",
            "label": f"Far from page 1 (pos {pos:.1f})",
            "fix": f"Pos {pos:.1f} — likely topical authority gap. Decide: (a) invest heavily in this URL with backlinks + deeper content, or (b) redirect/merge into a stronger sibling page covering the same intent.",
        })

    # Position decline
    if pos and prev_pos and prev_pos < pos - 3:
        issues.append({
            "severity": "high",
            "label": f"Position dropped {prev_pos:.1f} → {pos:.1f}",
            "fix": f"Dropped {pos - prev_pos:.1f} positions vs prior period. Check: (1) any recent edits that thinned content, (2) lost backlinks (run Ahrefs/Semrush), (3) new competitor URLs in SERP — open the query and study top 3 results, (4) Google algorithm update overlap.",
        })

    # Position improvement worth noting
    if pos and prev_pos and prev_pos > pos + 3:
        issues.append({
            "severity": "info",
            "label": f"Position improved {prev_pos:.1f} → {pos:.1f}",
            "fix": f"Gained {prev_pos - pos:.1f} positions — momentum. Reinforce: add 3 more internal links from related pages, share on LinkedIn for engagement signal, monitor whether to push for featured snippet (add 40–60 word direct answer near the top).",
        })

    # Click decline
    if prev_clicks >= 5 and clicks < prev_clicks * 0.6:
        issues.append({
            "severity": "high",
            "label": f"Clicks dropped {prev_clicks} → {clicks}",
            "fix": f"Clicks fell {((clicks - prev_clicks) / prev_clicks * 100):.0f}% vs prior. Cross-reference position change and impression change above. If position held but clicks dropped → SERP feature stole traffic (AI Overview, ad, snippet). If impressions dropped → query demand changed or you lost rankings on long-tail.",
        })

    # GSC clicks but no GA4 sessions = tracking issue
    if clicks >= 5 and sessions == 0:
        issues.append({
            "severity": "high",
            "label": "Tracking gap (GSC clicks, GA4 0 sessions)",
            "fix": f"{clicks} clicks in GSC but GA4 shows 0 sessions. Likely causes: redirect chain stripping the GA4 tag, GTM not firing, recent template change, or the URL has changed path. Open the page in incognito and verify GA4 debug view picks it up.",
        })

    # High bounce
    if sessions >= 10 and bounce >= 80:
        issues.append({
            "severity": "medium",
            "label": f"High bounce rate ({bounce:.0f}%)",
            "fix": f"{bounce:.0f}% bounce with {sessions} sessions — content/intent mismatch. Read first 200 words: does it answer the search query in the first paragraph? Add a TL;DR box at the top. Strengthen above-fold CTAs (e.g. interactive demo link). Check page speed.",
        })

    # Organic share too low
    if sessions >= 20 and organic == 0:
        issues.append({
            "severity": "medium",
            "label": "Zero organic share",
            "fix": f"{sessions} sessions but 0 from Organic Search channel. Either (1) traffic comes from paid/direct/referral only — fine if intentional, or (2) GA4 channel grouping config strips organic referrers. Check Admin → Channel groups in GA4.",
        })

    return issues


SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


if st.session_state.get("show_summary"):
    with st.spinner("Generating summary..."):
        prior_metrics = fetch_metrics(tuple(all_urls), p_start, p_end)
        daily = fetch_daily(start, end) if days >= 2 else []

    # ---- Per-URL movers + diagnosis ----
    movers = []
    diagnoses = {}
    for u in all_urls:
        m = metrics[u]
        pm = prior_metrics.get(u, {})
        curr_c = m["clicks"]
        prev_c = pm.get("clicks", 0)
        movers.append({
            "url": u,
            "clicks": curr_c,
            "prev_clicks": prev_c,
            "delta": curr_c - prev_c,
            "delta_pct": pct(curr_c, prev_c),
            "position": m["position"],
            "prev_position": pm.get("position"),
            "impressions": m["impressions"],
            "ctr": m["ctr"],
            "organic": m["organic"],
            "sessions": m["sessions"],
            "users": m["users"],
            "bounce": m["bounce"],
        })
        diagnoses[u] = diagnose(u, m, pm)

    top5 = sorted(movers, key=lambda x: x["clicks"], reverse=True)[:5]
    gainers = sorted([m for m in movers if m["delta"] > 0], key=lambda x: x["delta"], reverse=True)[:5]
    losers = sorted([m for m in movers if m["delta"] < 0], key=lambda x: x["delta"])[:5]
    pos_movers_up = sorted(
        [m for m in movers if m["position"] and m["prev_position"] and m["prev_position"] > m["position"] + 1],
        key=lambda x: x["prev_position"] - x["position"], reverse=True,
    )[:5]
    pos_movers_down = sorted(
        [m for m in movers if m["position"] and m["prev_position"] and m["position"] > m["prev_position"] + 1],
        key=lambda x: x["position"] - x["prev_position"], reverse=True,
    )[:5]
    zero_traffic = [m for m in movers if m["clicks"] == 0 and m["organic"] == 0]
    striking = [m for m in movers if m["position"] and 10 <= m["position"] <= 20 and m["impressions"] >= 500]
    low_ctr_top = [m for m in movers if m["position"] and m["position"] < 10 and m["ctr"] < 2.0 and m["impressions"] >= 200]

    # ---- Aggregate fixes across all URLs ----
    fix_groups: dict[str, list[str]] = {}
    for u, issues in diagnoses.items():
        for iss in issues:
            fix_groups.setdefault(iss["label"], []).append(u)

    fix_groups_sorted = sorted(
        fix_groups.items(),
        key=lambda kv: (
            SEVERITY_ORDER.get(next((i["severity"] for i in diagnoses[kv[1][0]] if i["label"] == kv[0]), "low"), 9),
            -len(kv[1]),
        ),
    )

    # ---- Daily highlights ----
    best_day = worst_day = None
    if daily:
        clicks_days = [d for d in daily if d.get("clicks", 0) > 0]
        if clicks_days:
            best_day = max(clicks_days, key=lambda d: d.get("clicks", 0))
            worst_day = min(clicks_days, key=lambda d: d.get("clicks", 0))

    # ---- Build markdown ----
    L = []
    L.append(f"# Klenty SEO Summary")
    L.append(f"_Period: **{start} → {end}** ({days} day{'s' if days != 1 else ''}) · compared to prior {days}d ({p_start} → {p_end})_")
    L.append("")

    # TL;DR
    L.append("## TL;DR")
    tldr_bits = []
    cp = pct(g["clicks"], pg["clicks"])
    if cp is not None:
        verb = "up" if cp > 0 else "down"
        tldr_bits.append(f"Total clicks **{verb} {abs(cp):.1f}%** ({g['clicks']:,} vs {pg['clicks']:,})")
    posp = pct(g["position"], pg["position"])
    if posp is not None:
        # Position: lower is better, so up % is bad
        verb = "worsened" if posp > 0 else "improved"
        tldr_bits.append(f"avg position **{verb}** ({pg['position']:.1f} → {g['position']:.1f})")
    up = pct(a["users"], pa["users"])
    if up is not None:
        verb = "up" if up > 0 else "down"
        tldr_bits.append(f"users **{verb} {abs(up):.1f}%** ({a['users']:,})")
    L.append("- " + ". ".join(tldr_bits).capitalize() + ".")
    L.append(f"- **{len([m for m in movers if m['clicks'] > 0])}** of {len(all_urls)} tracked URLs got clicks. **{len(zero_traffic)}** got zero traffic this period.")
    if fix_groups:
        L.append(f"- **{len(fix_groups)} fix categories** flagged across **{sum(len(v) for v in fix_groups.values())} URL-issues**. Top priorities below.")
    L.append("")

    # Overall performance
    L.append("## Overall performance")
    L.append(f"| Metric | This period | Prior period | Change |")
    L.append(f"|---|---|---|---|")
    L.append(f"| Clicks | {g['clicks']:,} | {pg['clicks']:,} | {fmt_pct(pct(g['clicks'], pg['clicks']))} |")
    L.append(f"| Impressions | {g['impressions']:,} | {pg['impressions']:,} | {fmt_pct(pct(g['impressions'], pg['impressions']))} |")
    L.append(f"| CTR | {g['ctr']:.2f}% | {pg['ctr']:.2f}% | {fmt_pct(pct(g['ctr'], pg['ctr']))} |")
    L.append(f"| Avg Position | {g['position']:.1f} | {pg['position']:.1f} | {fmt_pct(pct(g['position'], pg['position']))} *(lower=better)* |")
    L.append(f"| Users | {a['users']:,} | {pa['users']:,} | {fmt_pct(pct(a['users'], pa['users']))} |")
    L.append(f"| Sessions | {a['sessions']:,} | {pa['sessions']:,} | {fmt_pct(pct(a['sessions'], pa['sessions']))} |")
    L.append(f"| Bounce rate | {a['bounce']:.1f}% | {pa['bounce']:.1f}% | {fmt_pct(pct(a['bounce'], pa['bounce']))} |")
    L.append("")

    if best_day or worst_day:
        L.append("## Period highlights")
        if best_day:
            L.append(f"- 🟢 **Best day:** {best_day['date']} — {best_day.get('clicks', 0):,} clicks, {best_day.get('sessions', 0):,} sessions, {best_day.get('users', 0):,} users")
        if worst_day:
            L.append(f"- 🔴 **Worst day:** {worst_day['date']} — {worst_day.get('clicks', 0):,} clicks")
        L.append("")

    # What's working
    L.append("## What's working")
    L.append("**Top 5 pages by clicks:**")
    for i, m in enumerate(top5, 1):
        pos_str = f"pos {m['position']:.1f}" if m["position"] else "no rank"
        L.append(f"{i}. `{m['url']}` — **{m['clicks']:,} clicks**, {m['organic']:,} organic sessions, {pos_str}, CTR {m['ctr']:.2f}%")
    L.append("")
    if gainers:
        L.append("**Biggest click gainers vs prior period:**")
        for m in gainers:
            L.append(f"- `{m['url']}` — **+{m['delta']:,} clicks** ({m['prev_clicks']:,} → {m['clicks']:,}, {fmt_pct(m['delta_pct'])})")
        L.append("")
    if pos_movers_up:
        L.append("**Biggest position improvements:**")
        for m in pos_movers_up:
            L.append(f"- `{m['url']}` — pos {m['prev_position']:.1f} → **{m['position']:.1f}** ({m['prev_position'] - m['position']:.1f} positions gained)")
        L.append("")

    # What's broken
    L.append("## What's broken / declining")
    if losers:
        L.append("**Biggest click losers:**")
        for m in losers:
            L.append(f"- `{m['url']}` — **{m['delta']:,} clicks** ({m['prev_clicks']:,} → {m['clicks']:,}, {fmt_pct(m['delta_pct'])})")
        L.append("")
    if pos_movers_down:
        L.append("**Biggest position drops:**")
        for m in pos_movers_down:
            L.append(f"- `{m['url']}` — pos {m['prev_position']:.1f} → **{m['position']:.1f}** ({m['position'] - m['prev_position']:.1f} positions lost)")
        L.append("")
    if zero_traffic:
        L.append(f"**Zero-traffic pages ({len(zero_traffic)}):**")
        for m in zero_traffic[:15]:
            L.append(f"- `{m['url']}`")
        if len(zero_traffic) > 15:
            L.append(f"- _…and {len(zero_traffic) - 15} more_")
        L.append("")

    # Quick wins
    L.append("## Quick wins")
    if striking:
        L.append(f"**Striking distance ({len(striking)} URLs on positions 10–20 with ≥500 impressions):**")
        for m in sorted(striking, key=lambda x: -x["impressions"])[:8]:
            L.append(f"- `{m['url']}` — pos {m['position']:.1f}, {m['impressions']:,} impressions, {m['clicks']} clicks. Push to page 1 with on-page work.")
        L.append("")
    if low_ctr_top:
        L.append(f"**Low CTR at top positions ({len(low_ctr_top)} URLs in top 10 with <2% CTR):**")
        for m in sorted(low_ctr_top, key=lambda x: -x["impressions"])[:8]:
            L.append(f"- `{m['url']}` — pos {m['position']:.1f}, CTR {m['ctr']:.2f}%, {m['impressions']:,} impressions. Title/meta rewrite.")
        L.append("")
    if not striking and not low_ctr_top:
        L.append("_No striking-distance or low-CTR opportunities detected in tracked URLs._")
        L.append("")

    # Recommended fixes — grouped action list
    L.append("## Recommended fixes (grouped)")
    if not fix_groups_sorted:
        L.append("_All tracked URLs are clean — no flagged issues._")
    else:
        for label, urls in fix_groups_sorted[:10]:
            # Pull the fix text from the first URL's diagnosis
            sample = next(i for i in diagnoses[urls[0]] if i["label"] == label)
            sev_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢", "info": "🔵"}[sample["severity"]]
            L.append(f"### {sev_emoji} {label} — {len(urls)} URL{'s' if len(urls) != 1 else ''}")
            L.append(f"_{sample['fix']}_")
            L.append("")
            L.append("**Affected URLs:**")
            for u in urls[:10]:
                L.append(f"- `{u}`")
            if len(urls) > 10:
                L.append(f"- _…and {len(urls) - 10} more_")
            L.append("")

    summary_md = "\n".join(L)

    # ---- Render ----
    st.markdown('<div class="section-title">Generated Summary</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(summary_md)

    # Per-URL deep dive (collapsible)
    deep_dive_md = ["", "## Per-URL deep dive", ""]
    with st.expander(f"📂 Per-URL deep dive ({len(all_urls)} URLs)", expanded=False):
        for u in all_urls:
            m = metrics[u]; pm = prior_metrics.get(u, {})
            issues = diagnoses[u]
            pos_str = f"{m['position']:.1f}" if m["position"] else "—"
            prev_pos_str = f"{pm.get('position'):.1f}" if pm.get("position") else "—"
            header = f"**`{u}`**"
            st.markdown(header)
            cols = st.columns(6)
            cols[0].metric("Position", pos_str, f"{(m['position'] - pm.get('position')):.1f}" if m["position"] and pm.get("position") else None, delta_color="inverse")
            cols[1].metric("Clicks", f"{m['clicks']:,}", f"{m['clicks'] - pm.get('clicks', 0):+,}" if pm else None)
            cols[2].metric("Impressions", f"{m['impressions']:,}")
            cols[3].metric("CTR", f"{m['ctr']:.2f}%")
            cols[4].metric("Organic", f"{m['organic']:,}")
            cols[5].metric("Bounce", f"{m['bounce']:.1f}%")
            if issues:
                for iss in sorted(issues, key=lambda x: SEVERITY_ORDER.get(x["severity"], 9)):
                    sev_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢", "info": "🔵"}[iss["severity"]]
                    st.markdown(f"{sev_emoji} **{iss['label']}** — {iss['fix']}")
            else:
                st.markdown("✅ _No issues flagged._")
            st.markdown("---")

            # Append to markdown export
            deep_dive_md.append(f"### {u}")
            deep_dive_md.append(f"- Position: {pos_str} (prior {prev_pos_str})")
            deep_dive_md.append(f"- Clicks: {m['clicks']:,} | Impressions: {m['impressions']:,} | CTR: {m['ctr']:.2f}%")
            deep_dive_md.append(f"- Organic: {m['organic']:,} | Sessions: {m['sessions']:,} | Users: {m['users']:,} | Bounce: {m['bounce']:.1f}%")
            if issues:
                for iss in sorted(issues, key=lambda x: SEVERITY_ORDER.get(x["severity"], 9)):
                    deep_dive_md.append(f"  - **{iss['label']}** ({iss['severity']}): {iss['fix']}")
            else:
                deep_dive_md.append("  - No issues flagged.")
            deep_dive_md.append("")

    # Daily breakdown
    daily_md_lines = []
    if days >= 2 and daily:
        st.markdown('<div class="section-title">Daily breakdown</div>', unsafe_allow_html=True)
        ddf = pd.DataFrame(daily)
        for col in ["clicks", "impressions", "sessions", "users", "views"]:
            if col not in ddf:
                ddf[col] = 0
        if "ctr" in ddf:
            ddf["ctr"] = ddf["ctr"].round(2)
        if "position" in ddf:
            ddf["position"] = ddf["position"].round(1)
        ddf = ddf[["date", "clicks", "impressions", "ctr", "position", "sessions", "users", "views"]]
        ddf.columns = ["Date", "Clicks", "Impressions", "CTR %", "Position", "Sessions", "Users", "Views"]

        st.dataframe(
            ddf, use_container_width=True, hide_index=True,
            column_config={
                "Clicks": st.column_config.NumberColumn(format="%d"),
                "Impressions": st.column_config.NumberColumn(format="%d"),
                "CTR %": st.column_config.NumberColumn(format="%.2f%%"),
                "Position": st.column_config.NumberColumn(format="%.1f"),
                "Sessions": st.column_config.NumberColumn(format="%d"),
                "Users": st.column_config.NumberColumn(format="%d"),
                "Views": st.column_config.NumberColumn(format="%d"),
            },
            height=min(500, 60 + 35 * len(ddf)),
        )
        daily_md_lines = ["", "## Daily breakdown", "", "| Date | Clicks | Impressions | CTR | Position | Sessions | Users | Views |", "|---|---|---|---|---|---|---|---|"]
        for _, row in ddf.iterrows():
            daily_md_lines.append(f"| {row['Date']} | {row['Clicks']:,} | {row['Impressions']:,} | {row['CTR %']}% | {row['Position']} | {row['Sessions']:,} | {row['Users']:,} | {row['Views']:,} |")
    elif days < 2:
        st.info("Pick a range of 7d or more to see a daily breakdown.")

    # Compose full markdown for download (summary + daily + deep dive)
    full_md = summary_md + "\n" + "\n".join(daily_md_lines) + "\n" + "\n".join(deep_dive_md)

    dl1, dl2, _ = st.columns([1, 1, 6])
    with dl1:
        st.download_button(
            "⬇ Download .md",
            full_md.encode(),
            file_name=f"klenty-seo-summary-{start}-to-{end}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with dl2:
        if st.button("Hide summary", type="secondary", use_container_width=True):
            st.session_state["show_summary"] = False
            st.rerun()

# ---------------- URL Trend Inspector ----------------
st.markdown('<div class="section-title">URL Trend Inspector</div>', unsafe_allow_html=True)

ti1, ti2 = st.columns([2, 3])
with ti1:
    picked = st.selectbox(
        "Pick a tracked URL",
        options=["— or paste a URL below —"] + all_urls,
        key="trend_picker",
    )
with ti2:
    custom_path = st.text_input(
        "Or paste any klenty.com URL",
        placeholder="/blog/your-page/ or https://www.klenty.com/blog/...",
        key="trend_custom",
    )

# Resolve target URL — custom input wins if provided
target = None
if custom_path.strip():
    path = custom_path.strip()
    if path.startswith("http"):
        from urllib.parse import urlparse
        path = urlparse(path).path
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/"):
        path = path + "/"
    target = path
elif picked != "— or paste a URL below —":
    target = picked

if days < 2:
    st.info("Pick a range of 7d or more to see a daily trend.")
elif target:
    with st.spinner(f"Loading trend for {target}..."):
        trend = fetch_trend(target, start, end)

    if not trend:
        st.warning(f"No trend data available for `{target}` in this range. Check the URL or try a wider range.")
    else:
        tdf = pd.DataFrame(trend)

        # Toggle: Position vs Traffic
        metric_choice = st.radio(
            "Metric",
            ["📈 Position", "🚦 Traffic"],
            horizontal=True,
            label_visibility="collapsed",
            key="trend_metric",
        )

        # ---- Trend direction helper ----
        def trend_summary(series, lower_is_better=False):
            vals = [v for v in series if v is not None and not pd.isna(v) and v > 0]
            if len(vals) < 2:
                return None, None, None
            half = max(1, len(vals) // 2)
            first_avg = sum(vals[:half]) / half
            second_avg = sum(vals[-half:]) / half
            if first_avg == 0:
                return None, None, None
            change_pct = (second_avg - first_avg) / first_avg * 100
            if lower_is_better:
                improving = change_pct < 0
            else:
                improving = change_pct > 0
            return first_avg, second_avg, (change_pct, improving)

        if metric_choice == "📈 Position":
            if "position" not in tdf or tdf["position"].dropna().empty:
                st.info("No position data for this URL in this range.")
            else:
                first, second, ch = trend_summary(tdf["position"].tolist(), lower_is_better=True)
                if ch is not None:
                    change_pct, improving = ch
                    if improving:
                        verdict = f"<span style='color:#14A37F; font-weight:700;'>▲ Improving</span>"
                        explain = "Position is moving up in search results (lower number = better)."
                    elif abs(change_pct) < 1:
                        verdict = f"<span style='color:#6F7782; font-weight:700;'>● Stable</span>"
                        explain = "Position is holding steady."
                    else:
                        verdict = f"<span style='color:#E8384F; font-weight:700;'>▼ Declining</span>"
                        explain = "Position is dropping in search results (higher number = worse)."
                    st.markdown(
                        f"<div style='background:white; border:1px solid #EDEDED; border-radius:10px; padding:1rem 1.25rem; margin-bottom:0.75rem;'>"
                        f"<div style='font-size:0.7rem; color:#6F7782; text-transform:uppercase; letter-spacing:0.05em;'>Position trend for <code>{target}</code></div>"
                        f"<div style='font-size:1.5rem; margin-top:0.3rem;'>{verdict} &nbsp; <span style='color:#1E1F21;'>{first:.1f} → {second:.1f}</span></div>"
                        f"<div style='color:#6F7782; font-size:0.85rem; margin-top:0.3rem;'>{explain}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=tdf["date"], y=tdf["position"], name="Position",
                    mode="lines+markers",
                    line=dict(color="#14A37F", width=3),
                    marker=dict(size=8, color="#14A37F"),
                    fill="tozeroy",
                    fillcolor="rgba(20, 163, 127, 0.05)",
                ))
                fig.update_layout(
                    height=380, margin=dict(l=20, r=20, t=20, b=20),
                    plot_bgcolor="white", paper_bgcolor="white",
                    yaxis=dict(title="Position (lower = better)", autorange="reversed", gridcolor="#EDEDED", zeroline=False),
                    xaxis=dict(showgrid=False),
                )
                st.plotly_chart(fig, use_container_width=True)

        else:  # Traffic
            # Use sessions as the primary traffic metric, with users as overlay
            if "sessions" not in tdf or tdf["sessions"].dropna().empty:
                st.info("No GA4 traffic data for this URL in this range.")
            else:
                first, second, ch = trend_summary(tdf["sessions"].tolist(), lower_is_better=False)
                if ch is not None:
                    change_pct, improving = ch
                    if improving and change_pct > 5:
                        verdict = f"<span style='color:#14A37F; font-weight:700;'>▲ Growing</span>"
                        explain = f"Traffic up {abs(change_pct):.1f}% comparing the back half of the period to the front half."
                    elif abs(change_pct) < 5:
                        verdict = f"<span style='color:#6F7782; font-weight:700;'>● Stable</span>"
                        explain = "Traffic is holding within ±5%."
                    else:
                        verdict = f"<span style='color:#E8384F; font-weight:700;'>▼ Declining</span>"
                        explain = f"Traffic down {abs(change_pct):.1f}% comparing the back half of the period to the front half."
                    st.markdown(
                        f"<div style='background:white; border:1px solid #EDEDED; border-radius:10px; padding:1rem 1.25rem; margin-bottom:0.75rem;'>"
                        f"<div style='font-size:0.7rem; color:#6F7782; text-transform:uppercase; letter-spacing:0.05em;'>Traffic trend for <code>{target}</code></div>"
                        f"<div style='font-size:1.5rem; margin-top:0.3rem;'>{verdict} &nbsp; <span style='color:#1E1F21;'>{first:.0f} → {second:.0f} sessions/day avg</span></div>"
                        f"<div style='color:#6F7782; font-size:0.85rem; margin-top:0.3rem;'>{explain}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=tdf["date"], y=tdf["sessions"], name="Sessions",
                    mode="lines+markers",
                    line=dict(color="#F06A6A", width=3),
                    marker=dict(size=8, color="#F06A6A"),
                    fill="tozeroy",
                    fillcolor="rgba(240, 106, 106, 0.08)",
                ))
                if "users" in tdf:
                    fig.add_trace(go.Scatter(
                        x=tdf["date"], y=tdf["users"], name="Users",
                        mode="lines+markers",
                        line=dict(color="#4573D2", width=2, dash="dot"),
                        marker=dict(size=6),
                    ))
                fig.update_layout(
                    height=380, margin=dict(l=20, r=20, t=20, b=20),
                    plot_bgcolor="white", paper_bgcolor="white",
                    yaxis=dict(title="Traffic per day", gridcolor="#EDEDED"),
                    xaxis=dict(showgrid=False),
                    legend=dict(orientation="h", y=-0.15),
                )
                st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Pick a tracked URL above or paste any klenty.com URL to see its trend.")

st.markdown(
    '<div class="footnote">Data pulled live from Google Search Console + Google Analytics 4 · '
    'cached for 15 min · GSC has a ~2-day lag</div>',
    unsafe_allow_html=True,
)
