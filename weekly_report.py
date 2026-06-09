"""Weekly Slack SEO report — runs from GitHub Actions every Tuesday 9am IST.

Covers the previous Monday → Sunday window. Compares against the week before.
Posts a formatted summary to Slack via incoming webhook.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta

# Reuse the existing dashboard modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import google_clients as gc

DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
SEED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_urls.json")

SEVERITY_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢", "info": "🔵"}


def already_posted_today() -> bool:
    """Check via GitHub API whether a scheduled run from this workflow already
    succeeded today (UTC). Manual workflow_dispatch runs ALWAYS proceed."""
    if os.environ.get("GITHUB_EVENT_NAME") != "schedule":
        return False  # always allow manual triggers
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    wf_name = os.environ.get("GITHUB_WORKFLOW_ID", "")
    if not (repo and token):
        return False
    today_utc = date.today()
    url = f"https://api.github.com/repos/{repo}/actions/runs?per_page=30&event=schedule"
    try:
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
    except Exception as e:
        print(f"Dedup check failed (proceeding anyway): {e}")
        return False
    current_run_id = os.environ.get("GITHUB_RUN_ID", "")
    for run in data.get("workflow_runs", []):
        if str(run.get("id")) == current_run_id:
            continue  # skip the in-flight run
        if run.get("name") != wf_name:
            continue
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            continue
        try:
            ran_at = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00")).date()
        except Exception:
            continue
        if ran_at == today_utc:
            print(f"Already posted today (run #{run.get('run_number')} at {run['created_at']}). Skipping.")
            return True
    return False


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

def build_narrative(period_label: str, overview: dict, prior_ov: dict,
                    movers: list[dict], fix_groups: dict) -> str:
    """Plain-English summary paragraph — copy-paste friendly."""
    g = overview["gsc"]; pg = prior_ov["gsc"]
    a = overview["ga4"]; pa = prior_ov["ga4"]

    def chg(curr, prev, label, inverse=False):
        if not prev:
            return f"{label} held at {curr}"
        delta = (curr - prev) / prev * 100
        direction = "up" if delta > 0 else "down"
        if inverse:  # for position (lower=better)
            direction = "worsened" if delta > 0 else "improved"
        return f"{label} {direction} {abs(delta):.1f}%"

    top = sorted(movers, key=lambda x: x["clicks"], reverse=True)[:1]
    gainers = sorted([m for m in movers if m["delta"] > 0], key=lambda x: x["delta"], reverse=True)[:2]
    losers = sorted([m for m in movers if m["delta"] < 0], key=lambda x: x["delta"])[:2]
    high_sev_fixes = [(label, payload) for label, payload in fix_groups.items()
                      if payload["severity"] == "high"]
    striking_count = sum(1 for m in movers if m.get("position") and 10 <= m["position"] <= 20)
    zero_count = sum(1 for m in movers if m["clicks"] == 0 and m.get("organic", 0) == 0)

    paragraphs = []

    # ---- Paragraph 1: overall headline ----
    p1 = (
        f"*Week of {period_label}* — Klenty's tracked URLs received "
        f"*{g['clicks']:,} clicks* ({chg(g['clicks'], pg['clicks'], 'WoW')}) "
        f"from *{g['impressions']:,} impressions* ({chg(g['impressions'], pg['impressions'], 'WoW')}). "
        f"Average search position {chg(g['position'], pg['position'], '', inverse=True).strip()} "
        f"from {pg['position']:.1f} to {g['position']:.1f}, with CTR at {g['ctr']:.2f}%. "
        f"GA4 reported *{a['users']:,} users* ({chg(a['users'], pa['users'], 'WoW')}) "
        f"and {a['sessions']:,} sessions across the tracked set."
    )
    paragraphs.append(p1)

    # ---- Paragraph 2: winners + losers ----
    p2_parts = []
    if top:
        t = top[0]
        pos_str = f"position {t['position']:.1f}" if t["position"] else "no rank"
        p2_parts.append(
            f"Top performer was `{t['url']}` with *{t['clicks']:,} clicks* "
            f"and {t['organic']:,} organic sessions at {pos_str}."
        )
    if gainers:
        g_names = ", ".join(f"`{m['url']}` (+{m['delta']})" for m in gainers)
        p2_parts.append(f"Biggest gainers: {g_names}.")
    if losers:
        l_names = ", ".join(f"`{m['url']}` ({m['delta']})" for m in losers)
        p2_parts.append(f"Biggest declines: {l_names}.")
    if p2_parts:
        paragraphs.append(" ".join(p2_parts))

    # ---- Categorize high-severity issues into clean buckets ----
    def categorize_high_sev():
        buckets = {
            "position drops": 0,
            "indexing / not ranking": 0,
            "low CTR at top positions": 0,
            "click declines": 0,
            "tracking gaps": 0,
        }
        for label, payload in high_sev_fixes:
            count = len(payload["urls"])
            ll = label.lower()
            if "dropped" in ll and "→" in label and "position" not in ll and "click" not in ll:
                buckets["position drops"] += count
            elif "clicks dropped" in ll:
                buckets["click declines"] += count
            elif "not ranking" in ll or "not indexed" in ll:
                buckets["indexing / not ranking"] += count
            elif "low ctr" in ll:
                buckets["low CTR at top positions"] += count
            elif "tracking" in ll:
                buckets["tracking gaps"] += count
            else:
                buckets["position drops"] += count  # default bucket for misc drops
        return {k: v for k, v in buckets.items() if v > 0}

    # ---- Paragraph 3: fixes + opportunities ----
    p3_parts = []
    high_buckets = categorize_high_sev()
    if high_buckets:
        total_urls = sum(high_buckets.values())
        bucket_phrases = [f"*{n}* {name}" for name, n in sorted(high_buckets.items(), key=lambda x: -x[1])]
        p3_parts.append(
            f"This week's diagnosis flagged {total_urls} URL-issue{'s' if total_urls != 1 else ''} needing attention: "
            f"{', '.join(bucket_phrases)}."
        )
    if striking_count:
        p3_parts.append(
            f"*{striking_count} URL{'s' if striking_count != 1 else ''}* sit in striking distance "
            f"(positions 10–20) — strong candidates to push to page 1 this week with title rewrites, "
            f"FAQ schema, and internal linking from authority pages."
        )
    if zero_count:
        p3_parts.append(
            f"{zero_count} URL{'s' if zero_count != 1 else ''} had zero clicks and zero organic traffic — "
            f"audit indexing status and topical relevance, or consider consolidating into stronger sibling pages."
        )
    if p3_parts:
        paragraphs.append(" ".join(p3_parts))

    return "\n\n".join(paragraphs)


def build_llm_blocks(llm_overview: dict, prior_llm_overview: dict,
                     llm_per_page: dict) -> list[dict]:
    """Returns a list of Slack Block Kit blocks for the LLM Traffic section."""
    blocks = []
    total = llm_overview.get("total_sessions", 0)
    prior_total = prior_llm_overview.get("total_sessions", 0)
    total_users = llm_overview.get("total_users", 0)
    by_llm = llm_overview.get("by_llm", {})

    if not total and not prior_total:
        return []  # nothing to report

    def chg(c, p):
        if not p: return ""
        d = (c - p) / p * 100
        arrow = "🔺" if d > 0 else "🔻"
        return f"  {arrow} {abs(d):.1f}%"

    blocks.append({"type": "header", "text": {"type": "plain_text", "text": "🤖 LLM Traffic"}})
    blocks.append({"type": "section", "text": {"type": "mrkdwn",
                   "text": f"*{total:,}* sessions from AI tools{chg(total, prior_total)} · *{total_users:,}* users"}})

    # Per-LLM breakdown
    llm_lines = []
    for name, m in by_llm.items():
        sessions = m.get("sessions", 0)
        if sessions == 0:
            continue
        prev = prior_llm_overview.get("by_llm", {}).get(name, {}).get("sessions", 0)
        llm_lines.append(f"• *{name}*: {sessions:,} sessions{chg(sessions, prev)}")
    if llm_lines:
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
                       "text": "*By source*\n" + "\n".join(llm_lines)}})

    # Top URLs by LLM citations
    ranked = sorted(
        [(u, m) for u, m in llm_per_page.items() if m.get("total", 0) > 0],
        key=lambda x: -x[1]["total"],
    )
    if ranked:
        top_lines = []
        for u, m in ranked[:5]:
            sources = ", ".join(f"{k}={v}" for k, v in m.items() if k not in ("total", "users") and v > 0)
            top_lines.append(f"• `{u}` — *{m['total']}* ({sources})")
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
                       "text": "*Top cited URLs (this week)*\n" + "\n".join(top_lines)}})

    # Quick tips
    zero_count = sum(1 for m in llm_per_page.values() if m.get("total", 0) == 0)
    tip_lines = []
    if zero_count > 0:
        tip_lines.append(f"• *{zero_count}* of {len(llm_per_page)} tracked URLs got zero LLM citations — add FAQ schema + answer-first opening paragraph")
    tip_lines.append("• LLMs love structured Q&A: add H2 question-style headings with 40–60 word direct answers")
    tip_lines.append("• Build Reddit / Quora / Wikipedia citations — LLMs heavily reference these")
    tip_lines.append("• Add `/llms.txt` at klenty.com to guide AI crawlers ([llmstxt.org](https://llmstxt.org))")
    blocks.append({"type": "section", "text": {"type": "mrkdwn",
                   "text": "*How to grow LLM citations*\n" + "\n".join(tip_lines)}})

    return blocks


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

    # ---- Narrative summary (copy-paste friendly) ----
    narrative = build_narrative(period_label, overview, prior_ov, movers, fix_groups)
    blocks.append({"type": "section", "text": {"type": "mrkdwn",
                   "text": f"*📝 Executive summary*\n{narrative}"}})
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

    # ---- LLM Traffic section ----
    # (Caller appends llm blocks before this footer if data exists)

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
    if already_posted_today():
        return

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

    # LLM data
    print("Fetching LLM traffic...")
    llm_overview = gc.ga4_llm_overview(start, end)
    prior_llm_overview = gc.ga4_llm_overview(p_start, p_end)
    llm_per_page = gc.ga4_llm_traffic_by_page(urls, start, end)

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

    # Insert LLM section before the footer context block (last block if dashboard link exists)
    llm_blocks = build_llm_blocks(llm_overview, prior_llm_overview, llm_per_page)
    if llm_blocks:
        # Pop the existing footer (dashboard link) if present so we can re-append it last
        footer = None
        if DASHBOARD_URL and blocks and blocks[-1].get("type") == "context":
            footer = blocks.pop()
        blocks.append({"type": "divider"})
        blocks.extend(llm_blocks)
        if footer:
            blocks.append(footer)

    post_to_slack(blocks)


if __name__ == "__main__":
    main()
