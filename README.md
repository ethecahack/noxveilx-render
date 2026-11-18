# NoxveilX renderer

Renders ahead of time several times a day on GitHub Actions (no PC needed):
pulls the next ready script from n8n, renders the video (edge-tts voice, Pollinations images, captions, ffmpeg),
then sends it to n8n, which uploads it to YouTube as a scheduled video. YouTube publishes it at the exact slot:
shorts daily 2:00 PM Riyadh, long videos Mon/Wed/Fri 2:00 PM Riyadh — so a late GitHub run never delays publishing.

- Secret needed: `NOXVEIL_TOKEN` (the same token n8n checks).
- Run it now: Actions → "NoxveilX - render & publish" → Run workflow.
- Each run's log is kept as an artifact for 14 days.
