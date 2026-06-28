#!/usr/bin/env python3
"""
Build the static sermon-notes website from the markdown files in notes/.

Each file in notes/ is one sermon: a small "front-matter" block (title, speaker,
church, date, source) followed by the notes in markdown. This script reads them
all and regenerates the site/ folder from scratch, an index page with the latest
sermon shown in full at the top and a dated archive of every sermon below, plus
one page per sermon. Plain HTML + CSS; no server, no database.

Run it any time you add or edit a notes file:
    python build_site.py
"""

import datetime
import html
import os
import re
import shutil

import markdown

ROOT = os.path.dirname(os.path.abspath(__file__))
NOTES_DIR = os.path.join(ROOT, "notes")
SITE_DIR = os.path.join(ROOT, "site")
SERMONS_DIR = os.path.join(SITE_DIR, "sermons")

SITE_TITLE = "Sermon Notes"

STYLE_CSS = """\
:root{
  --bg:#faf7f1;
  --surface:#ffffff;
  --ink:#2a2724;
  --muted:#6b645c;
  --accent:#9a3b2e;
  --line:#e7e0d6;
  --maxw:42rem;
}
*{box-sizing:border-box;}
html{font-size:112.5%;}
body{
  margin:0;
  background:var(--bg);
  color:var(--ink);
  font-family:Georgia,'Times New Roman',serif;
  line-height:1.65;
}
.site-header{border-bottom:1px solid var(--line);background:var(--surface);}
a.site-title{
  display:block;
  max-width:var(--maxw);
  margin:0 auto;
  padding:1.1rem 1.25rem;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  font-weight:600;font-size:1.05rem;letter-spacing:.02em;
  color:var(--ink);text-decoration:none;
}
main{max-width:var(--maxw);margin:0 auto;padding:2rem 1.25rem 3rem;}
.eyebrow{
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  text-transform:uppercase;letter-spacing:.12em;font-size:.72rem;
  color:var(--accent);margin:0 0 .4rem;
}
.sermon-title{font-size:2rem;line-height:1.2;margin:.1rem 0 .3rem;}
.sermon-meta{color:var(--muted);font-style:italic;margin:0 0 1.2rem;}
.player{
  position:relative;width:100%;aspect-ratio:16/9;margin:.2rem 0 1rem;
  background:#000;border-radius:8px;overflow:hidden;scroll-margin-top:1rem;
}
.player iframe{position:absolute;inset:0;width:100%;height:100%;border:0;}
.sermon h2{
  font-size:1.15rem;margin:1.8rem 0 .4rem;padding-bottom:.25rem;
  border-bottom:1px solid var(--line);
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
}
.sermon ol{padding-left:1.3rem;}
.sermon ol li{margin:.6rem 0;}
.sermon a{color:var(--accent);}
.ts{
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  font-size:.78rem;color:var(--accent);text-decoration:none;white-space:nowrap;
}
.ts:hover{text-decoration:underline;}
.home-sub{color:var(--muted);font-size:1rem;margin:.2rem 0 1.6rem;}
.archive-list{list-style:none;padding:0;margin:0;}
.archive-list li{border-bottom:1px solid var(--line);}
.archive-list li:first-child{border-top:1px solid var(--line);}
.archive-list a{display:block;padding:1.15rem 0;text-decoration:none;color:var(--ink);}
.archive-list a:hover .a-title{color:var(--accent);}
.a-date{
  display:block;margin-bottom:.2rem;color:var(--muted);font-size:.8rem;letter-spacing:.02em;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
}
.a-title{display:block;font-size:1.25rem;line-height:1.25;margin-bottom:.3rem;}
.a-theme{display:block;color:var(--muted);font-size:.97rem;line-height:1.45;margin-bottom:.35rem;}
.a-speaker{
  display:block;color:var(--muted);font-size:.8rem;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
}
.back-link{
  display:inline-block;margin-bottom:1.5rem;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  font-size:.85rem;color:var(--muted);text-decoration:none;
}
.site-footer{
  max-width:var(--maxw);margin:0 auto;padding:2rem 1.25rem 3rem;
  color:var(--muted);font-size:.8rem;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
}
@media(max-width:480px){
  .sermon-title{font-size:1.6rem;}
}
"""


def parse_note(path):
    """Read one notes file into a dict (front-matter + rendered HTML body)."""
    with open(path, encoding="utf-8") as f:
        text = f.read()

    meta = {}
    body = text
    if text.startswith("---"):
        _, front, body = text.split("---", 2)
        for line in front.strip().splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                meta[key.strip().lower()] = value.strip()

    slug = os.path.splitext(os.path.basename(path))[0]
    return {
        "slug": slug,
        "title": meta.get("title", slug),
        "date": meta.get("date", ""),
        "speaker": meta.get("speaker", ""),
        "church": meta.get("church", ""),
        "source": meta.get("source", ""),
        "theme": meta.get("theme", ""),
        "body_html": markdown.markdown(body.strip()),
    }


PLAYER_SCRIPTS = """
<script src="https://www.youtube.com/iframe_api"></script>
<script>
var ytPlayer, ytReady = false;
function onYouTubeIframeAPIReady(){
  var el = document.getElementById('yt-player');
  if(!el){ return; }
  ytPlayer = new YT.Player('yt-player', {
    videoId: el.dataset.video,
    playerVars: { rel: 0, modestbranding: 1 },
    events: { onReady: function(){ ytReady = true; } }
  });
}
document.addEventListener('click', function(e){
  var a = e.target.closest ? e.target.closest('a.ts') : null;
  if(!a){ return; }
  var s = a.getAttribute('data-seconds');
  if(ytReady && ytPlayer && s){
    e.preventDefault();
    ytPlayer.seekTo(Number(s), true);
    ytPlayer.playVideo();
    var p = document.querySelector('.player');
    if(p){ p.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
  }
});
</script>
"""


def video_id_from_source(source):
    """Pull the 11-char YouTube video ID from a source URL (or '' if none)."""
    if not source:
        return ""
    match = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", source)
    if match:
        return match.group(1)
    match = re.search(r"(?:youtu\.be/|/live/|/embed/|/shorts/)([A-Za-z0-9_-]{11})", source)
    if match:
        return match.group(1)
    return ""


def format_time(seconds):
    """123 -> '2:03'; 3725 -> '1:02:05'."""
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def link_timestamps(body_html, source):
    """Turn [t=SECONDS] markers in the notes into links that jump the video to
    that moment. If there's no source video, just strip the markers."""
    if not source:
        return re.sub(r"\s*\[t=\d+\]", "", body_html)

    joiner = "&" if "?" in source else "?"

    def replace(match):
        seconds = match.group(1)
        label = format_time(seconds)
        url = html.escape(f"{source}{joiner}t={seconds}s")
        return (
            f' <a class="ts" href="{url}" target="_blank" rel="noopener" '
            f'data-seconds="{seconds}" title="Watch from {label}">{label}</a>'
        )

    return re.sub(r"\s*\[t=(\d+)\]", replace, body_html)


def format_date(value):
    """Turn 2026-06-28 into '28 June 2026'; leave anything unexpected as-is."""
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d").strftime("%-d %B %Y")
    except ValueError:
        return value


def page(title, inner, depth):
    """Wrap inner HTML in the shared page shell. depth=1 for /sermons/* pages."""
    prefix = "../" if depth else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="{prefix}style.css">
</head>
<body>
<header class="site-header"><a class="site-title" href="{prefix}index.html">{html.escape(SITE_TITLE)}</a></header>
<main>
{inner}
</main>
</body>
</html>
"""


def article_html(note, heading_tag):
    """The sermon write-up itself: title, meta line, notes body, source link."""
    bits = ['<article class="sermon">']
    bits.append(
        f'<{heading_tag} class="sermon-title">{html.escape(note["title"])}</{heading_tag}>'
    )
    meta_line = " · ".join(
        part
        for part in (note["speaker"], note["church"], format_date(note["date"]))
        if part
    )
    if meta_line:
        bits.append(f'<p class="sermon-meta">{html.escape(meta_line)}</p>')
    video_id = video_id_from_source(note["source"])
    if video_id:
        bits.append(
            '<div class="player">'
            f'<div id="yt-player" data-video="{html.escape(video_id)}"></div></div>'
        )
    bits.append(link_timestamps(note["body_html"], note["source"]))
    bits.append("</article>")
    return "\n".join(bits)


def build():
    notes = [
        parse_note(os.path.join(NOTES_DIR, name))
        for name in os.listdir(NOTES_DIR)
        if name.endswith(".md")
    ]
    if not notes:
        print("No notes found in notes/. Add a sermon file and run again.")
        return

    # Newest first.
    notes.sort(key=lambda n: n["date"], reverse=True)

    # Start the site/ folder fresh so deleted notes don't linger.
    if os.path.isdir(SITE_DIR):
        shutil.rmtree(SITE_DIR)
    os.makedirs(SERMONS_DIR)

    with open(os.path.join(SITE_DIR, "style.css"), "w", encoding="utf-8") as f:
        f.write(STYLE_CSS)

    # One page per sermon.
    for note in notes:
        inner = '<a class="back-link" href="../index.html">← All sermon notes</a>\n'
        inner += article_html(note, "h1")
        if video_id_from_source(note["source"]):
            inner += PLAYER_SCRIPTS
        out = page(note["title"], inner, depth=1)
        with open(os.path.join(SERMONS_DIR, note["slug"] + ".html"), "w", encoding="utf-8") as f:
            f.write(out)

    # The index: a clickable list of every sermon, newest first. Nothing is
    # opened by default, the reader taps a date to read that week's notes.
    church = notes[0]["church"]
    inner = ""
    if church:
        inner += f'<p class="home-sub">Weekly messages from {html.escape(church)}</p>\n'
    inner += '<ul class="archive-list">\n'
    for note in notes:
        item = f'<li><a href="sermons/{note["slug"]}.html">'
        item += f'<span class="a-date">{format_date(note["date"])}</span>'
        item += f'<span class="a-title">{html.escape(note["title"])}</span>'
        if note["theme"]:
            item += f'<span class="a-theme">{html.escape(note["theme"])}</span>'
        if note["speaker"]:
            item += f'<span class="a-speaker">{html.escape(note["speaker"])}</span>'
        item += "</a></li>\n"
        inner += item
    inner += "</ul>\n"
    with open(os.path.join(SITE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(page(SITE_TITLE, inner, depth=0))

    print(f"Built site/ with {len(notes)} sermon(s). Open site/index.html.")


if __name__ == "__main__":
    build()
