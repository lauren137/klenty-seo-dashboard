"""GSC + GA4 API clients. Loads OAuth from Streamlit secrets in prod, local files in dev."""
import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from typing import Optional
from urllib.parse import urlparse

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest, DateRange, Metric, Dimension,
    Filter, FilterExpression, FilterExpressionList,
)
from googleapiclient.discovery import build

# Local dev paths (only used if no Streamlit secrets are present)
LOCAL_MCP_DIR = "/Users/lauren/Desktop/ga4-gsc-mcp-server"
LOCAL_TOKEN_FILE = os.path.join(LOCAL_MCP_DIR, "token.json")

# Config — overridable via Streamlit secrets / env vars
GA4_PROPERTY_ID = os.environ.get("GA4_PROPERTY_ID", "264568011")
GSC_SITE_URL = os.environ.get("GSC_SITE_URL", "sc-domain:klenty.com")
SITE_DOMAIN = os.environ.get("SITE_DOMAIN", "https://www.klenty.com")

SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
]

# Klenty sitemap URLs — root + child files
SITEMAP_URLS = [
    "https://www.klenty.com/sitemap.xml",
    "https://www.klenty.com/blog/post-sitemap1.xml",
    "https://www.klenty.com/blog/post-sitemap2.xml",
    "https://www.klenty.com/blog/post-sitemap3.xml",
    "https://www.klenty.com/blog/page-sitemap.xml",
]

SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _fetch_xml(url: str) -> Optional[bytes]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "klenty-seo-dashboard/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
        return None


def fetch_sitemap_urls() -> list[str]:
    """Parse all Klenty sitemaps and return a deduped list of paths (with trailing slash)."""
    paths: set[str] = set()
    queue = list(SITEMAP_URLS)
    seen_sitemaps: set[str] = set()

    while queue:
        sm_url = queue.pop(0)
        if sm_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sm_url)

        xml_data = _fetch_xml(sm_url)
        if not xml_data:
            continue
        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError as e:
            print(f"Parse error for {sm_url}: {e}")
            continue

        # URL entries in this sitemap
        for loc in root.findall(".//sm:url/sm:loc", SITEMAP_NS):
            if loc.text:
                path = urlparse(loc.text.strip()).path or "/"
                if not path.endswith("/"):
                    path += "/"
                paths.add(path)

        # Nested sitemap entries (sitemap index)
        for loc in root.findall(".//sm:sitemap/sm:loc", SITEMAP_NS):
            if loc.text:
                child = loc.text.strip()
                if child not in seen_sitemaps:
                    queue.append(child)

    return sorted(paths)


def _load_token_dict() -> dict | None:
    """Try Streamlit secrets first, fall back to local token.json."""
    # 1. Streamlit Cloud secrets
    try:
        import streamlit as st
        if "google_oauth" in st.secrets:
            cfg = st.secrets["google_oauth"]
            return {
                "token": cfg.get("token", ""),
                "refresh_token": cfg["refresh_token"],
                "token_uri": cfg.get("token_uri", "https://oauth2.googleapis.com/token"),
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "scopes": SCOPES,
            }
    except Exception:
        pass
    # 2. Env vars (e.g. when running on Render/Railway)
    if os.environ.get("GOOGLE_REFRESH_TOKEN"):
        return {
            "token": "",
            "refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"],
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "scopes": SCOPES,
        }
    # 3. Local file (dev mode)
    if os.path.exists(LOCAL_TOKEN_FILE):
        with open(LOCAL_TOKEN_FILE) as f:
            return json.load(f)
    return None


def get_credentials() -> Credentials:
    token_data = _load_token_dict()
    if not token_data:
        raise RuntimeError(
            "No OAuth credentials found. Set Streamlit secrets [google_oauth] or "
            "place token.json at " + LOCAL_TOKEN_FILE
        )
    creds = Credentials.from_authorized_user_info(token_data, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # If we loaded from a local file, persist the refreshed token
            if os.path.exists(LOCAL_TOKEN_FILE):
                try:
                    with open(LOCAL_TOKEN_FILE, "w") as f:
                        f.write(creds.to_json())
                except OSError:
                    pass  # Read-only FS on cloud — fine, token refreshes in-memory
    return creds


def date_range(days: int) -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def prior_range(days: int) -> tuple[str, str]:
    end = date.today() - timedelta(days=days)
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


# ---------- GSC ----------

def gsc_page_metrics(
    pages: list[str],
    start: str,
    end: str,
) -> dict[str, dict]:
    """Pull per-URL clicks/impressions/ctr/position from GSC.

    Returns {page_path: {clicks, impressions, ctr, position}}.
    """
    svc = build("searchconsole", "v1", credentials=get_credentials(), cache_discovery=False)
    full_urls = {p: f"{SITE_DOMAIN}{p}" for p in pages}

    # Single query, dimension=page, filter to our URLs
    body = {
        "startDate": start,
        "endDate": end,
        "dimensions": ["page"],
        "rowLimit": 25000,
        "dimensionFilterGroups": [{
            "filters": [{
                "dimension": "page",
                "operator": "includingRegex",
                "expression": "|".join(p.replace("/", r"\/") for p in pages),
            }]
        }],
    }
    try:
        resp = svc.searchanalytics().query(siteUrl=GSC_SITE_URL, body=body).execute()
    except Exception:
        # Fallback: pull top 25000 pages and match locally
        resp = svc.searchanalytics().query(siteUrl=GSC_SITE_URL, body={
            "startDate": start, "endDate": end,
            "dimensions": ["page"], "rowLimit": 25000,
        }).execute()

    by_page = {}
    for row in resp.get("rows", []):
        url = row["keys"][0]
        for path, full in full_urls.items():
            if url == full or url.rstrip("/") == full.rstrip("/"):
                by_page[path] = {
                    "clicks": int(row.get("clicks", 0)),
                    "impressions": int(row.get("impressions", 0)),
                    "ctr": float(row.get("ctr", 0)) * 100,
                    "position": float(row.get("position", 0)),
                }
                break

    for p in pages:
        if p not in by_page:
            by_page[p] = {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": None}
    return by_page


def gsc_overview_daily(start: str, end: str) -> list[dict]:
    """Daily site-wide GSC totals."""
    svc = build("searchconsole", "v1", credentials=get_credentials(), cache_discovery=False)
    resp = svc.searchanalytics().query(
        siteUrl=GSC_SITE_URL,
        body={"startDate": start, "endDate": end, "dimensions": ["date"], "rowLimit": 1000},
    ).execute()
    return [{
        "date": r["keys"][0],
        "clicks": int(r.get("clicks", 0)),
        "impressions": int(r.get("impressions", 0)),
        "ctr": float(r.get("ctr", 0)) * 100,
        "position": float(r.get("position", 0)),
    } for r in resp.get("rows", [])]


def ga4_overview_daily(start: str, end: str) -> list[dict]:
    """Daily site-wide GA4 totals."""
    client = _ga4_client()
    req = RunReportRequest(
        property=f"properties/{GA4_PROPERTY_ID}",
        date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name="date")],
        metrics=[
            Metric(name="sessions"),
            Metric(name="totalUsers"),
            Metric(name="screenPageViews"),
        ],
        limit=1000,
    )
    resp = client.run_report(req)
    out = []
    for row in resp.rows:
        d = row.dimension_values[0].value
        iso = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        out.append({
            "date": iso,
            "sessions": int(float(row.metric_values[0].value)),
            "users": int(float(row.metric_values[1].value)),
            "views": int(float(row.metric_values[2].value)),
        })
    return sorted(out, key=lambda x: x["date"])


def gsc_all_pages(start: str, end: str, limit: int = 500) -> dict[str, dict]:
    """Top N pages site-wide by clicks. Returns {path: {clicks, impressions, ctr, position}}."""
    from urllib.parse import urlparse
    svc = build("searchconsole", "v1", credentials=get_credentials(), cache_discovery=False)
    resp = svc.searchanalytics().query(siteUrl=GSC_SITE_URL, body={
        "startDate": start, "endDate": end,
        "dimensions": ["page"], "rowLimit": limit,
        "orderBy": [{"fieldName": "clicks", "sortOrder": "DESCENDING"}],
    }).execute()
    by_page = {}
    for row in resp.get("rows", []):
        full_url = row["keys"][0]
        path = urlparse(full_url).path or "/"
        by_page[path] = {
            "clicks": int(row.get("clicks", 0)),
            "impressions": int(row.get("impressions", 0)),
            "ctr": float(row.get("ctr", 0)) * 100,
            "position": float(row.get("position", 0)),
        }
    return by_page


def ga4_all_pages(start: str, end: str, limit: int = 500) -> dict[str, dict]:
    """Top N pages site-wide by sessions. Returns {path: {views, sessions, users, bounce, organic}}."""
    client = _ga4_client()

    # Fetch a large pool of pages, sort + truncate client-side
    # (avoids SDK version differences around OrderBy class location)
    pool_size = max(limit * 5, 1000)
    req = RunReportRequest(
        property=f"properties/{GA4_PROPERTY_ID}",
        date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name="pagePath")],
        metrics=[
            Metric(name="screenPageViews"),
            Metric(name="sessions"),
            Metric(name="totalUsers"),
            Metric(name="bounceRate"),
        ],
        limit=pool_size,
    )
    resp = client.run_report(req)

    # Collect all rows, sort by sessions DESC, take top `limit`
    rows = []
    for row in resp.rows:
        rows.append((
            row.dimension_values[0].value,
            int(float(row.metric_values[0].value)),  # views
            int(float(row.metric_values[1].value)),  # sessions
            int(float(row.metric_values[2].value)),  # users
            float(row.metric_values[3].value) * 100, # bounce
        ))
    rows.sort(key=lambda r: -r[2])  # sort by sessions desc
    rows = rows[:limit]

    by_page = {}
    for path, views, sessions, users, bounce in rows:
        norm = path if path.endswith("/") else path + "/"
        by_page[norm] = {
            "views": views,
            "sessions": sessions,
            "users": users,
            "bounce": bounce,
            "organic": 0,
        }

    # Organic-only sessions for these pages
    organic_req = RunReportRequest(
        property=f"properties/{GA4_PROPERTY_ID}",
        date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name="pagePath")],
        metrics=[Metric(name="sessions")],
        dimension_filter=FilterExpression(
            filter=Filter(
                field_name="sessionDefaultChannelGroup",
                string_filter=Filter.StringFilter(value="Organic Search"),
            )
        ),
        limit=limit * 2,
    )
    organic_resp = client.run_report(organic_req)
    for row in organic_resp.rows:
        path = row.dimension_values[0].value
        norm = path if path.endswith("/") else path + "/"
        if norm in by_page:
            by_page[norm]["organic"] = int(float(row.metric_values[0].value))
    return by_page


def gsc_overview(start: str, end: str) -> dict:
    svc = build("searchconsole", "v1", credentials=get_credentials(), cache_discovery=False)
    resp = svc.searchanalytics().query(
        siteUrl=GSC_SITE_URL,
        body={"startDate": start, "endDate": end, "dimensions": []},
    ).execute()
    rows = resp.get("rows", [])
    if not rows:
        return {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}
    r = rows[0]
    return {
        "clicks": int(r.get("clicks", 0)),
        "impressions": int(r.get("impressions", 0)),
        "ctr": float(r.get("ctr", 0)) * 100,
        "position": float(r.get("position", 0)),
    }


def gsc_page_trend(page: str, start: str, end: str) -> list[dict]:
    """Daily trend for one page."""
    svc = build("searchconsole", "v1", credentials=get_credentials(), cache_discovery=False)
    full = f"{SITE_DOMAIN}{page}"
    body = {
        "startDate": start,
        "endDate": end,
        "dimensions": ["date"],
        "rowLimit": 1000,
        "dimensionFilterGroups": [{
            "filters": [{"dimension": "page", "operator": "equals", "expression": full}]
        }],
    }
    resp = svc.searchanalytics().query(siteUrl=GSC_SITE_URL, body=body).execute()
    return [{
        "date": r["keys"][0],
        "clicks": int(r.get("clicks", 0)),
        "impressions": int(r.get("impressions", 0)),
        "ctr": float(r.get("ctr", 0)) * 100,
        "position": float(r.get("position", 0)),
    } for r in resp.get("rows", [])]


# ---------- GA4 ----------

def _ga4_client():
    return BetaAnalyticsDataClient(credentials=get_credentials())


def ga4_page_metrics(
    pages: list[str],
    start: str,
    end: str,
) -> dict[str, dict]:
    """Pull per-URL views/sessions/users/bounce/organic from GA4."""
    client = _ga4_client()
    page_set = {p.rstrip("/") for p in pages}

    # ---- Overall metrics ----
    req = RunReportRequest(
        property=f"properties/{GA4_PROPERTY_ID}",
        date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name="pagePath")],
        metrics=[
            Metric(name="screenPageViews"),
            Metric(name="sessions"),
            Metric(name="totalUsers"),
            Metric(name="bounceRate"),
        ],
        limit=100000,
    )
    resp = client.run_report(req)

    by_page = {}
    for row in resp.rows:
        path = row.dimension_values[0].value
        norm = path.rstrip("/")
        if norm in page_set:
            original = next(p for p in pages if p.rstrip("/") == norm)
            existing = by_page.get(original, {"views": 0, "sessions": 0, "users": 0, "bounce": 0.0, "organic": 0, "organic_users": 0})
            views = int(float(row.metric_values[0].value))
            sessions = int(float(row.metric_values[1].value))
            users = int(float(row.metric_values[2].value))
            bounce = float(row.metric_values[3].value) * 100
            by_page[original] = {
                **existing,
                "views": existing["views"] + views,
                "sessions": existing["sessions"] + sessions,
                "users": existing["users"] + users,
                "bounce": bounce,
            }

    # ---- Organic-only metrics ----
    organic_req = RunReportRequest(
        property=f"properties/{GA4_PROPERTY_ID}",
        date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name="pagePath")],
        metrics=[
            Metric(name="sessions"),
            Metric(name="totalUsers"),
        ],
        dimension_filter=FilterExpression(
            filter=Filter(
                field_name="sessionDefaultChannelGroup",
                string_filter=Filter.StringFilter(value="Organic Search"),
            )
        ),
        limit=100000,
    )
    organic_resp = client.run_report(organic_req)
    for row in organic_resp.rows:
        path = row.dimension_values[0].value
        norm = path.rstrip("/")
        if norm in page_set:
            original = next(p for p in pages if p.rstrip("/") == norm)
            entry = by_page.setdefault(original, {"views": 0, "sessions": 0, "users": 0, "bounce": 0.0, "organic": 0, "organic_users": 0})
            entry["organic"] = entry.get("organic", 0) + int(float(row.metric_values[0].value))
            entry["organic_users"] = entry.get("organic_users", 0) + int(float(row.metric_values[1].value))

    for p in pages:
        if p not in by_page:
            by_page[p] = {"views": 0, "sessions": 0, "users": 0, "bounce": 0.0, "organic": 0, "organic_users": 0}
        else:
            by_page[p].setdefault("organic", 0)
            by_page[p].setdefault("organic_users", 0)
    return by_page


def ga4_overview(start: str, end: str) -> dict:
    client = _ga4_client()
    req = RunReportRequest(
        property=f"properties/{GA4_PROPERTY_ID}",
        date_ranges=[DateRange(start_date=start, end_date=end)],
        metrics=[
            Metric(name="sessions"),
            Metric(name="totalUsers"),
            Metric(name="screenPageViews"),
            Metric(name="bounceRate"),
        ],
    )
    resp = client.run_report(req)
    if not resp.rows:
        return {"sessions": 0, "users": 0, "views": 0, "bounce": 0.0}
    r = resp.rows[0]
    return {
        "sessions": int(float(r.metric_values[0].value)),
        "users": int(float(r.metric_values[1].value)),
        "views": int(float(r.metric_values[2].value)),
        "bounce": float(r.metric_values[3].value) * 100,
    }


def ga4_organic_overview(start: str, end: str) -> dict:
    """Site-wide organic-search-only sessions/users/views."""
    client = _ga4_client()
    req = RunReportRequest(
        property=f"properties/{GA4_PROPERTY_ID}",
        date_ranges=[DateRange(start_date=start, end_date=end)],
        metrics=[
            Metric(name="sessions"),
            Metric(name="totalUsers"),
            Metric(name="screenPageViews"),
        ],
        dimension_filter=FilterExpression(
            filter=Filter(
                field_name="sessionDefaultChannelGroup",
                string_filter=Filter.StringFilter(value="Organic Search"),
            )
        ),
    )
    resp = client.run_report(req)
    if not resp.rows:
        return {"sessions": 0, "users": 0, "views": 0}
    r = resp.rows[0]
    return {
        "sessions": int(float(r.metric_values[0].value)),
        "users": int(float(r.metric_values[1].value)),
        "views": int(float(r.metric_values[2].value)),
    }


# LLM source hosts → human-friendly names. Add new ones here as AI tools emerge.
LLM_SOURCES_MAP = {
    "ChatGPT":    ["chatgpt.com", "chat.openai.com"],
    "Perplexity": ["perplexity.ai", "www.perplexity.ai"],
    "Claude":     ["claude.ai"],
    "Gemini":     ["gemini.google.com", "bard.google.com"],
}
LLM_HOST_TO_NAME = {host.lower(): name for name, hosts in LLM_SOURCES_MAP.items() for host in hosts}
ALL_LLM_HOSTS = list(LLM_HOST_TO_NAME.keys())


def ga4_llm_traffic_by_page(pages: list[str], start: str, end: str) -> dict[str, dict]:
    """Returns {path: {ChatGPT: int, Perplexity: int, ..., total: int, users: int}}."""
    client = _ga4_client()
    page_set = {p.rstrip("/") for p in pages}
    llm_names = list(LLM_SOURCES_MAP.keys())

    req = RunReportRequest(
        property=f"properties/{GA4_PROPERTY_ID}",
        date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name="pagePath"), Dimension(name="sessionSource")],
        metrics=[Metric(name="sessions"), Metric(name="totalUsers")],
        dimension_filter=FilterExpression(
            filter=Filter(
                field_name="sessionSource",
                in_list_filter=Filter.InListFilter(values=ALL_LLM_HOSTS, case_sensitive=False),
            )
        ),
        limit=100000,
    )
    resp = client.run_report(req)

    by_page: dict[str, dict] = {}
    for row in resp.rows:
        path = row.dimension_values[0].value
        source = row.dimension_values[1].value.lower()
        norm = path.rstrip("/")
        if norm not in page_set:
            continue
        original = next(p for p in pages if p.rstrip("/") == norm)
        if original not in by_page:
            by_page[original] = {name: 0 for name in llm_names}
            by_page[original]["total"] = 0
            by_page[original]["users"] = 0

        llm_name = LLM_HOST_TO_NAME.get(source)
        if not llm_name:
            continue

        sessions = int(float(row.metric_values[0].value))
        users = int(float(row.metric_values[1].value))
        by_page[original][llm_name] += sessions
        by_page[original]["total"] += sessions
        by_page[original]["users"] += users  # NB: may overcount across LLMs

    for p in pages:
        if p not in by_page:
            by_page[p] = {name: 0 for name in llm_names}
            by_page[p]["total"] = 0
            by_page[p]["users"] = 0
    return by_page


def ga4_llm_overview(start: str, end: str) -> dict:
    """Site-wide LLM traffic totals."""
    client = _ga4_client()
    req = RunReportRequest(
        property=f"properties/{GA4_PROPERTY_ID}",
        date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name="sessionSource")],
        metrics=[Metric(name="sessions"), Metric(name="totalUsers")],
        dimension_filter=FilterExpression(
            filter=Filter(
                field_name="sessionSource",
                in_list_filter=Filter.InListFilter(values=ALL_LLM_HOSTS, case_sensitive=False),
            )
        ),
        limit=200,
    )
    resp = client.run_report(req)
    by_llm = {name: {"sessions": 0, "users": 0} for name in LLM_SOURCES_MAP}
    total_sessions = 0
    total_users = 0
    for row in resp.rows:
        source = row.dimension_values[0].value.lower()
        sessions = int(float(row.metric_values[0].value))
        users = int(float(row.metric_values[1].value))
        name = LLM_HOST_TO_NAME.get(source)
        if name:
            by_llm[name]["sessions"] += sessions
            by_llm[name]["users"] += users
        total_sessions += sessions
        total_users += users
    return {"by_llm": by_llm, "total_sessions": total_sessions, "total_users": total_users}


def ga4_page_trend(page: str, start: str, end: str) -> list[dict]:
    """Daily GA4 trend for one page."""
    client = _ga4_client()
    norm = page.rstrip("/")
    req = RunReportRequest(
        property=f"properties/{GA4_PROPERTY_ID}",
        date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name="date"), Dimension(name="pagePath")],
        metrics=[
            Metric(name="screenPageViews"),
            Metric(name="sessions"),
            Metric(name="totalUsers"),
        ],
        limit=100000,
    )
    resp = client.run_report(req)
    daily = {}
    for row in resp.rows:
        d = row.dimension_values[0].value
        path = row.dimension_values[1].value.rstrip("/")
        if path != norm:
            continue
        # GA4 date format is YYYYMMDD
        iso = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        entry = daily.setdefault(iso, {"date": iso, "views": 0, "sessions": 0, "users": 0})
        entry["views"] += int(float(row.metric_values[0].value))
        entry["sessions"] += int(float(row.metric_values[1].value))
        entry["users"] += int(float(row.metric_values[2].value))
    return sorted(daily.values(), key=lambda x: x["date"])
