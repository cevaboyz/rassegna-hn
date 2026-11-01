#!/usr/bin/env python3
"""Render one issue as an email: HTML with inline styles (email clients ignore <style>) plus a plain-text part.

Usage: python3 scripts/render_email.py data/issues/YYYY-MM-DD.json --site-url URL --out-dir OUT
Writes OUT/subject.txt, OUT/email.html, OUT/email.txt. Standard library only, so it runs on a bare GitHub runner.

Layout choices (for a quick morning read, not a wall of text):
- every section has an emoji header and its own white card on a grey background;
- each story is a small card: label chip, title, one meta line (points, comments, mood), a short summary, one link;
- long texts are cut at a sentence boundary; the full version stays on the site;
- tables + inline styles only, because Gmail and Outlook drop <style> blocks and flexbox.
Every field is read with .get(): a partial issue (fallback editorial, missing tools) still renders.
"""
import argparse, json, html, os, re

ap = argparse.ArgumentParser()
ap.add_argument("issue"); ap.add_argument("--site-url", default=""); ap.add_argument("--out-dir", default=".")
a = ap.parse_args()
I = json.load(open(a.issue)); E = I.get("editorial") or {}; st = I.get("stats") or {}; v = st.get("validation") or {}
stories = I.get("stories") or []
by_id = {s.get("id"): s for s in stories}
site = a.site_url.rstrip("/")
link_issue = f"{site}/?d={I['date']}" if site else ""
e = html.escape

# palette and fonts: the portfolio's night theme (andreacastagna.info).
# Web fonts load in Apple Mail and some clients; elsewhere the fallbacks keep the same mono/grotesk feel.
INK, MUTED, ACC, LINE, BG, SOFT, WARM = "#e6fff6", "#8e9bbd", "#00ffa3", "#2e3470", "#060914", "#121a36", "#ff2e88"
PANEL = "#0b1022"
sans = "font-family:'IBM Plex Mono',Menlo,Consolas,'Courier New',monospace"
serif = "font-family:'Space Grotesk','Helvetica Neue',Helvetica,Arial,sans-serif"

LABEL_EMOJI = {
    "dev_tools": "🛠️", "ai_society": "🤖", "ai_models": "🧠", "ai_industry": "🏭", "startups_business": "🚀", "big_tech": "🏢",
    "policy_law": "⚖️", "ai_agents_coding": "🧑‍💻", "science": "🔬", "culture_history": "📜", "hardware": "🔌",
    "security_privacy": "🔒", "os_systems": "💻", "games_creative": "🎮", "web_browsers": "🌐", "programming_langs": "⌨️",
    "energy_env": "🌱", "software_eng": "🏗️", "cloud_devops": "☁️", "data_db": "🗄️", "health_medicine": "🩺",
    "work_life": "🧘", "marketing_web_biz": "📈", "society_trends": "🌍", "video_media": "🎬",
}
TONE = {"entusiasta": "🤩 entusiasta", "positivo": "🙂 positivo", "diviso": "⚖️ diviso", "scettico": "🤨 scettico",
        "negativo": "👎 negativo", "neutro": "😐 neutro"}


def short(text, limit=260):
    """Cut at the last sentence end before `limit` characters; fall back to a word boundary."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    m = list(re.finditer(r"[.!?](\s|$)", cut))
    if m and m[-1].end() > limit * 0.5:
        return cut[:m[-1].end()].strip()
    return cut.rsplit(" ", 1)[0].rstrip(",;:") + "…"


def a_(url, text, color=ACC, bold=False):
    w = "font-weight:600;" if bold else ""
    return f'<a href="{e(url)}" style="color:{color};{w}text-decoration:none">{e(text)}</a>' if url else e(text)


def button(url, text):
    if not url:
        return ""
    return (f'<a href="{e(url)}" style="{sans};display:inline-block;font-size:12px;font-weight:600;color:{ACC};'
            f'text-decoration:none;border:1px solid {ACC};padding:5px 10px;margin:8px 6px 0 0">[ {e(text)} ]</a>')


def chip(text):
    return (f'<span style="{sans};display:inline-block;font-size:11px;color:{INK};background:{SOFT};border:1px solid {LINE};'
            f'padding:1px 7px;margin:0 6px 4px 0">{e(text)}</span>')


SEC = [0]  # running number for the terminal-style "// 01" labels


def section(emoji, title, inner):
    SEC[0] += 1
    return (f'<tr><td style="padding:0 0 14px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{PANEL}" '
            f'style="background:{PANEL};border:1px solid {LINE}"><tr><td style="padding:18px 18px 8px">'
            f'<p style="{sans};font-size:11px;letter-spacing:.06em;color:{WARM};margin:0 0 2px">// {SEC[0]:02d}</p>'
            f'<p style="{serif};font-size:19px;font-weight:700;color:{INK};margin:0 0 14px">{emoji}&nbsp; {e(title)}</p>'
            f'{inner}</td></tr></table></td></tr>')


def item(inner, last=False):
    border = "" if last else f"border-bottom:1px dashed {LINE};"
    return f'<div style="{border}padding:0 0 12px;margin:0 0 12px">{inner}</div>'


def p(text, size=15, color=INK, extra=""):
    return f'<p style="{sans};font-size:{size - 1}px;line-height:1.6;color:{color};margin:0 0 4px;{extra}">{text}</p>'


tool_url = {}
for t in I.get("tools") or []:
    if t.get("url") and t.get("url_verified") and t.get("name"):
        tool_url.setdefault(t["name"].lower(), t["url"])

sections, txt = [], []
date_it = "/".join(reversed(I["date"].split("-")))

# ---- header
header = (f'<tr><td style="padding:4px 4px 16px">'
          f'<p style="{sans};font-size:12px;letter-spacing:.04em;color:{MUTED};margin:0">// rassegna_hn.log · {e(date_it)}</p>'
          f'<p style="{serif};font-size:30px;font-weight:700;letter-spacing:-.02em;color:{INK};margin:4px 0 0">Rassegna <span style="color:{ACC}">HN</span><span style="color:{WARM}">_</span></p>'
          f'<h1 style="{serif};font-size:24px;line-height:1.25;font-weight:700;color:{INK};margin:14px 0 12px">{e(E.get("headline") or "Rassegna del giorno")}</h1>')
if E.get("intro"):
    header += p(e(E["intro"]), 16, INK, "line-height:1.6")
n_comm = sum(1 for s in stories if s.get("summary_source") == "commenti")
header += p(f'🗂️ {len(stories)} storie · 💬 {st.get("comments_fetched", 0)} commenti letti'
            + (f' · {a_(link_issue, "apri sul sito ↗")}' if link_issue else ""), 13, MUTED, "margin-top:10px")
header += "</td></tr>"
txt += [f"📰 RASSEGNA HN · {date_it}", "", E.get("headline") or "Rassegna del giorno", ""]
if E.get("intro"):
    txt += [E["intro"], ""]

# ---- try today
tt = E.get("try_today") or []
if tt:
    rows = []
    txt += ["🧪 DA PROVARE OGGI", ""]
    for k, t in enumerate(tt):
        s = by_id.get(t.get("story_id"), {})
        url = tool_url.get((t.get("name") or "").lower())
        inner = (p(f'<b>{e(t.get("name", ""))}</b>', 17, INK, serif) + p(e(short(t.get("why"), 320)), 14, INK)
                 + button(url, "Apri ↗") + button(s.get("hn_url"), "💬 Discussione"))
        rows.append(item(inner, k == len(tt) - 1))
        txt += [f"• {t.get('name', '')}", f"  {short(t.get('why'), 320)}"] + ([f"  {url}"] if url else []) + [f"  {s.get('hn_url', '')}", ""]
    sections.append(section("🧪", "Da provare oggi", "".join(rows)))

# ---- for your work
fw = E.get("for_your_work") or []
if fw:
    rows = []
    txt += ["💼 PER IL TUO LAVORO", ""]
    for k, f in enumerate(fw):
        s = by_id.get(f.get("story_id"), {})
        inner = p(a_(s.get("url") or s.get("hn_url"), s.get("title", ""), INK, True), 16, INK, serif) + p(e(short(f.get("note"), 320)), 14, MUTED)
        rows.append(item(inner, k == len(fw) - 1))
        txt += [f"• {s.get('title', '')}", f"  {short(f.get('note'), 320)}", ""]
    sections.append(section("💼", "Per il tuo lavoro", "".join(rows)))

# ---- top stories
top = stories[:8]
if top:
    rows = []
    txt += ["🔥 LE STORIE DEL GIORNO", ""]
    for k, s in enumerate(top):
        emo = LABEL_EMOJI.get(s.get("label"), "📌")
        meta = f'▲ {s.get("points", 0)} · 💬 {s.get("comments", 0)}'
        if s.get("tone") in TONE:
            meta += f' · {TONE[s["tone"]]}'
        badge = chip("🧩 ricostruita dai commenti") if s.get("summary_source") == "commenti" else ""
        # the chip already says "ricostruita dai commenti": drop the prefix and restore the capital letter
        summary = short(re.sub(r"^Ricostruita dai commenti:\s*", "", s.get("summary") or ""), 280)
        summary = summary[:1].upper() + summary[1:]
        inner = (chip(f'{emo} {s.get("label_name", "")}') + badge
                 + p(a_(s.get("url") or s.get("hn_url"), s.get("title", ""), INK, True), 17, INK, serif + ";margin-top:4px")
                 + p(e(meta), 12, MUTED)
                 + (p(e(summary), 14, INK, "margin-top:6px") if summary else "")
                 + p(a_(s.get("hn_url"), "Leggi la discussione →"), 13, ACC, "margin-top:4px"))
        rows.append(item(inner, k == len(top) - 1))
        txt += [f"{emo} {s.get('title', '')}", f"   ▲ {s.get('points', 0)} · 💬 {s.get('comments', 0)}"
                + (" · ricostruita dai commenti" if badge else ""), f"   {summary}", f"   {s.get('hn_url', '')}", ""]
    more = len(stories) - len(top)
    if more > 0 and link_issue:
        rows.append(p(a_(link_issue, f"…e altre {more} storie sul sito →"), 14, ACC, "margin:0 0 10px"))
    sections.append(section("🔥", "Le storie del giorno", "".join(rows)))

# ---- tools
tools = [t for t in I.get("tools") or [] if (t.get("relevance") or 0) >= 3][:6]
if tools:
    rows = []
    txt += ["🛠️ TOOL DA TENERE D'OCCHIO", ""]
    for k, t in enumerate(tools):
        flag = " ⚠️ link da verificare" if t.get("url_verified") is False else ""
        inner = (p(f'{a_(t.get("url"), t.get("name", ""), INK, True)}<span style="color:{MUTED};font-size:12px">{e(flag)}</span>', 15)
                 + p(e(short(t.get("what_it"), 180)), 14, INK)
                 + (p("👉 " + e(short(t.get("why_for_reader_it"), 200)), 13, MUTED) if t.get("why_for_reader_it") else ""))
        rows.append(item(inner, k == len(tools) - 1))
        txt += [f"• {t.get('name', '')}{flag}: {short(t.get('what_it'), 180)}"] + ([f"  {t['url']}"] if t.get("url") else []) + [""]
    sections.append(section("🛠️", "Tool da tenere d'occhio", "".join(rows)))

# ---- comments of the day
cod = (I.get("comments_of_day") or [])[:2]
if cod:
    rows = []
    txt += ["💬 COMMENTI DEL GIORNO", ""]
    for c in cod:
        rows.append(f'<div style="{sans};font-size:14px;line-height:1.55;color:{INK};margin:0 0 12px;padding:10px 14px;'
                    f'border-left:2px solid {WARM};background:{SOFT}">“{e(c.get("quote", ""))}”'
                    f'<br><span style="font-size:12px;color:{MUTED}">— {a_(c.get("hn_url"), c.get("author", ""), MUTED)} su {e(c.get("story_title", ""))}</span></div>')
        txt += [f'“{c.get("quote", "")}”', f"  — {c.get('author', '')}, {c.get('hn_url', '')}", ""]
    sections.append(section("💬", "Commenti del giorno", "".join(rows)))

# ---- watch
watch = E.get("watch") or []
if watch:
    lis = "".join(f'<li style="margin:0 0 8px">{e(short(w, 240))}</li>' for w in watch)
    sections.append(section("👀", "Da seguire", f'<ul style="{sans};font-size:14px;line-height:1.5;color:{INK};margin:0 0 10px;padding-left:20px">{lis}</ul>'))
    txt += ["👀 DA SEGUIRE", ""] + [f"• {short(w, 240)}" for w in watch] + [""]

# ---- footer
checks = (f"{st.get('candidates', 0)} storie esaminate, {st.get('selected', len(stories))} analizzate · "
          f"{v.get('from_article', 0)} dall'articolo, {n_comm} ricostruite dai commenti · "
          f"citazioni verificate {v.get('quote_ok', 0)}, scartate {v.get('quote_dropped', 0)} · link non verificati {v.get('tool_url_unverified', 0)}")
footer = (f'<tr><td style="padding:6px 6px 0">'
          + p("✅ Controlli: " + e(checks), 12, MUTED)
          + p("Contenuti generati automaticamente da fonti pubbliche: possono contenere errori. Le affermazioni sono attribuite alle fonti.", 12, MUTED)
          + (p(a_(link_issue, "📖 Leggi l'edizione completa sul sito"), 13, ACC, "margin-top:8px") if link_issue else "")
          + "</td></tr>")
txt += ["✅ Controlli: " + checks] + ([f"📖 Edizione completa: {link_issue}"] if link_issue else [])

preheader = short(E.get("intro") or E.get("headline") or "", 140)
body = (f'<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta name="color-scheme" content="dark"><meta name="supported-color-schemes" content="dark">'
        f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Space+Grotesk:wght@500;700&display=swap">'
        f'<title>{e(E.get("headline") or "Rassegna HN")}</title></head>'
        f'<body bgcolor="{BG}" style="margin:0;padding:0;background:{BG}">'
        # hidden preheader: the preview line shown next to the subject in most inboxes
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0">{e(preheader)}</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{BG}" style="background:{BG}"><tr><td align="center" style="padding:20px 10px">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px">'
        + header + "".join(sections) + footer
        + "</table></td></tr></table></body></html>")
os.makedirs(a.out_dir, exist_ok=True)
open(os.path.join(a.out_dir, "email.html"), "w").write(body)
open(os.path.join(a.out_dir, "email.txt"), "w").write("\n".join(txt))
open(os.path.join(a.out_dir, "subject.txt"), "w").write(f"📰 Rassegna HN {date_it} · {E.get('headline') or ''}"[:150])
print("ok", len(body))
