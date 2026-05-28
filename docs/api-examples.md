Immediate Server Response Model (200 OK)
JSON

{
  "status": "processing",
  "message": "Agent-loopen körs asynkront i bakgrunden."
}

Note: This endpoint returns immediately. The 5-agent pipeline continues execution independently inside host worker threads.
🗄️ 2. Fetch All Solutions Index
HTTP Request Specification

    URL: http://localhost:8500/api/solutions

    Method: GET

Command Line Interacts (curl)
Bash

curl -X GET http://localhost:8500/api/solutions

Server Response Model (200 OK)

Returns an array of historic artifacts sorted reverse-chronologically (newest entries first). This index intentionally strips heavy code bodies to optimize transfer payload weights.
JSON

[
  {
    "id": 2,
    "prompt": "Skriv en nodejs-funktion som skriver hello world i konsollen.",
    "timestamp": "2026-05-28 23:22:11"
  },
  {
    "id": 1,
    "prompt": "Skriv en Python-funktion som validerar om en sträng är en korrekt e-postadress. Använd regex.",
    "timestamp": "2026-05-28 21:16:40"
  }
]

🔬 3. Extract Specific Solution Artifact
HTTP Request Specification

    URL: http://localhost:8500/api/solutions/{solution_id}

    Method: GET

    Path Variables: solution_id (Integer, Required): The explicit primary key ID of the target entry.

Command Line Interacts (curl)
Bash

curl -X GET http://localhost:8500/api/solutions/1

Server Response Model (200 OK)

Returns the complete payload including the source code compiled, evaluated, and passed by the DeepSeek validation critic.
JSON

{
  "id": 1,
  "prompt": "Skriv en Python-funktion som validerar om en sträng är en korrekt e-postadress. Använd regex.",
  "solution": "### Python Email Validator\n\nHär är den optimerade och granskade lösningen med användning av standardbiblioteket `re`:\n\n
http://googleusercontent.com/immersive_entry_chip/0

### Server Response Model (`200 OK`)
Returns the complete payload including the source code compiled, evaluated, and passed by the DeepSeek validation critic.
```json
{
  "id": 1,
  "prompt": "Skriv en Python-funktion som validerar om en sträng är en korrekt e-postadress. Använd regex.",
  "solution": "### Python Email Validator\n\nHär är den optimerade och granskade lösningen med användning av standardbiblioteket `re`:\n\n
http://googleusercontent.com/immersive_entry_chip/1

"timestamp": "2026-05-28 21:16:40"
}
```

### Server Error Response Model (`404 Not Found`)
If you request an ID that does not exist inside the SQLite persistence layer:
```json
{
  "detail": "Lösningen hittades inte i databasen."
}
```

---

## 🪝 4. Outgoing Webhook Schema (Callback Event)

If a `webhook_url` was specified during the dispatch request, the application will emit the following payload automatically once the Critic agent reaches validation approval or loop threshold limits.

* **Method Issued:** `POST`
* **Headers Dispatched:** `Content-Type: application/json`

### Dispatched JSON Body Structure
```json
{
  "status": "completed",
  "id": 1,
  "prompt": "Skriv en Python-funktion som validerar om en sträng är en korrekt e-postadress. Använd regex.",
  "solution": "```python\nimport re\n...",
}
```