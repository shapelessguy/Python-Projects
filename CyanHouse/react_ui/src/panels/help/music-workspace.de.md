# {{name}}

{{description}}

Hier werden lose Songs zu einer ordentlichen Musikbibliothek. Der **Eingang** (oben, `{{inbox}}`) enthält, was wartet; die **Ausgabe** (unten, `{{output}}`) enthält, was einsortiert ist{{#publish}}, bis du es nach **Music** verschiebst{{/publish}}.

## Songs hineinbringen
- Dateien oder ganze Ordner vom Computer auf den Eingang ziehen. Beliebige Ordner und Namen gehen – `Künstler - Titel.mp3` ist am nützlichsten.
- Rechtsklick (oder mehrere ankreuzen) zum Umbenennen, Verschieben, Löschen oder Ordner anlegen.

## Einen Song erkennen
Einen Song im Eingang anklicken. Rechts wird er abgespielt (Doppelklick auf die Zeile startet ihn) und auf MusicBrainz anhand von Künstler und Titel gesucht, die er trägt – seine Tags, sonst sein Dateiname.

1. Jedes Album, auf dem der Song vorkommt, wird aufgelistet, das beste zuerst: das Studioalbum, dann Singles und EPs, Compilations und Live-Aufnahmen zuletzt. Das erste ist angekreuzt.
2. Falscher Song? **Künstler** oder **Titel** korrigieren und **Suchen** drücken.
3. **TAG & FILE** drücken: Die Tags werden in die Datei geschrieben, und sie wandert nach `Künstler/Album/NN - Titel` in der Ausgabe, mit dem Albumcover daneben. Der nächste Song öffnet sich von selbst.

## Einsortieren von selbst
Das oben Beschriebene brauchst du selten: Der Server geht den Eingang selbst durch und sortiert jeden Song ein, bei dem er sicher ist – Titel und Künstler passen, die Länge stimmt bis auf wenige Sekunden mit der Aufnahme überein, und er ist auf einem offiziellen Album, einer Single oder EP dieses Künstlers. Unordentliche Namen werden auf jede sinnvolle Weise gelesen („Titel - Künstler“, zusätzliche Teile…).

Wobei er nicht sicher ist, bleibt im Eingang mit **?** markiert – mit der Maus darüberfahren zeigt den Grund. **TO CHECK** zeigt nur diese.

## Veröffentlichen
{{#publish}}Die einsortierten Künstler oder Alben aus der Ausgabe auf den Tab **Music** ziehen. Plex wird sofort benachrichtigt.
{{/publish}}{{^publish}}Um einsortierte Songs nach **Music** zu verschieben, braucht man die Veröffentlichungs-Berechtigung – jemand, der sie hat, holt sie aus der Ausgabe.
{{/publish}}
