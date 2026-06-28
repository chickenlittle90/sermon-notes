# Sermon Notes

Turns a church sermon posted on YouTube into clean, readable notes.

This is **Phase 1**: a script you run by hand. You give it a YouTube link, it
pulls the video's captions, asks Claude to write notes, and saves them as a
file you can read. Later phases (emailing the notes, detecting new sermons
automatically, running on a schedule) come once we're happy with the format.

## One-time setup

You'll do this once. Open the Terminal app and run these, one line at a time:

```bash
cd /Users/jeremy/sermon-notes
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Then set your Anthropic API key (the key that lets the script talk to Claude):

```bash
export ANTHROPIC_API_KEY=sk-ant-...your-key-here...
```

> Note: `export` only lasts for the current Terminal window. The next time you
> open Terminal, run the `export ANTHROPIC_API_KEY=...` line again (and
> `source venv/bin/activate` to switch the project on). To avoid retyping the
> key, you can add the `export` line to your `~/.zshrc` file.

## Making notes for a sermon

With the steps above done, run:

```bash
python generate_notes.py "https://www.youtube.com/watch?v=XXXXXXXXXXX"
```

(Put the link in quotes.) The notes print to the screen and are also saved into
the `output/` folder as a `.md` (markdown) text file, named by date and title.

## Good to know

- **Wait for the captions.** For a brand-new upload or a livestream, YouTube can
  take 12–24 hours to finish the captions. If you run the script too early it
  will tell you the transcript isn't ready yet, just try again the next morning.
- **It won't crash on you.** A bad link, a video with no captions, or a missing
  key all produce a short, plain message rather than a wall of red error text.
- **Tuning the notes.** The instructions Claude follows live in the
  `NOTES_PROMPT` section near the top of `generate_notes.py`. That's the part to
  adjust as we shape the notes until they're just right.

## What's under the hood

- `youtube-transcript-api`, reads YouTube's existing captions (no API key needed).
- `anthropic`, sends the transcript to Claude (`claude-sonnet-4-6`) to write the notes.
