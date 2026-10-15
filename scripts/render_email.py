#!/usr/bin/env python3
"""Render one issue as an email: HTML with inline styles (email clients ignore <style>) plus a plain-text part.

Usage: python3 scripts/render_email.py data/issues/YYYY-MM-DD.json --site-url URL --out-dir OUT
Writes OUT/subject.txt, OUT/email.html, OUT/email.txt. Standard library only, so it runs on a bare GitHub runner.
"""
import argparse, json, html, os

ap = argparse.ArgumentParser()
ap.add_argument("issue"); ap.add_argument("--site-url", default=""); ap.add_argument("--out-dir", default=".")
a = ap.parse_args()
I = json.load(open(a.issue)); E = I.get("editorial", {}); st = I["stats"]; v = st.get("validation", {})
by_id = {s["id"]: s for s in I["stories"]}
site = a.site_url.rstrip("/")
link_issue = f"{site}/?d={I['date']}" if site else ""
e = html.escape

INK, MUTED, ACC, LINE, BG = "#14201a", "#5d6b63", "#0d6b5c", "#d3dad1", "#f3f5f2"
font = "font-family:Georgia,'Times New Roman',serif"
sans = "font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif"

def h2(t): return f'<h2 style="{font};font-size:20px;color:{INK};margin:28px 0 8px;border-top:1px solid {LINE};padding-top:16px">{e(t)}</h2>'
def a_(url, text): return f'<a href="{e(url)}" style="color:{ACC}">{e(text)}</a>' if url else e(text)

parts, txt = [], []
parts.append(f'<p style="{sans};font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:{MUTED};margin:0">Rassegna HN · {e(I["date"])}</p>')
parts.append(f'<h1 style="{font};font-size:26px;line-height:1.2;color:{INK};margin:6px 0 10px">{e(E.get("headline", "Rassegna del giorno"))}</h1>')
parts.append(f'<p style="{sans};font-size:16px;line-height:1.55;color:{INK};margin:0">{e(E.get("intro", ""))}</p>')
txt += [f"RASSEGNA HN · {I['date']}", E.get("headline", ""), "", E.get("intro", ""), ""]

if E.get("try_today"):
    parts.append(h2("Da provare oggi")); txt.append("DA PROVARE OGGI")
    for t in E["try_today"]:
        s = by_id.get(t.get("story_id"), {})
        parts.append(f'<p style="{sans};font-size:15px;line-height:1.5;color:{INK};margin:0 0 12px"><b>{e(t.get("name", ""))}</b><br>{e(t.get("why", ""))}'
                     f'<br><span style="font-size:13px;color:{MUTED}">Da: {a_(s.get("hn_url"), s.get("title", ""))}</span></p>')
        txt += [f"- {t.get('name','')}: {t.get('why','')} ({s.get('hn_url','')})"]
    txt.append("")

if E.get("for_your_work"):
    parts.append(h2("Per il lavoro di marketing")); txt.append("PER IL LAVORO DI MARKETING")
    for f in E["for_your_work"]:
        s = by_id.get(f.get("story_id"), {})
        parts.append(f'<p style="{sans};font-size:15px;line-height:1.5;color:{INK};margin:0 0 12px">{a_(s.get("url") or s.get("hn_url"), s.get("title", ""))}<br>{e(f.get("note", ""))}</p>')
        txt += [f"- {s.get('title','')}: {f.get('note','')} ({s.get('hn_url','')})"]
    txt.append("")

parts.append(h2("Le storie del giorno")); txt.append("LE STORIE DEL GIORNO")
for s in I["stories"][:8]:
    badge = " · ricostruita dai commenti" if s.get("summary_source") == "commenti" else ""
    parts.append(f'<p style="{sans};font-size:15px;line-height:1.5;color:{INK};margin:0 0 14px">'
                 f'<span style="font-size:12px;color:{MUTED}">{e(s.get("label_name", ""))} · {s.get("points", 0)} punti · {s.get("comments", 0)} commenti{badge}</span><br>'
                 f'<b>{a_(s.get("url") or s.get("hn_url"), s["title"])}</b><br>{e(s.get("summary", ""))}<br>'
                 f'<span style="font-size:13px">{a_(s["hn_url"], "Discussione su HN")}</span></p>')
    txt += [f"- {s['title']} ({s.get('points',0)} punti, {s.get('comments',0)} commenti)", f"  {s.get('summary','')}", f"  {s['hn_url']}"]
txt.append("")

tools = [t for t in I.get("tools", []) if (t.get("relevance") or 0) >= 3]
if tools:
    parts.append(h2("Tool rilevanti")); txt.append("TOOL RILEVANTI")
    for t in tools[:8]:
        flag = " (link non verificato)" if t.get("url_verified") is False else ""
        parts.append(f'<p style="{sans};font-size:14px;line-height:1.5;color:{INK};margin:0 0 10px"><b>{a_(t.get("url"), t["name"])}</b>{e(flag)} · {e(t.get("what_it", ""))}<br>'
                     f'<span style="color:{MUTED}">{e(t.get("why_for_reader_it", ""))}</span></p>')
        txt += [f"- {t['name']}: {t.get('what_it','')} {t.get('url') or ''}{flag}"]
    txt.append("")

cod = I.get("comments_of_day", [])[:2]
if cod:
    parts.append(h2("Commenti del giorno")); txt.append("COMMENTI DEL GIORNO")
    for c in cod:
        parts.append(f'<blockquote style="{sans};font-size:14px;line-height:1.5;color:{INK};margin:0 0 12px;padding:8px 12px;border-left:3px solid #e2672a;background:{BG}">'
                     f'{e(c["quote"])}<br><span style="font-size:12px;color:{MUTED}">{a_(c.get("hn_url"), c.get("author", ""))} su {e(c.get("story_title", ""))}</span></blockquote>')
        txt += [f'"{c["quote"]}" ({c.get("author","")}, {c.get("hn_url","")})']
    txt.append("")

checks = (f"{st['candidates']} storie esaminate, {st['selected']} analizzate; {st['comments_fetched']} commenti letti su {st['comments_listed']} dichiarati; "
          f"notizie da articolo {v.get('from_article', 0)}, ricostruite dai commenti {v.get('from_comments', 0)}; "
          f"citazioni verificate {v.get('quote_ok', 0)}, scartate {v.get('quote_dropped', 0)}; link non verificati {v.get('tool_url_unverified', 0)}; classifica: {st['ranking_source']}.")
parts.append(f'<p style="{sans};font-size:12px;line-height:1.5;color:{MUTED};margin:28px 0 0;border-top:1px solid {LINE};padding-top:12px">Controlli: {e(checks)}'
             + (f'<br>{a_(link_issue, "Leggi l’edizione completa sul sito")}' if link_issue else "") + "</p>")
txt += ["Controlli: " + checks] + ([f"Edizione completa: {link_issue}"] if link_issue else [])

body = (f'<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        f'<body style="margin:0;padding:0;background:{BG}"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG}"><tr><td align="center" style="padding:20px 12px">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;background:#ffffff;border:1px solid {LINE};border-radius:8px"><tr><td style="padding:24px 22px">'
        + "".join(parts) + "</td></tr></table></td></tr></table></body></html>")
os.makedirs(a.out_dir, exist_ok=True)
open(os.path.join(a.out_dir, "email.html"), "w").write(body)
open(os.path.join(a.out_dir, "email.txt"), "w").write("\n".join(txt))
open(os.path.join(a.out_dir, "subject.txt"), "w").write(f"Rassegna HN {I['date']} · {E.get('headline', '')}"[:150])
print("ok", len(body))
