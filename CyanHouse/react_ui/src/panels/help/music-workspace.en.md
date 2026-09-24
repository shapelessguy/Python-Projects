# {{name}}

{{description}}

This is where loose songs become a tidy music library. The **inbox** (top, `{{inbox}}`) holds what is waiting; the **output** (bottom, `{{output}}`) holds what is filed{{#publish}}, until you move it to **Music**{{/publish}}.

## Getting songs in
- Drop files or whole folders from your computer onto the inbox. Any folders and names will do — `Artist - Title.mp3` is the most useful.
- Right-click (or tick several) to rename, move, delete or create a folder.

## Recognising a song
Click a song in the inbox. The right side plays it (double-click the row to start it) and looks it up on MusicBrainz by the artist and title it carries — its tags, or else its file name.

1. Every album the song appears on is listed, best first: the studio album, then singles and EPs, compilations and live recordings last. The first one is ticked.
2. Wrong song? Correct the **Artist** or **Title** and press **Search**.
3. Press **TAG & FILE**: the tags are written into the file and it moves to `Artist/Album/NN - Title` in the output, with the album cover beside it. The next song opens by itself.

## Filing by itself
You rarely need to do the above: the server goes through the inbox on its own and files every song it is sure of — the title and artist match, the length matches the recording to within a few seconds, and it is on an official album, single or EP of that artist. Messy names are read every sensible way ("Title - Artist", extra parts…).

What it is not sure of stays in the inbox marked **?** — hover it for the reason. **TO CHECK** shows only those.

## Publishing
{{#publish}}Drag the filed artists or albums from the output onto the **Music** tab. Plex is told straight away.
{{/publish}}{{^publish}}Moving filed songs into **Music** needs the publish permission — someone who has it will take them from the output.
{{/publish}}
