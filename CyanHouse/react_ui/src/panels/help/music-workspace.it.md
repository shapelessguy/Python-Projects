# {{name}}

{{description}}

Qui le canzoni sparse diventano una libreria musicale in ordine. L'**inbox** (sopra, `{{inbox}}`) contiene quello che aspetta; l'**output** (sotto, `{{output}}`) quello già archiviato{{#publish}}, finché non lo sposti in **Music**{{/publish}}.

## Portare dentro le canzoni
- Trascina file o intere cartelle dal tuo computer sull'inbox. Cartelle e nomi qualsiasi vanno bene — `Artista - Titolo.mp3` è il più utile.
- Tasto destro (o spunta più righe) per rinominare, spostare, cancellare o creare una cartella.

## Riconoscere una canzone
Clicca una canzone nell'inbox. A destra puoi ascoltarla (doppio clic sulla riga per farla partire) e viene cercata su MusicBrainz con l'artista e il titolo che porta — i suoi tag, altrimenti il nome del file.

1. Sono elencati tutti gli album in cui compare, dal migliore: l'album in studio, poi singoli ed EP, raccolte e registrazioni dal vivo per ultime. Il primo è già selezionato.
2. Canzone sbagliata? Correggi **Artist** o **Title** e premi **Search**.
3. Premi **TAG & FILE**: i tag vengono scritti nel file e questo va in `Artista/Album/NN - Titolo` nell'output, con la copertina dell'album accanto. La canzone successiva si apre da sola.

## Archiviazione automatica
Di rado serve farlo a mano: il server scorre l'inbox da solo e archivia ogni canzone di cui è sicuro — titolo e artista corrispondono, la durata coincide con la registrazione entro pochi secondi, ed è in un album, singolo o EP ufficiale di quell'artista. I nomi disordinati vengono letti in ogni modo sensato ("Titolo - Artista", parti in più…).

Quelle di cui non è sicuro restano nell'inbox segnate con **?** — passaci sopra col mouse per il motivo. **TO CHECK** mostra solo quelle.

## Pubblicare
{{#publish}}Trascina gli artisti o gli album archiviati dall'output sulla scheda **Music**. Plex viene avvisato subito.
{{/publish}}{{^publish}}Spostare le canzoni archiviate in **Music** richiede il permesso di pubblicazione — ci penserà chi ce l'ha, prendendole dall'output.
{{/publish}}
