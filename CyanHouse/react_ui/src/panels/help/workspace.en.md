# {{name}}

{{description}}

This is where a download becomes a clean film. The **inbox** (top, `{{inbox}}`) holds what is waiting; the **output** (bottom, `{{output}}`) holds what is finished{{#publish}}, until you move it to its library{{/publish}}.

## Getting files in
- Drop files or whole folders from your computer onto the inbox — uploads resume if the connection drops.
- Right-click (or tick several) to rename, move or delete. Things move freely between the inbox and the output{{#publish}}, and you can also drag them in from other tabs{{/publish}}.

## Preparing a film
Pick the video in the inbox. The right side becomes the player plus everything the remux will need:

1. **Look up** the film and choose the right match — this gives it its final name, e.g. `Braveheart (1995)`.
2. For every **audio** and **subtitle** track, choose its language. **— drop —** leaves the track out. One track per language: picking a language already used moves it off the other track.
3. **Delay (ms)**: if a track is out of sync, play it and adjust until it matches — the number you hear working is the one written into the file.
4. **SRT**: tick it on an audio track to have subtitles generated from that audio (speech-to-text on the PC) before the remux.
5. Missing subtitles? Upload them with **＋** or drop them on the player.

Everything is saved as you go — you can close the page and come back.

## Remuxing
Press **REMUX** (or **REMUX ALL** for every ready film in the inbox). It goes into the queue (**☰**, top right) and runs on the server, one film at a time, even with the page closed. Progress is shown in steps: generating subtitles, remuxing, checking, moving.

When it is done the finished film is in the output, and the original download is moved to the inbox's `.trash` — nothing is deleted until the new file has been checked.

## Publishing
{{#publish}}Drag the finished film from the output onto its library tab (e.g. **Movies**). Plex is told straight away.
{{/publish}}{{^publish}}Moving finished films into a library needs the publish permission — someone who has it will take them from the output.
{{/publish}}
