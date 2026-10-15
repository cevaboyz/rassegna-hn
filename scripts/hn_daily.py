#!/usr/bin/env python3
"""HN Daily: scouting + comment digest for the morning newsletter.

Usage: python3 -I hn_daily.py --taxonomy taxonomy.json --out OUTDIR [--hours 24] [--top 22] [--batches 3]

Steps
1. Candidates: every story of the last N hours with >= 20 points (Algolia search_by_date),
   enriched with the official HN API rankings (top/best/show/ask) when Firebase is reachable,
   otherwise with Algolia's `front_page` tag. The official API is preferred because it is the
   source of truth for rankings; Algolia is the fallback and the source of full comment trees.
2. Scoring: "hot" score from points, comments and ranking position, plus a separate
   "relevance" score against the reader's work profile (marketing, analytics, automation, AI tools).
   Relevance never hides a story: it only adds extra picks to the selection.
3. Selection: top stories by hot score + extra high-relevance stories + best Show HN (tools).
4. Comments: full tree per story (Algolia items API), structural metrics, links shared in
   comments, and a compact sample of the most discussed / most evidence-rich comments.
   HN does not expose comment scores, so "interesting" is approximated by reply subtree size,
   length and evidence signals (first-hand use, numbers, links).
5. Pre-labels each story with the taxonomy regex rules (a hint for the LLM, not the final label).
6. Writes digest_batch{i}.json files sized for parallel LLM analysis, plus run_meta.json.
"""
import argparse, json, math, re, html, time, collections, concurrent.futures as cf
import urllib.request, urllib.parse
from urllib.parse import urlparse

ALGOLIA = "https://hn.algolia.com/api/v1"
FIREBASE = "https://hacker-news.firebaseio.com/v0"
UA = {"User-Agent": "hn-daily/1.0"}

# Reader work profile (marketing / analytics / automation). Weight 3 = core of the job, 2 = adjacent tooling, 1 = general interest.
PROFILE = {
    3: [r"\bmarketing\b", r"\bads?\b", r"advertis", r"\bseo\b", r"\bgeo\b", r"generative engine", r"\banalytics\b", r"\bga4\b",
        r"google tag", r"tag manager", r"\bgtm\b", r"tracking", r"server.?side", r"consent", r"attribution", r"conversion",
        r"\bcro\b", r"a/b test", r"landing page", r"amazon (seller|ads|listing)", r"e-?commerce", r"shopify", r"\bcrm\b",
        r"newsletter", r"email marketing", r"meta ads", r"google ads", r"looker", r"bigquery", r"dashboard", r"\bmcp\b",
        r"claude", r"\bskills?\b", r"n8n", r"zapier", r"make\.com", r"automation", r"\bscrap(e|er|ing)\b", r"crawler"],
    2: [r"\bagents?\b", r"agentic", r"\bllm", r"\bprompt", r"\brag\b", r"\bsql\b", r"duckdb", r"postgres", r"sqlite", r"\betl\b",
        r"spreadsheet", r"excel", r"google sheets", r"notion", r"asana", r"workflow", r"\bpython\b", r"pandas", r"polars",
        r"visuali[sz]", r"\bchart", r"no.?code", r"low.?code", r"self.?host", r"image generation", r"video generation",
        r"text.?to.?speech", r"transcri", r"\bocr\b", r"browser automation", r"playwright", r"open.?source alternative"],
    1: [r"\bopenai\b", r"anthropic", r"gemini", r"\bgpt", r"open.?weight", r"\bapi\b", r"\bcli\b", r"privacy", r"gdpr",
        r"\bsearch\b", r"youtube", r"social media", r"design", r"figma", r"photograph"],
}
PROFILE_RX = [(w, re.compile(p, re.I)) for w, ps in PROFILE.items() for p in ps]
EVIDENCE_RX = re.compile(r"\b(i (use|used|tried|built|run|switched|benchmarked|tested)|we (use|built|run|switched|moved)|in production|"
                         r"benchmark|\d+(\.\d+)?\s?(ms|x|%|gb|mb|tokens|\$|usd|eur)|\$\d)", re.I)
LINK_RX = re.compile(r"https?://[^\s<>\"')\]]+")


def get(url, timeout=30, retries=2):
    for i in range(retries + 1):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout))
        except Exception:
            if i == retries:
                raise
            time.sleep(1.5 * (i + 1))


def clean(t):
    t = html.unescape(re.sub(r"<p>", "\n", t or ""))
    t = re.sub(r"<a [^>]*href=\"([^\"]+)\"[^>]*>[^<]*</a>", r"\1", t)
    return re.sub(r"<[^>]+>", "", t).strip()


def relevance(text):
    hits = sorted({p.pattern for w, p in PROFILE_RX if p.search(text)})
    score = sum(w for w, p in PROFILE_RX if p.search(text))
    return score, hits


def official_rankings():
    """Rank position per list from the official API. Returns ({}, False) if Firebase is unreachable."""
    ranks = {}
    try:
        for lst in ("topstories", "beststories", "showstories", "askstories"):
            ids = get(f"{FIREBASE}/{lst}.json", timeout=15, retries=0)
            for pos, i in enumerate(ids[:200]):
                ranks.setdefault(str(i), {})[lst] = pos + 1
        return ranks, True
    except Exception:
        return {}, False


def candidates(hours):
    lo = int(time.time()) - hours * 3600
    out, page = {}, 0
    while True:
        q = urllib.parse.urlencode({"tags": "story", "numericFilters": f"created_at_i>{lo},points>=20", "hitsPerPage": 1000, "page": page})
        r = get(f"{ALGOLIA}/search_by_date?{q}")
        for h in r["hits"]:
            out[h["objectID"]] = h
        page += 1
        if page >= r["nbPages"]:
            break
    # Algolia front page snapshot (fallback ranking signal; can include stories older than the window)
    fp = get(f"{ALGOLIA}/search?tags=front_page&hitsPerPage=100")["hits"]
    fp_pos = {h["objectID"]: i + 1 for i, h in enumerate(fp)}
    for h in fp:
        out.setdefault(h["objectID"], h)
    return list(out.values()), fp_pos


def prelabel(title, url, tax):
    d = (urlparse(url or "").netloc or "").lower()
    best, top = None, 0
    for t in tax:
        n = sum(len(re.findall(p, title, re.I)) for p in t["patterns"]) + 2 * sum(1 for dd in t.get("domains", []) if dd in d)
        if n > top:
            best, top = t["id"], n
    return best


def flatten(node):
    rows = []
    def walk(n, depth):
        for c in n.get("children") or []:
            if c.get("type") != "comment":
                continue
            rows.append({"id": c["id"], "author": c.get("author"), "parent": c.get("parent_id"), "depth": depth,
                         "created": c.get("created_at"), "text": clean(c.get("text")), "_node": c})
            walk(c, depth + 1)
    walk(node, 0)
    sizes = {}
    def size(n):
        s = 1 + sum(size(k) for k in (n.get("children") or []) if k.get("type") == "comment")
        sizes[n["id"]] = s
        return s
    size(node)
    for r in rows:
        r["replies"] = sizes[r["id"]] - 1
        del r["_node"]
    return [r for r in rows if r["text"]]


def comment_sample(rows, k=25, maxlen=550):
    """Most discussed top-level comments, their most discussed reply, then evidence-rich comments."""
    by_parent = collections.defaultdict(list)
    for r in rows:
        by_parent[r["parent"]].append(r)
    top = sorted([r for r in rows if r["depth"] == 0], key=lambda r: -r["replies"])
    picked, seen = [], set()
    def add(r, why):
        if r["id"] in seen or len(picked) >= k:
            return
        seen.add(r["id"])
        picked.append({"id": r["id"], "author": r["author"], "depth": r["depth"], "replies": r["replies"], "why_sampled": why,
                       "text": r["text"][:maxlen] + ("…" if len(r["text"]) > maxlen else "")})
    for r in top[:10]:
        add(r, "top-level most replied")
        kids = sorted(by_parent[r["id"]], key=lambda x: -x["replies"])
        if kids:
            add(kids[0], "main reply to a top thread")
    ev = sorted([r for r in rows if EVIDENCE_RX.search(r["text"]) and len(r["text"]) > 120], key=lambda r: -(r["replies"] + len(r["text"]) / 400))
    for r in ev:
        add(r, "first-hand evidence / numbers / links")
    for r in sorted(rows, key=lambda r: -len(r["text"])):
        add(r, "long-form")
    return picked


def links_in(rows, story_url):
    own = (urlparse(story_url or "").netloc or "").replace("www.", "")
    c = collections.Counter()
    for r in rows:
        for u in set(LINK_RX.findall(r["text"])):
            u = u.rstrip(".,;:")
            p = urlparse(u)
            host = p.netloc.replace("www.", "")
            if not host or host in (own, "news.ycombinator.com"):
                continue
            if host == "github.com":
                parts = [x for x in p.path.split("/") if x][:2]
                if len(parts) == 2:
                    c[f"https://github.com/{parts[0]}/{parts[1]}"] += 1
                    continue
            c[f"{p.scheme}://{host}{p.path}".rstrip("/")] += 1
    return [{"url": u, "mentions": n} for u, n in c.most_common(15)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--taxonomy", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--top", type=int, default=22)
    ap.add_argument("--extra_relevant", type=int, default=6)
    ap.add_argument("--show", type=int, default=8)
    ap.add_argument("--batches", type=int, default=3)
    a = ap.parse_args()
    tax = json.load(open(a.taxonomy))
    tax = tax["labels"] if isinstance(tax, dict) else tax

    ranks, firebase_ok = official_rankings()
    cands, fp_pos = candidates(a.hours)
    now = time.time()
    for h in cands:
        i = h["objectID"]
        pts, com = h.get("points") or 0, h.get("num_comments") or 0
        age_h = max(1.0, (now - h["created_at_i"]) / 3600)
        r = ranks.get(i, {})
        rank = min([v for k, v in r.items() if k in ("topstories", "beststories")] or [fp_pos.get(i, 999)])
        h["_rank"] = rank
        h["_ranks"] = r or ({"algolia_front_page": fp_pos[i]} if i in fp_pos else {})
        # log-scaled popularity + discussion intensity + ranking bonus; velocity favours stories still climbing
        h["_hot"] = round(math.log1p(pts) + 0.8 * math.log1p(com) + (2.0 if rank <= 30 else 1.0 if rank <= 90 else 0)
                          + 0.5 * math.log1p(pts / age_h), 3)
        rel, hits = relevance(h["title"] + " " + clean(h.get("story_text")) + " " + (h.get("url") or ""))
        h["_rel"], h["_rel_hits"] = rel, hits
        h["_is_show"] = "show_hn" in h.get("_tags", [])
    by_hot = sorted(cands, key=lambda h: -h["_hot"])
    sel, ids = [], set()
    def take(h, why):
        if h["objectID"] not in ids:
            ids.add(h["objectID"]); h["_why"] = why; sel.append(h)
    for h in by_hot[: a.top]:
        take(h, "top")
    for h in sorted([h for h in cands if h["_rel"] >= 3 and (h.get("points") or 0) >= 30], key=lambda h: -(h["_rel"] * 2 + h["_hot"]))[: a.extra_relevant]:
        take(h, "relevant-to-profile")
    for h in sorted([h for h in cands if h["_is_show"]], key=lambda h: -h["_hot"])[: a.show]:
        take(h, "show-hn-tool")

    def enrich(h):
        try:
            item = get(f"{ALGOLIA}/items/{h['objectID']}", timeout=60)
        except Exception as e:
            return h, None, str(e)
        return h, item, None

    stories, errors = [], []
    with cf.ThreadPoolExecutor(6) as ex:
        for h, item, err in ex.map(enrich, sel):
            if err:
                errors.append({"id": h["objectID"], "error": err}); continue
            rows = flatten(item)
            authors = collections.Counter(r["author"] for r in rows)
            stories.append({
                "id": int(h["objectID"]), "title": h["title"], "url": h.get("url"),
                "hn_url": f"https://news.ycombinator.com/item?id={h['objectID']}", "author": h.get("author"),
                "created": h.get("created_at"), "points": item.get("points") or h.get("points"),
                "num_comments_listed": h.get("num_comments"), "comments_fetched": len(rows),
                "unique_commenters": len(authors), "max_depth": max([r["depth"] for r in rows], default=0),
                "top_threads": sum(1 for r in rows if r["depth"] == 0),
                "is_show_hn": h["_is_show"], "is_ask_hn": "ask_hn" in h.get("_tags", []),
                "story_text": clean(item.get("text"))[:1500],
                "hot_score": h["_hot"], "rank_positions": h["_ranks"], "selected_because": h["_why"],
                "profile_relevance": h["_rel"], "profile_hits": h["_rel_hits"],
                "rule_label": prelabel(h["title"], h.get("url"), tax),
                "links_in_comments": links_in(rows, h.get("url")),
                "comment_sample": comment_sample(rows),
            })
    stories.sort(key=lambda s: -s["hot_score"])
    n = max(1, a.batches)
    for b in range(n):
        json.dump(stories[b::n], open(f"{a.out}/digest_batch{b+1}.json", "w"), ensure_ascii=False, indent=1)
    meta = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "window_hours": a.hours,
            "official_api_reachable": firebase_ok, "ranking_source": "HN official API" if firebase_ok else "Algolia front_page",
            "candidates": len(cands), "selected": len(stories), "errors": errors,
            "comments_fetched_total": sum(s["comments_fetched"] for s in stories),
            "comments_listed_total": sum(s["num_comments_listed"] or 0 for s in stories),
            "top_candidates_not_selected": [{"title": h["title"], "points": h.get("points"), "comments": h.get("num_comments")} for h in by_hot[a.top:a.top + 15] if h["objectID"] not in ids]}
    json.dump(meta, open(f"{a.out}/run_meta.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: meta[k] for k in ("official_api_reachable", "candidates", "selected", "comments_fetched_total", "comments_listed_total", "errors")}))


if __name__ == "__main__":
    main()
