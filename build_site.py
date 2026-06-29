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
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');
:root{
  --bg:#F4F3EE;
  --ink:#16160F;
  --sage:#1F4D43;
  --muted:#65615a;
  --muted2:#8a8378;
  --line:#d9d6cc;
  --maxw:44rem;
}
*{box-sizing:border-box;}
body{
  margin:0;background:var(--bg);color:var(--ink);
  font-family:'Space Grotesk',system-ui,sans-serif;line-height:1.6;
}
.site-header{
  border-bottom:1px solid var(--line);padding:1.1rem 1.5rem;
  display:flex;align-items:center;justify-content:space-between;
}
a.site-title{
  font-size:1rem;font-weight:700;letter-spacing:-.01em;
  color:var(--ink);text-decoration:none;
}
a.back-link{
  font-size:.85rem;font-weight:500;color:var(--muted2);text-decoration:none;
}
a.back-link:hover{color:var(--sage);}
main{max-width:var(--maxw);margin:0 auto;padding:2rem 1.5rem 4rem;}
.home-eyebrow{
  font-size:.72rem;font-weight:700;letter-spacing:.16em;
  text-transform:uppercase;color:var(--sage);margin-bottom:1.4rem;
}
.archive-list{list-style:none;padding:0;margin:0;}
.archive-list li{border-top:1px solid var(--line);}
.archive-list li:last-child{border-bottom:1px solid var(--line);}
.archive-list a{
  display:flex;gap:1.5rem;padding:1.3rem 0;
  text-decoration:none;color:var(--ink);align-items:flex-start;
}
.archive-list a:hover .a-title{color:var(--sage);}
.a-date{
  font-size:.8rem;font-weight:500;color:var(--muted2);
  white-space:nowrap;min-width:7rem;flex-shrink:0;padding-top:.15rem;
}
.a-content{flex:1;}
.a-title{display:block;font-size:1.15rem;font-weight:700;line-height:1.2;margin-bottom:.3rem;}
.a-theme{display:block;font-size:.9rem;line-height:1.5;color:var(--muted);margin-bottom:.4rem;}
.a-speaker{display:block;font-size:.78rem;font-weight:500;color:var(--muted2);}
.sermon-eyebrow{
  font-size:.72rem;font-weight:700;letter-spacing:.16em;
  text-transform:uppercase;color:var(--sage);margin-bottom:.6rem;
}
.sermon-title{
  font-size:2.4rem;font-weight:700;line-height:1.05;
  letter-spacing:-.03em;margin:.1rem 0 .5rem;
}
.sermon-meta{font-size:.9rem;font-weight:500;color:var(--muted2);margin:0 0 1.5rem;}
.player{
  position:relative;width:100%;aspect-ratio:16/9;
  margin:.5rem 0 2rem;background:#000;overflow:hidden;scroll-margin-top:1rem;
}
.player iframe{position:absolute;inset:0;width:100%;height:100%;border:0;}
.sermon h2{
  font-size:.72rem;font-weight:700;letter-spacing:.16em;
  text-transform:uppercase;color:var(--sage);
  border:none;padding:0;margin:2rem 0 .75rem;
}
.sermon h2::after{content:'';display:block;height:1px;background:var(--line);margin-top:.5rem;}
.sermon p{font-size:1rem;line-height:1.7;color:var(--muted);margin:.4rem 0;}
.sermon ol{padding-left:0;list-style:none;margin:.5rem 0;counter-reset:kp;}
.sermon ol li{
  border-bottom:1px solid var(--line);padding:1.1rem 0;
  display:flex;gap:1.2rem;align-items:flex-start;counter-increment:kp;
}
.sermon ol li::before{
  content:counter(kp);font-size:1.8rem;font-weight:700;
  color:var(--sage);line-height:.95;min-width:1.8rem;
  letter-spacing:-.03em;flex-shrink:0;
}
.sermon ol li strong{font-size:1rem;font-weight:700;}
.sermon ol li p{margin:.3rem 0 0;font-size:.95rem;color:var(--muted);}
.sermon a{color:var(--sage);}
.ts{
  display:inline-flex;align-items:center;gap:3px;
  font-size:.7rem;font-weight:700;color:#fff!important;background:var(--sage);
  padding:2px 7px 2px 5px;border-radius:4px;
  text-decoration:none;white-space:nowrap;margin-left:.4rem;vertical-align:middle;
}
.ts::before{content:'▶';font-size:.55rem;}
.ts:hover{opacity:.8;}
@media(max-width:520px){
  .sermon-title{font-size:1.8rem;}
  .a-date{min-width:5.5rem;font-size:.75rem;}
  .site-header{padding:.9rem 1.1rem;}
  main{padding:1.5rem 1.1rem 3rem;}
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


def page(title, inner, depth, header_right=""):
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
<header class="site-header">
  <a class="site-title" href="{prefix}index.html">{html.escape(SITE_TITLE)}</a>
  {header_right}
</header>
<main>
{inner}
</main>
</body>
</html>
"""


def article_html(note, heading_tag):
    """The sermon write-up itself: title, meta line, notes body, source link."""
    bits = ['<article class="sermon">']
    bits.append(f'<p class="sermon-eyebrow">{html.escape(format_date(note["date"]))}</p>')
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
        inner = article_html(note, "h1")
        if video_id_from_source(note["source"]):
            inner += PLAYER_SCRIPTS
        back = '<a class="back-link" href="../index.html">← All sermon notes</a>'
        out = page(note["title"], inner, depth=1, header_right=back)
        with open(os.path.join(SERMONS_DIR, note["slug"] + ".html"), "w", encoding="utf-8") as f:
            f.write(out)

    # The index: a clickable list of every sermon, newest first. Nothing is
    # opened by default, the reader taps a date to read that week's notes.
    church = notes[0]["church"]
    inner = '<p class="home-eyebrow">Weekly Messages</p>\n'
    inner += '<ul class="archive-list">\n'
    for note in notes:
        item = f'<li><a href="sermons/{note["slug"]}.html">'
        item += f'<span class="a-date">{format_date(note["date"])}</span>'
        item += '<div class="a-content">'
        item += f'<span class="a-title">{html.escape(note["title"])}</span>'
        if note["theme"]:
            item += f'<span class="a-theme">{html.escape(note["theme"])}</span>'
        if note["speaker"]:
            item += f'<span class="a-speaker">{html.escape(note["speaker"])}</span>'
        item += "</div></a></li>\n"
        inner += item
    inner += "</ul>\n"
    with open(os.path.join(SITE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(page(SITE_TITLE, inner, depth=0))

    print(f"Built site/ with {len(notes)} sermon(s). Open site/index.html.")


if __name__ == "__main__":
    build()
