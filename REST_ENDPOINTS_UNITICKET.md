# uniTicket - Endpoint REST API e Chiamate JSON

Questo documento riassume tutti gli endpoint per le chiamate REST (e gli endpoint JSON ausiliari) disponibili nella piattaforma **uniTicket**, i relativi metodi HTTP, permessi richiesti, parametri e file sorgente in cui sono definiti.

---

## 1. Architettura e Autenticazione

Il routing principale del progetto è configurato in [`uniticket/uni_ticket_project/urls.py`](file:///Users/saverio/Desktop/uniTicket/uniticket/uni_ticket_project/urls.py). I moduli API REST sono abilitati in base alle applicazioni installate (`INSTALLED_APPS`):
- `rest_framework` -> include [`uniticket/api_rest/urls.py`](file:///Users/saverio/Desktop/uniTicket/uniticket/api_rest/urls.py) su prefisso radice (`/api/...`).
- `chat` -> include [`uniticket/chat/urls.py`](file:///Users/saverio/Desktop/uniTicket/uniticket/chat/urls.py) su prefisso radice (`/api/chat/...`).

### Modalità di Autenticazione
1. **Token DRF Custom (`AuthorizationToken`)**:
   - Definito in [`uniticket/api_rest/authorizations.py`](file:///Users/saverio/Desktop/uniTicket/uniticket/api_rest/authorizations.py) e memorizzato nel modello `api_rest.models.AuthorizationToken`.
   - Header HTTP richiesto: `Authorization: Token <valore_token>`.
2. **Session Authentication di Django**:
   - Tramite cookie di sessione standard (`sessionid`).
3. **CSRF-Exempt Session Authentication**:
   - Utilizzato specificamente nel modulo `chat` ([`uniticket/chat/api.py`](file:///Users/saverio/Desktop/uniTicket/uniticket/chat/api.py)) per agevolare le interazioni AJAX/REST dalla UI.

---

## 2. Modulo `api_rest`

Definito in [`uniticket/api_rest/urls.py`](file:///Users/saverio/Desktop/uniTicket/uniticket/api_rest/urls.py) e gestito dalle viste nel package [`uniticket/api_rest/views/`](file:///Users/saverio/Desktop/uniTicket/uniticket/api_rest/views/).

> **Nota sui prefissi:** I path con `{manager}` e `{operatore}` usano la funzione `slugify()` sui valori di `MANAGEMENT_URL_PREFIX` in [`uniticket/uni_ticket/settings.py`](file:///Users/saverio/Desktop/uniTicket/uniticket/uni_ticket/settings.py):
> - Di default `MANAGEMENT_URL_PREFIX["manager"] = "Manager"` -> prefisso `/api/manager/...`
> - Di default `MANAGEMENT_URL_PREFIX["operator"] = "Operatore"` -> prefisso `/api/operatore/...`

### 2.1 Schema OpenAPI
| Metodo | Endpoint | Nome URL | Classe View | Descrizione |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/openapi/` | `openapi-schema` | `get_schema_view` | Schema OpenAPI dell'applicazione in formato standard |
| `GET` | `/openapi.json/` | `openapi-schema-json` | `get_schema_view` | Schema OpenAPI dell'applicazione in formato JSON (`JSONOpenAPIRenderer`) |

### 2.2 Generici (Strutture e Categorie)
| Metodo | Endpoint | Nome URL | Classe View | Permessi | Descrizione |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/strutture/list/` | `api-strutture-list` | [`TicketAPIStruttureList`](file:///Users/saverio/Desktop/uniTicket/uniticket/api_rest/views/generic.py#L88) | `IsAuthenticated` | Elenco di tutte le strutture organizzative attive (`OrganizationalStructureSerializer`) |
| `GET` | `/api/ticket/category/list/` | `api-ticket-category-list` | [`TicketAPITicketCategoryList`](file:///Users/saverio/Desktop/uniTicket/uniticket/api_rest/views/generic.py#L94) | `IsAuthenticated` | Elenco di tutte le categorie/tipologie di ticket attive (`TicketCategorySerializer`) |

### 2.3 Utente (`user`) - Ciclo di vita Ticket
| Metodo | Endpoint | Nome URL | Classe View | Permessi | Descrizione |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/<structure_slug>/<category_slug>/ticket/new/` | `api-new-ticket` | [`TicketAPIView`](file:///Users/saverio/Desktop/uniTicket/uniticket/api_rest/views/user.py#L43) | `IsAuthenticated` | Restituisce la definizione del modulo dinamico (campi, condizioni, validazioni) per la categoria |
| `POST` | `/api/<structure_slug>/<category_slug>/ticket/new/` | `api-new-ticket` | [`TicketAPIView`](file:///Users/saverio/Desktop/uniTicket/uniticket/api_rest/views/user.py#L43) | `IsAuthenticated` | Invia i dati compilati e crea una nuova istanza di ticket |
| `GET` | `/api/ticket/<ticket_uid>/` | `api-view-ticket` | [`TicketAPIDetail`](file:///Users/saverio/Desktop/uniTicket/uniticket/api_rest/views/user.py#L135) | Proprietario / autorizzato | Restituisce i dettagli del ticket, lo stato e lo storico dei messaggi serializzati |
| `GET` | `/api/ticket/user/list/` | `api-ticket-user-list` | [`TicketAPIListCreated`](file:///Users/saverio/Desktop/uniTicket/uniticket/api_rest/views/user.py#L175) | `IsAuthenticated` | Lista paginata di tutti i ticket creati o compilati dall'utente autenticato (`TicketSerializer`) |
| `GET` / `POST` | `/api/ticket/close/<ticket_id>/` | `api-ticket-close` | [`TicketAPIClose`](file:///Users/saverio/Desktop/uniTicket/uniticket/api_rest/views/user.py#L198) | Proprietario / autorizzato | Operazione di chiusura del ticket con invio delle relative motivazioni |

### 2.4 Manager - Contatori e Statistiche
Richiedono che l'utente autenticato abbia il ruolo di **Manager** per la struttura specificata:
| Metodo | Endpoint | Nome URL | Classe View | Descrizione |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/manager/<structure_slug>/tickets/unassigned/count/` | `api-manager-tickets-unassigned-count` | [`TicketAPIUnassignedCounter`](file:///Users/saverio/Desktop/uniTicket/uniticket/api_rest/views/manager.py#L27) | Conteggio ticket aperti e non ancora assegnati nella struttura |
| `GET` | `/api/manager/<structure_slug>/tickets/open/count/` | `api-manager-tickets-open-count` | [`TicketAPIOpenCounter`](file:///Users/saverio/Desktop/uniTicket/uniticket/api_rest/views/manager.py#L37) | Conteggio ticket aperti e presi in carico nella struttura |
| `GET` | `/api/manager/<structure_slug>/tickets/my-open/count/` | `api-manager-tickets-my-open-count` | [`TicketAPIMyOpenCounter`](file:///Users/saverio/Desktop/uniTicket/uniticket/api_rest/views/manager.py#L47) | Conteggio ticket aperti presi in carico personalmente dal manager |
| `GET` | `/api/manager/<structure_slug>/tickets/messages/count/` | `api-manager-tickets-messages-count` | [`TicketAPIMessagesCounter`](file:///Users/saverio/Desktop/uniTicket/uniticket/api_rest/views/manager.py#L58) | Conteggio messaggi non letti relativi ai ticket seguiti della struttura |

### 2.5 Operatore - Contatori e Statistiche
Richiedono che l'utente autenticato abbia il ruolo di **Operatore** per la struttura/ufficio specificato:
| Metodo | Endpoint | Nome URL | Classe View | Descrizione |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/operatore/<structure_slug>/tickets/unassigned/count/` | `api-operator-tickets-unassigned-count` | [`TicketAPIUnassignedCounter`](file:///Users/saverio/Desktop/uniTicket/uniticket/api_rest/views/operator.py#L27) | Conteggio ticket non assegnati visibili all'operatore |
| `GET` | `/api/operatore/<structure_slug>/tickets/open/count/` | `api-operator-tickets-open-count` | [`TicketAPIOpenCounter`](file:///Users/saverio/Desktop/uniTicket/uniticket/api_rest/views/operator.py#L40) | Conteggio ticket aperti visibili all'operatore |
| `GET` | `/api/operatore/<structure_slug>/tickets/my-open/count/` | `api-operator-tickets-my-open-count` | [`TicketAPIMyOpenCounter`](file:///Users/saverio/Desktop/uniTicket/uniticket/api_rest/views/operator.py#L53) | Conteggio ticket aperti presi in carico personalmente dall'operatore |
| `GET` | `/api/operatore/<structure_slug>/tickets/messages/count/` | `api-operator-tickets-messages-count` | [`TicketAPIMessagesCounter`](file:///Users/saverio/Desktop/uniTicket/uniticket/api_rest/views/operator.py#L67) | Conteggio messaggi non letti sui ticket visibili all'operatore |

> **Nota:** In [`uniticket/api_rest/urls.py`](file:///Users/saverio/Desktop/uniTicket/uniticket/api_rest/urls.py#L14-L21) sono predisposti i `ModelViewSet` per `users` e `groups`, attualmente commentati nel routing DRF (`path('api/', include(router.urls))`).

---

## 3. Modulo `chat`

Definito in [`uniticket/chat/urls.py`](file:///Users/saverio/Desktop/uniTicket/uniticket/chat/urls.py) e implementato in [`uniticket/chat/api.py`](file:///Users/saverio/Desktop/uniTicket/uniticket/chat/api.py). Registrato tramite DRF `DefaultRouter` con prefisso base `/api/chat/`.

### 3.1 Messaggi di Chat (`/api/chat/message/`)
| Metodo | Endpoint | ViewSet | Parametri Query | Descrizione |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/chat/message/` | [`ChatMessageModelViewSet`](file:///Users/saverio/Desktop/uniTicket/uniticket/chat/api.py#L34) | `room`, `target`, `broadcast` | Elenco paginato dei messaggi dove l'utente è mittente o destinatario. Se specificato `room`, aggiorna il timestamp `last_seen` del canale utente |
| `POST` | `/api/chat/message/` | [`ChatMessageModelViewSet`](file:///Users/saverio/Desktop/uniTicket/uniticket/chat/api.py#L34) | — | Creazione e invio di un nuovo messaggio di chat |
| `GET` | `/api/chat/message/<id>/` | [`ChatMessageModelViewSet`](file:///Users/saverio/Desktop/uniTicket/uniticket/chat/api.py#L34) | `room` | Dettaglio del singolo messaggio per stanza e aggiornamento `last_seen` |

### 3.2 Utenti e Presenza Chat (`/api/chat/user/`)
| Metodo | Endpoint | ViewSet | Descrizione |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/chat/user/<id>/` | [`UserModelViewSet`](file:///Users/saverio/Desktop/uniTicket/uniticket/chat/api.py#L80) | Dettaglio dell'utente per la chat (ammesso solo per l'utente stesso o per superuser) |
| `PUT` | `/api/chat/user/<id>/` | [`UserModelViewSet`](file:///Users/saverio/Desktop/uniTicket/uniticket/chat/api.py#L80) | Aggiorna lo stato (`change_status`) del canale utente nella stanza specificata nel body (`room`) |

*(La chat dispone inoltre del socket real-time su `ws/chat/<room_name>/` definito in [`uniticket/chat/routing.py`](file:///Users/saverio/Desktop/uniTicket/uniticket/chat/routing.py)).*

---

## 4. Endpoint JSON ausiliari (DataTables)

Definiti in [`uniticket/uni_ticket/urls.py`](file:///Users/saverio/Desktop/uniTicket/uniticket/uni_ticket/urls.py#L75) e implementati in [`uniticket/uni_ticket/views/datatables.py`](file:///Users/saverio/Desktop/uniTicket/uniticket/uni_ticket/views/datatables.py). Rispondono in `GET` restituendo payload JSON formattati per i componenti tabellari frontend (DataTables):

### 4.1 Utente
- `/user_all_tickets.json`
- `/user_opened_ticket.json`
- `/user_closed_ticket.json`
- `/user_unassigned_ticket.json`

### 4.2 Manager (`/<structure_slug>/...`)
- `/<structure_slug>/manager_unassigned_ticket.json`
- `/<structure_slug>/manager_opened_ticket.json`
- `/<structure_slug>/my/manager_opened_ticket.json`
- `/<structure_slug>/manager_closed_ticket.json`
- `/<structure_slug>/manager_all_tickets.json`

### 4.3 Operatore (`/<structure_slug>/...`)
- `/<structure_slug>/operator_unassigned_ticket.json`
- `/<structure_slug>/operator_opened_ticket.json`
- `/<structure_slug>/my/operator_opened_ticket.json`
- `/<structure_slug>/operator_closed_ticket.json`
- `/<structure_slug>/operator_all_tickets.json`
