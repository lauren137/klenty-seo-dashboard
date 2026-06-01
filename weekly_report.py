"""Weekly Slack SEO report — runs from GitHub Actions every Tuesday 9am IST.

Covers the previous Monday → Sunday window. Compares against the week before.
Posts a formatted summary to Slack via incoming webhook.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import date, timedelta

# Reuse the existing dashboard modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import google_clients as gc

DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
SEED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_urls.json")

SEVERITY_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢", "info": "🔵"}


# ---------------- Date math ----------------

def last_full_week(today: date) -> tuple[date, date]:
    """Return (monday, sunday) of the most recent completed Mon–Sun week.
    weekday(): Mon=0, Sun=6. Always returns a Sunday strictly before today.
    """
    offset = (today.weekday() + 1) % 7 or 7
    last_sunday = today - timedelta(days=offset)
    last_monday = last_sunday - timedelta(days=6)
    return last_monday, last_sunday


def prior_week(monday: date, sunday: date) -> tuple[date, date]:
    return monday - timedelta(days=7), sunday - timedelta(days=7)


# ---------------- Diagnosis (lite — only top issues for Slack) ----------------

def diagnose_url(m: dict, prior: dict) -> list[dict]:
    issues = []
    pos = m.get("position"); clicks = m.get("clicks", 0)
    impr = m.get("impressions", 0); ctr = m.get("ctr", 0)
    sessions = m.get("sessions", 0); bounce = m.get("bounce", 0)
    organic = m.get("organic", 0)
    prev_clicks = prior.get("clicks", 0); prev_pos = prior.get("position")

    if (pos is None or pos == 0) and impr == 0 and clicks == 0:
        issues.append({"severity": "high", "label": "Not ranking",
                       "fix": "Check indexing in GSC, add to sitemap, build internal links."})
    if pos and pos < 10 and impr >= 200 and ctr < 2.0:
        issues.append({"severity": "high", "label": f"Low CTR at pos {pos:.1f}",
                       "fix": f"{impr:,} impressions, {ctr:.2f}% CTR. Rewrite title + meta description for stronger hook."})
    if pos and 10 <= pos <= 20 and impr >= 500:
        issues.append({"severity": "medium", "label": f"Striking distance (pos {pos:.1f})",
                       "fix": "Push to page 1: stronger H1, FAQ schema, 3-5 internal links from authority pages."})
    if pos and prev_pos and prev_pos < pos - 3:
        issues.append({"severity": "high", "label": f"Dropped {prev_pos:.1f} → {pos:.1f}",
                       "fix": "Audit recent edits, lost backlinks, new SERP competitors, algo updates."})
    if prev_clicks >= 5 and clicks < prev_clicks * 0.6:
        issues.append({"severity": "high", "label": f"Clicks dropped {prev_clicks} → {clicks}",
                       "fix": "Cross-reference position & impression deltas. If position held → SERP feature stole traffic."})
    if clicks >= 5 and sessions == 0:
        issues.append({"severity": "high", "label": "Tracking gap",
                       "fix": f"{clicks} GSC clicks but 0 GA4 sessions. Check redirects, GTM, tag firing."})
    if sessions >= 10 and bounce >= 80:
        issues.append({"severity": "medium", "label": f"Bounce {bounce:.0f}%",
                       "fix": "Add TL;DR + clearer CTA above the fold."})
    return issues


# ---------------- Slack Block Kit ----------------

def build_blocks(period_label: str, prior_label: str, overview: dict, prior_ov: dict,
                 movers: list[dict], fix_groups: dict, deep_link: str | None) -> list[dict]:
    g = overview["gsc"]; pg = prior_ov["gsc"]
    a = overview["ga4"]; pa = prior_ov["ga4"]

    def pct(c, p):
        if not p: return None
        return (c - p) / p * 100

    def delta(c, p, inverse=False):
        pp = pct(c, p)
        if pp is None: return "—"
        arrow = "🔺" if (pp > 0) ^ inverse else "🔻"
        return f"{arrow} {abs(pp):.1f}%"

    top5 = sorted(movers, key=lambda x: x["clicks"], reverse=True)[:5]
    gainers = sorted([m for m in movers if m["delta"] > 0], key=lambda x: x["delta"], reverse=True)[:3]
    losers = sorted([m for m in movers if m["delta"] < 0], key=lambda x: x["delta"])[:3]

    blocks: list[dict] = []
    blocks.append({"type": "header", "text": {"type": "plain_text",
                   "text": f"📊 Klenty SEO Weekly · {period_label}"}})
    blocks.append({"type": "context", "elements": [
        {"type": "mrkdwn", "text": f"Comparing to prior week ({prior_label})"}
    ]})
    blocks.append({"type": "divider"})

    # ---- Overall ----
    blocks.append({"type": "section", "fields": [
        {"type": "mrkdwn", "text": f"*Clicks*\n{g['clicks']:,}  {delta(g['clicks'], pg['clicks'])}"},
        {"type": "mrkdwn", "text": f"*Impressions*\n{g['impressions']:,}  {delta(g['impressions'], pg['impressions'])}"},
        {"type": "mrkdwn", "text": f"*Avg Position*\n{g['position']:.1f}  {delta(g['position'], pg['position'], inverse=True)}"},
        {"type": "mrkdwn", "text": f"*CTR*\n{g['ctr']:.2f}%"},
        {"type": "mrkdwn", "text": f"*Users*\n{a['users']:,}  {delta(a['users'], pa['users'])}"},
        {"type": "mrkdwn", "text": f"*Sessions*\n{a['sessions']:,}  {delta(a['sessions'], pa['sessions'])}"},
    ]})
    blocks.append({"type": "divider"})

    # ---- Top performers ----
    top_lines = []
    for i, m in enumerate(top5, 1):
        pos = f"pos {m['position']:.1f}" if m['position'] else "no rank"
        top_lines.append(f"{i}. `{m['url']}` — *{m['clicks']:,} clicks*, {m['organic']:,} organic, {pos}")
    blocks.append({"type": "section", "text": {"type": "mrkdwn",
                   "text": "*🏆 Top 5 by clicks*\n" + ("\n".join(top_lines) or "_no data_")}})

    # ---- Movers ----
    mover_text = ""
    if gainers:
        mover_text += "*📈 Gainers*\n" + "\n".join(
            f"• `{m['url']}` — +{m['delta']:,} ({m['prev_clicks']:,} → {m['clicks']:,})"
            for m in gainers
        )
    if losers:
        if mover_text: mover_text += "\n\n"
        mover_text += "*📉 Losers*\n" + "\n".join(
            f"• `{m['url']}` — {m['delta']:,} ({m['prev_clicks']:,} → {m['clicks']:,})"
            for m in losers
        )
    if mover_text:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": mover_text}})

    blocks.append({"type": "divider"})

    # ---- Top fix recommendations ----
    if fix_groups:
        fix_text = "*🛠️ Recommended fixes this week*\n"
        for label, payload in list(fix_groups.items())[:5]:
            urls = payload["urls"]; fix = payload["fix"]; sev = payload["severity"]
            emoji = SEVERITY_EMOJI.get(sev, "•")
            url_list = ", ".join(f"`{u}`" for u in urls[:3])
            if len(urls) > 3:
                url_list += f" _+{len(urls) - 3} more_"
            fix_text += f"\n{emoji} *{label}* ({len(urls)} URLs)\n_{fix}_\nAffected: {url_list}\n"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": fix_text}})

    # ---- Footer ----
    if deep_link:
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"<{deep_link}|Open full dashboard →>"}
        ]})

    return blocks


def post_to_slack(blocks: list[dict]):
    if not SLACK_WEBHOOK_URL:
        print("⚠ SLACK_WEBHOOK_URL not set — printing payload instead\n")
        print(json.dumps({"blocks": blocks}, indent=2))
        return
    payload = json.dumps({"blocks": blocks}).encode()
    req = urllib.request.Request(
        SLACK_WEBHOOK_URL, data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode()
        print(f"Slack POST status={resp.status} body={body}")


# ---------------- Main ----------------

def main():
    today = date.today()
    mon, sun = last_full_week(today)
    p_mon, p_sun = prior_week(mon, sun)
    start, end = mon.isoformat(), sun.isoformat()
    p_start, p_end = p_mon.isoformat(), p_sun.isoformat()
    period_label = f"{mon.strftime('%b %d')} – {sun.strftime('%b %d, %Y')}"
    prior_label = f"{p_mon.strftime('%b %d')} – {p_sun.strftime('%b %d')}"
    print(f"Reporting period: {start} → {end} (vs {p_start} → {p_end})")

    with open(SEED_PATH) as f:
        urls = json.load(f)
    print(f"Tracking {len(urls)} URLs")

    # Fetch everything
    print("Fetching GSC + GA4...")
    overview = {"gsc": gc.gsc_overview(start, end), "ga4": gc.ga4_overview(start, end)}
    prior_ov = {"gsc": gc.gsc_overview(p_start, p_end), "ga4": gc.ga4_overview(p_start, p_end)}

    gsc_curr = gc.gsc_page_metrics(urls, start, end)
    ga4_curr = gc.ga4_page_metrics(urls, start, end)
    gsc_prior = gc.gsc_page_metrics(urls, p_start, p_end)
    ga4_prior = gc.ga4_page_metrics(urls, p_start, p_end)

    # Build per-URL records + diagnoses
    movers = []
    fix_groups: dict[str, dict] = {}
    for u in urls:
        cm = {**gsc_curr.get(u, {}), **ga4_curr.get(u, {})}
        pm = {**gsc_prior.get(u, {}), **ga4_prior.get(u, {})}
        delta_clicks = (cm.get("clicks", 0) or 0) - (pm.get("clicks", 0) or 0)
        movers.append({
            "url": u,
            "clicks": cm.get("clicks", 0) or 0,
            "prev_clicks": pm.get("clicks", 0) or 0,
            "delta": delta_clicks,
            "position": cm.get("position"),
            "organic": cm.get("organic", 0) or 0,
            "sessions": cm.get("sessions", 0) or 0,
        })
        for iss in diagnose_url(cm, pm):
            label = iss["label"]
            grp = fix_groups.setdefault(label, {"urls": [], "fix": iss["fix"], "severity": iss["severity"]})
            grp["urls"].append(u)

    # Sort fix_groups by severity → count
    sev_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    fix_groups_sorted = dict(sorted(
        fix_groups.items(),
        key=lambda kv: (sev_order.get(kv[1]["severity"], 9), -len(kv[1]["urls"])),
    ))

    blocks = build_blocks(period_label, prior_label, overview, prior_ov, movers, fix_groups_sorted, DASHBOARD_URL)
    post_to_slack(blocks)


if __name__ == "__main__":
    main()
