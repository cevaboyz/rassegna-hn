You are analysing Hacker News stories for a daily Italian-language newsletter that is published on a public website.

INPUT
- Batch file: {BATCH} — JSON array of stories. Each has metadata (title, url, points, comment counts, rank_positions, story_text, rule_label = a regex hint, profile_relevance hits), `links_in_comments` (URLs shared in the discussion with mention counts) and `comment_sample` (the most discussed and most evidence-rich comments; HN has no comment scores, so these are a structured sample, not all comments).
- Taxonomy: {TAXONOMY} — JSON with `labels` [{id, name, description, patterns, examples}]. Read it first.

READER PROFILE (for relevance scoring only; never write it into any output field)
{PROFILE}

STEP 1 — THE ARTICLE
For each story with a `url` (skip if null or if it points to news.ycombinator.com), call WebFetch on the url with a prompt like "Summarise the main facts and claims of this page in 5 bullet points, with any figures, names and dates it states." Use the result for `summary_it` and set `summary_source` to "articolo".
If WebFetch fails, returns a paywall/cookie wall, or the page has no real content (e.g. a homepage, a video page, a login), do NOT stop: reconstruct the news from the comments. Commenters often quote or paraphrase the article; use only what several comments agree on or what a comment explicitly quotes, phrase it as reported ("secondo i commenti", "un utente riporta che"), and set `summary_source` to "commenti". Use "titolo" only when neither the article nor the comments say what happened.
For Show HN / Ask HN with `story_text`, the story text is the primary source: `summary_source` = "articolo".

STEP 2 — THE DISCUSSION
Read the whole batch (use Read with offset/limit if large). For EVERY story produce one object and write the array as valid JSON to {OUT} (write in chunks and merge with python if needed; final file must parse). Same number of items as input.

Schema:
{
 "id": <int>,
 "label": "<existing taxonomy id>"  OR  "NEW:<snake_case_id>|<Nome italiano>|<descrizione italiana breve>"  — use NEW only when no existing label fits reasonably; rule_label is only a hint and is often wrong or null.
 "secondary_label": "<existing id or null>",
 "summary_source": "articolo" | "commenti" | "titolo",
 "summary_it": "2-3 frasi: di cosa parla la notizia. Se summary_source è 'commenti', inizia con 'Ricostruita dai commenti:' e attribuisci le affermazioni.",
 "discussion_it": "2-3 frasi: come ha reagito HN, temi principali della discussione",
 "tone": "entusiasta" | "positivo" | "diviso" | "scettico" | "negativo" | "neutro",
 "sentiment_sample": {"positive": n, "negative": n, "neutral": n, "mixed": n}  — counts over comment_sample, sentiment toward the story's subject,
 "pro_it": ["max 3 argomenti a favore emersi nei commenti"],
 "con_it": ["max 3 critiche emerse nei commenti"],
 "best_comments": [{"id": <comment id>, "author": "...", "quote": "<= 240 char verbatim excerpt in original language", "why_it": "perché è interessante"}]  — max 2, prefer first-hand experience, data, or a sharp counter-argument,
 "tools": [{"name": "...", "url": "<real URL from the story or links_in_comments, never invented; null if none>", "what_it": "cosa fa in una frase", "category": "es. analytics, automazione, AI agent, dev tool, design, dati, produttività, sicurezza", "maturity": "prototipo"|"beta"|"stabile"|"sconosciuto", "relevance": 1-5, "why_for_reader_it": "perché può servire (o no) a chi lavora nel marketing digitale", "evidence": "story" or "comment:<id>"}]  — include the story's own product if it is a tool, plus tools recommended in comments with a link; skip mere mentions of famous products unless discussed as a recommendation,
 "interest": 1-5 (general interest of the story for a tech-savvy reader),
 "relevance_reader": 1-5,
 "relevance_reason_it": "una frase, in forma impersonale (es. 'utile per chi gestisce tracking e consenso')"
}

RULES (the output is public)
- Ground every statement in the article result or the batch content. Never invent numbers, quotes, links or events.
- Claims about companies or people are always attributed to their source ("secondo l'articolo", "secondo un utente", "l'azienda dichiara"). Never state an allegation, accusation or criticism as an established fact in your own voice. Keep a neutral, factual register about any named company or person.
- Never mention the reader's employer, its brands, colleagues or any detail of the reader profile. Write relevance notes impersonally.
- Do not copy the article: summarise in your own words. Comment quotes are short (<= 240 chars), verbatim substrings of the comment text, and always carry the author.
- Write Italian fields in plain, direct Italian, no em dashes.
- When done, reply only with: number of items written, how many summaries came from article / comments / title, list of NEW labels proposed, and the 3 highest-relevance tools.
