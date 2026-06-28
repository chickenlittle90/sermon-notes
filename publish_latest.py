#!/usr/bin/env python3
"""
Sermon Notes Automation, auto-detect and publish the latest sermon.

Reads the church's YouTube RSS feed, finds the latest full Sunday service (a
video whose title contains "Online Church Service"), and, if we haven't already
published it, generates its notes and rebuilds the website. It does nothing (and
exits cleanly) when there is no new sermon, or when the new sermon's captions
aren't ready yet, so it is safe to run on a schedule.

Run:
    python publish_latest.py            # detect and publish
    python publish_latest.py --dry-run  # just report what it would do

Requires the ANTHROPIC_API_KEY environment variable (except for --dry-run).
"""

import json
import os
import re
import sys
import urllib.request
import warnings

# Silence the harmless LibreSSL warning from the system Python (see generate_notes).
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

import generate_notes

# --- Configuration ---------------------------------------------------------
# The channel also posts short clips and weekly updates, so we recognise the
# weekly service two ways: by its title, and by its length. The full service
# runs ~1.5-2 hours, far longer than any clip or update, so a long video is
# treated as the service even if its title is worded differently.
CHANNEL_ID = "UCYAN1DndQuBwD_2nrIaw8-Q"  # CityLife Church
TITLE_KEYWORDS = ("church service", "live from melbourne")
LONG_SECONDS = 60 * 60        # a video this long is almost certainly the service
TITLED_MIN_SECONDS = 30 * 60  # a service-titled video must be at least this long

ROOT = os.path.dirname(os.path.abspath(__file__))
PROCESSED_FILE = os.path.join(ROOT, "processed.json")


def fetch_feed_entries():
    """Return the channel's recent videos as dicts: {id, title, date}, newest first."""
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
    with urllib.request.urlopen(feed_url, timeout=20) as resp:
        xml = resp.read().decode("utf-8", "replace")

    entries = []
    for block in re.findall(r"<entry>.*?</entry>", xml, re.S):
        vid = re.search(r"<yt:videoId>([^<]+)</yt:videoId>", block)
        title = re.search(r"<title>([^<]*)</title>", block)
        published = re.search(r"<published>([^<]+)</published>", block)
        if vid and title and published:
            entries.append(
                {
                    "id": vid.group(1),
                    "title": title.group(1),
                    "date": published.group(1)[:10],  # YYYY-MM-DD
                }
            )
    return entries


def video_duration_seconds(video_id):
    """Best-effort video length in seconds, read from the watch page (no API key).

    Returns None if it can't be determined, in which case we fall back to the
    title alone.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as resp:
            html = resp.read().decode("utf-8", "replace")
    except Exception:
        return None
    match = re.search(r'"lengthSeconds":"(\d+)"', html)
    return int(match.group(1)) if match else None


def find_latest_sermon(entries):
    """Pick the newest feed entry that is the weekly service.

    A video qualifies if it is clearly long (the full service), or if its title
    looks like a service and it isn't just a short clip. Length is read from the
    watch page, so a mistitled-but-long video is still caught and a short clip
    with a service-like title is skipped.
    """
    for entry in entries:  # the feed is newest-first
        title_match = any(k in entry["title"].lower() for k in TITLE_KEYWORDS)
        duration = video_duration_seconds(entry["id"])
        if duration is not None:
            if duration >= LONG_SECONDS:
                return entry
            if title_match and duration >= TITLED_MIN_SECONDS:
                return entry
        elif title_match:
            return entry  # couldn't read the length, so trust the title
    return None


def load_processed():
    """Return the list of video IDs we've already published."""
    try:
        with open(PROCESSED_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_processed(ids):
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(ids, f, indent=2)


def main():
    dry_run = "--dry-run" in sys.argv[1:]

    if not dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. Set it first, e.g.:")
        print("    export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    try:
        entries = fetch_feed_entries()
    except Exception as err:
        print(f"Couldn't read the YouTube feed: {err}")
        sys.exit(1)

    latest = find_latest_sermon(entries)
    if not latest:
        print("No full-length service found in the latest feed. Nothing to do.")
        sys.exit(0)

    processed = load_processed()

    if latest["id"] in processed:
        print(f"Latest sermon already published ({latest['id']}). Nothing to do.")
        sys.exit(0)

    print(f"New sermon found: {latest['title']} ({latest['date']})")

    if dry_run:
        print("(dry run) Would publish this sermon. Not generating.")
        sys.exit(0)

    result = generate_notes.process_video(latest["id"], latest["date"])
    if result == "done":
        processed.append(latest["id"])
        save_processed(processed)
        print("Published. The website is up to date.")
        sys.exit(0)
    elif result == "not_ready":
        # Don't record it, so the next run tries again once captions are ready.
        print("Captions aren't ready yet. Will try again on the next run.")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
