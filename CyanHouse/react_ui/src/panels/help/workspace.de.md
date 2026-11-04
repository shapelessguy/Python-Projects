# {{name}}

{{description}}

Hier wird aus einem Download ein sauberer Film. Der **Eingang** (oben, `{{inbox}}`) enthält, was wartet; die **Ausgabe** (unten, `{{output}}`) enthält, was fertig ist{{#publish}}, bis du es in seine Bibliothek verschiebst{{/publish}}.

## Dateien hineinbringen
- Dateien oder ganze Ordner vom Computer auf den Eingang ziehen – Uploads werden fortgesetzt, wenn die Verbindung abbricht.
- Rechtsklick (oder mehrere ankreuzen) zum Umbenennen, Verschieben oder Löschen. Dinge wandern frei zwischen Eingang und Ausgabe{{#publish}}, und du kannst sie auch aus anderen Tabs hereinziehen{{/publish}}.

## Einen Film vorbereiten
Das Video im Eingang auswählen. Rechts erscheinen der Player und alles, was der Remux braucht:

1. Den Film **nachschlagen** und den richtigen Treffer wählen – das gibt ihm seinen endgültigen Namen, z. B. `Braveheart (1995)`.
2. Für jede **Audio**- und **Untertitel**spur die Sprache wählen. **— drop —** lässt die Spur weg. Eine Spur pro Sprache: Eine schon verwendete Sprache zu wählen, nimmt sie der anderen Spur weg.
3. **Delay (ms)**: Ist eine Spur nicht synchron, abspielen und anpassen, bis sie passt – die Zahl, die du funktionieren hörst, wird in die Datei geschrieben.
4. **SRT**: Bei einer Audiospur ankreuzen, um vor dem Remux Untertitel aus diesem Ton erzeugen zu lassen (Spracherkennung auf dem PC).
5. Fehlen Untertitel? Die Dateien in den Ordner des Films im Eingang ziehen.

Alles wird laufend gespeichert – du kannst die Seite schließen und später zurückkommen.

## Remuxen
**REMUX** drücken (oder **REMUX ALL** für jeden fertigen Film im Eingang). Er kommt in die Warteschlange (**☰**, oben rechts) und läuft auf dem Server, ein Film nach dem anderen, auch bei geschlossener Seite. Der Fortschritt wird in Schritten gezeigt: Untertitel erzeugen, remuxen, prüfen, verschieben.

Danach liegt der fertige Film in der Ausgabe, und der ursprüngliche Download wird in den `.trash` des Eingangs verschoben – nichts wird gelöscht, bevor die neue Datei geprüft ist.

## Veröffentlichen
{{#publish}}Den fertigen Film aus der Ausgabe auf den Tab seiner Bibliothek ziehen (z. B. **Movies**). Plex wird sofort benachrichtigt.
{{/publish}}{{^publish}}Um fertige Filme in eine Bibliothek zu verschieben, braucht man die Veröffentlichungs-Berechtigung – jemand, der sie hat, holt sie aus der Ausgabe.
{{/publish}}
