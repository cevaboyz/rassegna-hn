#!/usr/bin/env python3
"""Write one assembled issue into the site data and refresh the derived files.

Usage: python3 -I scripts/publish.py --run RUNDIR --date YYYY-MM-DD [--site .]
- data/issues/<date>.json   the full issue (what the page and the email read)
- data/index.json           one small entry per edition (edition picker + tool archive)
- data/taxonomy.json        labels; new labels created by the day's analysis are appended
- feed.xml                  RSS of the last 30 editions, for feed readers
Idempotent: re-running for the same date replaces that date's entries.
"""
import argparse, json, os, html, datetime, email.utils

ap = argparse.ArgumentParser()
ap.add_argument("--run", required=True); ap.add_argument("--date", required=True); ap.add_argument("--site", default=".")
ap.add_argument("--base-url", default="")
a = ap.parse_args()
D = os.path.join(a.site, "data")
os.makedirs(os.path.join(D, "issues"), exist_ok=True)

issue = json.load(open(os.path.join(a.run, "issue.json")))
entry = json.load(open(os.path.join(a.run, "index.json")))
new_labels = json.load(open(os.path.join(a.run, "new_labels.json")))
json.dump(issue, open(os.path.join(D, "issues", f"{a.date}.json"), "w"), ensure_ascii=False)

ip = os.path.join(D, "index.json")
index = json.load(open(ip)) if os.path.exists(ip) else []
index = [e for e in index if e["date"] != a.date] + [entry]
index.sort(key=lambda e: e["date"], reverse=True)
json.dump(index, open(ip, "w"), ensure_ascii=False)

tp = os.path.join(D, "taxonomy.json")
tax = json.load(open(tp))
have = {l["id"] for l in tax["labels"]}
added = [l for l in new_labels if l["id"] not in have]
tax["labels"] += added
json.dump(tax, open(tp, "w"), ensure_ascii=False, indent=1)

# RSS 2.0: title = headline, description = intro + "da provare" names
base = a.base_url.rstrip("/")
items = []
for e in index[:30]:
    p = os.path.join(D, "issues", f"{e['date']}.json")
    if not os.path.exists(p):
        continue
    iss = json.load(open(p)); ed = iss.get("editorial", {})
    desc = ed.get("intro", "")
    if ed.get("try_today"):
        desc += " Da provare: " + "; ".join(t.get("name", "") for t in ed["try_today"]) + "."
    dt = datetime.datetime.strptime(e["date"], "%Y-%m-%d").replace(hour=7, minute=30, tzinfo=datetime.timezone.utc)
    link = f"{base}/?d={e['date']}" if base else f"?d={e['date']}"
    items.append(f"<item><title>{html.escape(e['date'] + ' · ' + (e.get('headline') or 'Rassegna HN'))}</title>"
                 f"<link>{html.escape(link)}</link><guid isPermaLink=\"false\">rassegna-hn-{e['date']}</guid>"
                 f"<pubDate>{email.utils.format_datetime(dt)}</pubDate><description>{html.escape(desc)}</description></item>")
rss = ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>Rassegna HN</title>'
       f"<link>{html.escape(base or '.')}</link><description>Rassegna quotidiana di Hacker News</description><language>it</language>"
       + "".join(items) + "</channel></rss>\n")
open(os.path.join(a.site, "feed.xml"), "w").write(rss)
print(json.dumps({"issue": f"data/issues/{a.date}.json", "editions": len(index), "labels_added": [l["id"] for l in added]}))
