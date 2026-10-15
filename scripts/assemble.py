#!/usr/bin/env python3
"""Merge digests + LLM analyses into one newsletter issue, validating the LLM output against the raw data.

Usage: python3 -I assemble.py --run RUNDIR --taxonomy taxonomy.json --date YYYY-MM-DD [--editorial editorial.json]
Writes RUNDIR/issue.json (one ArtifactData document) and RUNDIR/new_labels.json, prints a validation report.
"""
import argparse, json, glob, collections, re

ap = argparse.ArgumentParser()
ap.add_argument("--run", required=True); ap.add_argument("--taxonomy", required=True)
ap.add_argument("--date", required=True); ap.add_argument("--editorial")
# private deny-list (one term per line, kept outside the public repo): the build fails if any term appears in the output
ap.add_argument("--deny-file")
a = ap.parse_args()

tax = json.load(open(a.taxonomy)); tax = tax["labels"] if isinstance(tax, dict) else tax
names = {t["id"]: t["name"] for t in tax}
digest = {s["id"]: s for f in sorted(glob.glob(f"{a.run}/digest_batch*.json")) for s in json.load(open(f))}
analysis = {x["id"]: x for f in sorted(glob.glob(f"{a.run}/analysis_*.json")) for x in json.load(open(f))}
meta = json.load(open(f"{a.run}/run_meta.json"))
report = collections.Counter(); issues = []

new_labels = {}
stories = []
for sid, d in digest.items():
    x = analysis.get(sid)
    if not x:
        issues.append(f"story {sid} has no analysis"); continue
    lab = x["label"]
    if lab.startswith("NEW:"):
        nid, nname, ndesc = (lab[4:].split("|") + ["", ""])[:3]
        new_labels[nid] = {"id": nid, "name": nname or nid, "description": ndesc, "patterns": [], "domains": [], "origin": f"daily-{a.date}", "examples": [d["title"]]}
        names[nid] = nname or nid; lab = nid
    elif lab not in names:
        issues.append(f"story {sid}: unknown label {lab}"); report["bad_label"] += 1
    # verify quotes and ids against the raw comment sample (fabrication guard)
    sample = {c["id"]: c for c in d["comment_sample"]}
    good = []
    for c in x.get("best_comments", []):
        src = sample.get(c.get("id"))
        q = (c.get("quote") or "").rstrip("…").strip()
        if src and q and q in src["text"]:
            good.append({**c, "hn_url": f"https://news.ycombinator.com/item?id={c['id']}", "replies": src["replies"]}); report["quote_ok"] += 1
        else:
            report["quote_dropped"] += 1; issues.append(f"story {sid}: dropped unverifiable quote from comment {c.get('id')}")
    # tool URLs must come from the story URL or the links shared in comments
    allowed = {(d.get("url") or "").rstrip("/"), d["hn_url"]} | {l["url"].rstrip("/") for l in d["links_in_comments"]}
    tools = []
    for t in x.get("tools", []):
        u = (t.get("url") or "").rstrip("/")
        if u and not any(u == al or u.startswith(al) or al.startswith(u) for al in allowed if al):
            report["tool_url_unverified"] += 1; t["url_verified"] = False
        else:
            t["url_verified"] = bool(u)
        t.update({"story_id": sid, "story_title": d["title"]}); tools.append(t)
    stories.append({
        "id": sid, "title": d["title"], "url": d.get("url"), "hn_url": d["hn_url"], "points": d["points"],
        "comments": d["num_comments_listed"], "comments_fetched": d["comments_fetched"], "commenters": d["unique_commenters"],
        "is_show_hn": d["is_show_hn"], "is_ask_hn": d["is_ask_hn"], "hot_score": d["hot_score"], "rank": d["rank_positions"],
        "selected_because": d["selected_because"], "label": lab, "label_name": names.get(lab, lab),
        "secondary_label": x.get("secondary_label"), "summary_source": x.get("summary_source", "titolo"), "summary": x.get("summary_it"), "discussion": x.get("discussion_it"),
        "tone": x.get("tone"), "sentiment_sample": x.get("sentiment_sample"), "pro": x.get("pro_it", []), "con": x.get("con_it", []),
        "best_comments": good, "tools": tools, "interest": x.get("interest"), "relevance": x.get("relevance_reader"),
        "relevance_reason": x.get("relevance_reason_it"),
    })

stories.sort(key=lambda s: -s["hot_score"])
by_label = collections.defaultdict(list)
for s in stories:
    by_label[s["label"]].append(s)
topics = sorted([{"label": k, "name": names.get(k, k), "story_ids": [s["id"] for s in v], "points": sum(s["points"] or 0 for s in v),
                  "comments": sum(s["comments"] or 0 for s in v)} for k, v in by_label.items()], key=lambda t: -(t["points"] + 2 * t["comments"]))
tools = sorted([t for s in stories for t in s["tools"]], key=lambda t: (-(t.get("relevance") or 0), not t["url_verified"]))
comments_of_day = sorted([dict(c, story_id=s["id"], story_title=s["title"]) for s in stories for c in s["best_comments"]],
                         key=lambda c: -c["replies"])[:10]
editorial = json.load(open(a.editorial)) if a.editorial else {}
# every story the editorial points to must exist in this issue
known = {s["id"] for s in stories}
for sec in ("try_today", "for_your_work"):
    for e in editorial.get(sec, []):
        if e.get("story_id") not in known:
            issues.append(f"editorial {sec}: story_id {e.get('story_id')} not in issue"); report["editorial_bad_ref"] += 1
issue = {
    "date": a.date, "generated_at": meta["generated_at"], "editorial": editorial,
    "stats": {"candidates": meta["candidates"], "selected": len(stories), "comments_listed": meta["comments_listed_total"],
              "comments_fetched": meta["comments_fetched_total"], "ranking_source": meta["ranking_source"],
              "official_api_reachable": meta["official_api_reachable"], "validation": dict(report)},
    "topics": topics, "stories": stories, "tools": tools, "comments_of_day": comments_of_day,
    "new_labels": list(new_labels.values()),
    "not_selected": meta.get("top_candidates_not_selected", []),
}
if a.deny_file:
    terms = [t.strip() for t in open(a.deny_file) if t.strip()]
    blob = json.dumps(issue, ensure_ascii=False)
    for t in terms:
        if re.search(r"\b" + re.escape(t) + r"\b", blob, re.I):
            issues.append(f"DENY: a private term appears in the output (term #{terms.index(t) + 1})"); report["deny_hit"] += 1
    issue["stats"]["validation"] = dict(report)
report["from_article"] = sum(1 for s in stories if s["summary_source"] == "articolo")
report["from_comments"] = sum(1 for s in stories if s["summary_source"] == "commenti")
issue["stats"]["validation"] = dict(report)
json.dump(issue, open(f"{a.run}/issue.json", "w"), ensure_ascii=False)
json.dump(list(new_labels.values()), open(f"{a.run}/new_labels.json", "w"), ensure_ascii=False, indent=1)
# small index document: lets the archive page list editions and aggregate tools without loading every issue
keep = ("name", "url", "what_it", "category", "maturity", "relevance", "why_for_reader_it", "url_verified", "story_id")
index = {"date": a.date, "headline": editorial.get("headline", ""), "stories": len(stories),
         "labels": [s["label"] for s in stories], "tools": [{k: t.get(k) for k in keep} for t in tools]}
json.dump(index, open(f"{a.run}/index.json", "w"), ensure_ascii=False)
size = len(json.dumps(issue, ensure_ascii=False).encode())
print(json.dumps({"stories": len(stories), "tools": len(tools), "topics": len(topics), "new_labels": list(new_labels), "bytes": size,
                  "fits_256KiB": size < 250_000, "validation": dict(report), "issues": issues[:20]}, ensure_ascii=False, indent=1))
