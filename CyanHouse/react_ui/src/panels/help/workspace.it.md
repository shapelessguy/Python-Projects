# {{name}}

{{description}}

Qui un download diventa un film pulito. L'**inbox** (sopra, `{{inbox}}`) contiene quello che aspetta; l'**output** (sotto, `{{output}}`) quello che è finito{{#publish}}, finché non lo sposti nella sua libreria{{/publish}}.

## Portare dentro i file
- Trascina file o intere cartelle dal tuo computer sull'inbox — i caricamenti riprendono se la connessione cade.
- Tasto destro (o spunta più righe) per rinominare, spostare o cancellare. Tra inbox e output si sposta tutto liberamente{{#publish}}, e puoi anche trascinare qui cose da altre schede{{/publish}}.

## Preparare un film
Scegli il video nell'inbox. A destra compare il player con tutto quello che serve al remux:

1. **Look up**: cerca il film e scegli quello giusto — gli dà il nome definitivo, es. `Braveheart (1995)`.
2. Per ogni traccia **audio** e **sottotitoli** scegli la lingua. **— drop —** la esclude. Una traccia per lingua: se scegli una lingua già usata, viene tolta dall'altra traccia.
3. **Delay (ms)**: se una traccia è fuori sincrono, riproducila e regola finché combacia — il valore che senti funzionare è quello che viene scritto nel file.
4. **SRT**: spuntalo su una traccia audio per generare i sottotitoli da quell'audio (speech-to-text sul PC) prima del remux.
5. Mancano i sottotitoli? Caricali con **＋** o trascinali sul player.

Tutto viene salvato mentre lavori — puoi chiudere la pagina e tornare dopo.

## Remux
Premi **REMUX** (o **REMUX ALL** per tutti i film pronti nell'inbox). Il film entra nella coda (**☰**, in alto a destra) e viene elaborato sul server, uno alla volta, anche a pagina chiusa. L'avanzamento è mostrato a passi: generazione sottotitoli, remux, controllo, spostamento.

A lavoro finito il film è nell'output, e il download originale viene spostato nella `.trash` dell'inbox — niente viene cancellato finché il nuovo file non è stato controllato.

## Pubblicare
{{#publish}}Trascina il film finito dall'output sulla scheda della sua libreria (es. **Movies**). Plex viene avvisato subito.
{{/publish}}{{^publish}}Spostare i film finiti in una libreria richiede il permesso di pubblicazione — chi ce l'ha li prenderà dall'output.
{{/publish}}
