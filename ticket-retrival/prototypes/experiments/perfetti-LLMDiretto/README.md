# perfetti-LLMDiretto

Struttura iniziale del prototipo personale di classificazione LLM diretta.
**Non implementato**: nessun modello, provider, chiave o prompt è ancora configurato.
Il costruttore si ferma esplicitamente per non produrre risultati fittizi nel benchmark.

- `prototype.py`: classe derivata dal contratto condiviso `prototypes.base.Prototype`.
- `results/`: risultati personali esclusi da Git; condividere solo report revisionati.
- Catalogo, dataset, dipendenze e benchmark rimangono quelli comuni del progetto.

Prossimo step da concordare: modello locale/remoto e risorse, formato del prompt,
output strutturato con ID validato, trattamento dell'astensione e costi.
Restituire un solo ID non produce una vera graduatoria Top-5: documentarlo nei confronti.

La cartella con trattino è caricabile dal benchmark esistente tramite import dinamico.
Il test automatico verifica caricamento e arresto esplicito dello scaffold.
