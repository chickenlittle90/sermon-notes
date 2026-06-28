#!/usr/bin/env python3
"""
Sermon Notes Automation

Takes a YouTube video URL, pulls the auto-generated transcript, asks Claude to
write sermon notes (with a timestamp on each key point), saves them as a page in
notes/, and rebuilds the static website so the new sermon appears on it.

Usage:
    python generate_notes.py "https://www.youtube.com/watch?v=XXXXXXXXXXX" [YYYY-MM-DD]

The optional date is the service date (defaults to today). Requires the
ANTHROPIC_API_KEY environment variable to be set.
"""

import datetime
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import warnings

# macOS's system Python links against LibreSSL, which makes urllib3 emit a noisy
# (harmless) warning on import. Silence it so the script's output stays clean.
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

import anthropic
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

# ---------------------------------------------------------------------------
# The notes prompt. This shapes every sermon's notes, tweak it freely.
# ---------------------------------------------------------------------------
NOTES_PROMPT = """You are summarising a church sermon into clear, faithful notes for \
a general churchgoer to review and reflect on afterward. You will receive an \
auto-generated YouTube transcript that may contain errors and often includes \
non-sermon content (welcome, worship lyrics, announcements, prayer ministry). \
Identify and focus only on the main teaching. Ignore the surrounding service content.

Correct obvious misheard biblical names and scripture references from context. Do not \
invent any reference you are not confident about.

Begin your response with exactly these two lines, then a blank line, then the notes:
TITLE: a short, clear sermon title based on the message itself, not the raw video title
SPEAKER: the preacher's name, or Unknown if you cannot tell from the transcript

Then produce the notes using exactly these Markdown headings, in this order:

## Theme
One sentence describing what the sermon is about.

## Main Scriptures
The key passages referenced.

## Summary
3 to 5 sentences capturing the core message.

## Key Points
A numbered list. Each item begins with a bold heading, then a few sentences of \
explanation, keeping any illustrations or stories the preacher used (told briefly). \
Immediately after each bold heading, append the start time of that point as a marker \
in the form [t=SECONDS], chosen from the nearest transcript time marker where that \
point begins.

## Takeaways to Reflect On
A short paragraph of practical points to apply.

The transcript contains time markers written as [t=SECONDS], giving the number of \
seconds into the video. Use them only for the Key Points headings as described above; \
do not add time markers to any other section.

Keep it clear and readable. Do not add anything that wasn't in the sermon. Match the \
length to the sermon: a short sermon gives shorter notes, a long one gives fuller \
notes. Do not include any preamble, and do not repeat the title as a heading inside \
the notes. Never use em dashes (the long dash, distinct from a hyphen) anywhere in the \
notes; use commas, full stops, or the word "and" instead."""

MODEL = "claude-sonnet-4-6"

# The church these sermons come from, shown on the site. Edit if it ever changes.
CHURCH = "CityLife Church"


def extract_video_id(url):
    """Pull the 11-character YouTube video ID out of the common URL shapes.

    Handles: watch?v=ID, youtu.be/ID, /live/ID, /embed/ID, /shorts/ID, and a
    bare 11-char ID. Returns the ID, or None if we can't find one.
    """
    url = url.strip()

    # A bare video ID passed directly.
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url

    parsed = urllib.parse.urlparse(url)

    # youtu.be/<id>
    if parsed.netloc.endswith("youtu.be"):
        candidate = parsed.path.lstrip("/").split("/")[0]
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
            return candidate

    # youtube.com/watch?v=<id>
    query = urllib.parse.parse_qs(parsed.query)
    if "v" in query and re.fullmatch(r"[A-Za-z0-9_-]{11}", query["v"][0]):
        return query["v"][0]

    # youtube.com/live/<id>, /embed/<id>, /shorts/<id>
    match = re.search(r"/(?:live|embed|shorts)/([A-Za-z0-9_-]{11})", parsed.path)
    if match:
        return match.group(1)

    return None


def fetch_title(video_id):
    """Fetch the video's title via YouTube's public oEmbed endpoint (no API key).

    Used for the notes header and the output filename. Best-effort: returns None
    on any failure so we never block note generation on it.
    """
    watch_url = "https://www.youtube.com/watch?v=" + video_id
    oembed_url = (
        "https://www.youtube.com/oembed?"
        + urllib.parse.urlencode({"url": watch_url, "format": "json"})
    )
    try:
        with urllib.request.urlopen(oembed_url, timeout=10) as resp:
            data = json.load(resp)
        return data.get("title")
    except Exception:
        return None


def fetch_transcript(video_id):
    """Fetch the transcript as a single text block with periodic time markers.

    Uses the youtube-transcript-api 1.x interface (instance-based; snippets are
    objects with .text and .start). A marker like [t=312] (seconds into the video)
    is inserted roughly every 20 seconds so the notes prompt can tag each key
    point with the moment it begins.
    """
    api = YouTubeTranscriptApi()
    fetched = api.fetch(video_id)

    parts = []
    last_marker = -999.0
    for snippet in fetched:
        if snippet.start - last_marker >= 20:
            parts.append(f"[t={int(snippet.start)}]")
            last_marker = snippet.start
        parts.append(snippet.text)
    return " ".join(parts).strip()


def slugify(text, fallback):
    """Turn a title into a safe, short filename slug."""
    if not text:
        return fallback
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    slug = slug[:60].strip("-")
    return slug or fallback


def generate_notes(transcript, title, url):
    """Send the transcript to Claude and return the generated notes as text."""
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

    context_line = "Sermon video"
    if title:
        context_line += f': "{title}"'
    user_content = (
        f"{context_line}\nSource: {url}\n\n"
        "Here is the automatically generated transcript:\n\n"
        f"{transcript}"
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=NOTES_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return next(block.text for block in response.content if block.type == "text")


def parse_generated(text):
    """Split Claude's response into (title, speaker, body).

    The response starts with `TITLE:` and `SPEAKER:` lines; the notes body
    starts at the first `## ` heading.
    """
    title = ""
    speaker = ""
    for line in text.splitlines()[:6]:
        stripped = line.strip()
        if stripped.upper().startswith("TITLE:"):
            title = stripped.split(":", 1)[1].strip()
        elif stripped.upper().startswith("SPEAKER:"):
            speaker = stripped.split(":", 1)[1].strip()

    marker = text.find("## ")
    body = text[marker:].strip() if marker != -1 else text.strip()
    return title, speaker, body


def extract_theme(body):
    """Pull the one-line theme out of the body's '## Theme' section."""
    match = re.search(r"##\s*Theme\s*\n+(.+?)(?:\n##|\Z)", body, re.S)
    return " ".join(match.group(1).split()) if match else ""


def write_notes_file(notes_dir, slug, front_matter, body):
    """Write a notes/<slug>.md file (front-matter + body). Skips empty fields."""
    lines = ["---"]
    for key, value in front_matter:
        if value:
            lines.append(f"{key}: {value}")
    lines.append("---")
    content = "\n".join(lines) + "\n\n" + body.strip() + "\n"

    path = os.path.join(notes_dir, slug + ".md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def process_video(video_id, service_date):
    """Fetch, generate notes for, and publish one video, then rebuild the site.

    Returns one of:
      "done"      notes were generated and the website was rebuilt
      "not_ready" the transcript isn't available yet (try again later)
      "error"     something went wrong (bad video, API failure)
    """
    canonical_url = f"https://www.youtube.com/watch?v={video_id}"
    yt_title = fetch_title(video_id)
    print(f"Video: {yt_title or video_id}")

    try:
        transcript = fetch_transcript(video_id)
    except (TranscriptsDisabled, NoTranscriptFound):
        print(
            "No transcript is available yet. For a fresh upload or livestream, "
            "YouTube can take 12-24 hours to produce the final captions."
        )
        return "not_ready"
    except VideoUnavailable:
        print("That video is unavailable (private, deleted, or region-blocked).")
        return "error"
    except Exception:
        print(
            "Couldn't get the transcript yet. The captions may still be "
            "processing (they can take 12-24 hours); try again later."
        )
        return "not_ready"

    if not transcript:
        print("The transcript came back empty. Try again later.")
        return "not_ready"

    print(f"Transcript fetched ({len(transcript.split())} words). Generating notes...")

    try:
        raw = generate_notes(transcript, yt_title, canonical_url)
    except anthropic.AuthenticationError:
        print("The Anthropic API key was rejected. Double-check ANTHROPIC_API_KEY.")
        return "error"
    except anthropic.APIError as err:
        print(f"The Claude API call failed: {err}")
        return "error"

    title, speaker, body = parse_generated(raw)
    if not title:
        title = yt_title or video_id
    theme = extract_theme(body)

    notes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notes")
    os.makedirs(notes_dir, exist_ok=True)
    slug = f"{service_date}-{slugify(title, video_id)}"
    front_matter = [
        ("title", title),
        ("speaker", "" if speaker.lower() == "unknown" else speaker),
        ("church", CHURCH),
        ("date", service_date),
        ("source", canonical_url),
        ("theme", theme),
    ]
    notes_path = write_notes_file(notes_dir, slug, front_matter, body)
    print(f'Saved notes: "{title}" by {speaker or "Unknown"} -> {notes_path}')

    import build_site

    build_site.build()
    print("Website updated.")
    return "done"


def main():
    if len(sys.argv) not in (2, 3):
        print('Usage: python generate_notes.py "<youtube-url>" [YYYY-MM-DD]')
        sys.exit(1)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY is not set. Set it first, e.g.:\n"
            "    export ANTHROPIC_API_KEY=sk-ant-..."
        )
        sys.exit(1)

    url = sys.argv[1]
    service_date = sys.argv[2] if len(sys.argv) == 3 else datetime.date.today().isoformat()
    try:
        datetime.datetime.strptime(service_date, "%Y-%m-%d")
    except ValueError:
        print(f"The date should look like 2026-06-28, not '{service_date}'.")
        sys.exit(1)

    video_id = extract_video_id(url)
    if not video_id:
        print(
            "Couldn't find a YouTube video ID in that URL. Please pass a full "
            "video link, for example:\n"
            '    python generate_notes.py "https://www.youtube.com/watch?v=XXXXXXXXXXX"'
        )
        sys.exit(1)

    result = process_video(video_id, service_date)
    if result == "done":
        print("Open site/index.html to see it.")
        sys.exit(0)
    elif result == "not_ready":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
