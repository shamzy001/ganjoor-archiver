## ADDED Requirements

### Requirement: Rate-limited HTTP client
The system SHALL enforce a minimum 1.0-second interval between consecutive outgoing HTTP requests to `api.ganjoor.net`, measured from the moment the previous response was received. No burst requests are permitted regardless of how many coroutines are awaiting a response.

#### Scenario: Sequential requests respect the rate limit
- **WHEN** two API calls are made back-to-back
- **THEN** the second request is not sent until at least 1.0 seconds after the first response was received

#### Scenario: Rate limit survives concurrent coroutines
- **WHEN** multiple coroutines call the client simultaneously
- **THEN** requests are serialised and none are sent closer than 1.0 s apart

### Requirement: Exponential backoff on transient errors
The system SHALL retry HTTP 429 and 5xx responses up to 3 times with delays of 5 s, 15 s, and 45 s respectively before declaring the request permanently failed.

#### Scenario: 429 is retried with backoff
- **WHEN** the server responds with HTTP 429
- **THEN** the client waits 5 s and retries; on a second 429 waits 15 s; on a third waits 45 s

#### Scenario: 5xx is retried with backoff
- **WHEN** the server responds with HTTP 500, 502, 503, or 504
- **THEN** the same backoff sequence (5 s → 15 s → 45 s) is applied

#### Scenario: 4xx other than 429 is not retried
- **WHEN** the server responds with HTTP 404 or 400
- **THEN** the client raises immediately without retrying

### Requirement: Permanent failure returns None
After exhausting all 3 retries, the client SHALL return `None` (not raise) so the caller can log the failure and continue with other entities.

#### Scenario: Caller receives None after 3 failures
- **WHEN** all 3 retry attempts for a URL receive 429 or 5xx
- **THEN** `_get()` returns `None` instead of raising an exception

### Requirement: Connection reuse across the crawl session
The system SHALL create a single `httpx.AsyncClient` instance per crawl session and reuse it for all requests. The client SHALL be closed when the session ends.

#### Scenario: Client is used as an async context manager
- **WHEN** `GanjoorClient` is used with `async with GanjoorClient() as client`
- **THEN** one `httpx.AsyncClient` is created on entry and closed on exit

### Requirement: Correct API endpoints
The client SHALL expose four coroutines mapping to Ganjoor REST endpoints:

| Method | Endpoint |
|---|---|
| `get_poets()` | `GET /api/ganjoor/poets` |
| `get_poet(id)` | `GET /api/ganjoor/poet/{id}` |
| `get_category(id)` | `GET /api/ganjoor/cat/{id}?poems=true&cat=true` |
| `get_poem(id)` | `GET /api/ganjoor/poem/{id}?verses=true` |

#### Scenario: get_poets returns a list
- **WHEN** `get_poets()` is called and the API returns HTTP 200
- **THEN** a `list[dict]` is returned with at least one poet entry

#### Scenario: get_category includes child categories and poems
- **WHEN** `get_category(id)` is called for a non-leaf category
- **THEN** the returned dict contains both a `cat.cats` array (child categories) and a `poems` array
