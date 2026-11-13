# NoxveilX renderer

Runs every day at 2:00 PM Riyadh on GitHub Actions (no PC needed):
pulls the next ready script from n8n, renders the video (edge-tts voice, Pollinations images, captions, ffmpeg),
then sends it to n8n, which uploads it to the NoxveilX YouTube channel.

- Secret needed: `NOXVEIL_TOKEN` (the same token n8n checks).
- Run it now: Actions → "NoxveilX - render & publish" → Run workflow.
- Each run's log is kept as an artifact for 14 days.
