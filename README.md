# Gender Classifier and Profiles API

A FastAPI app that supports both Stage 0 classification and Stage 1 profile persistence.

## What This App Does

- Stage 0:
  - Accepts a `name` query parameter on `GET /api/classify`
  - Calls `https://api.genderize.io`
  - Returns a normalized classification payload
- Stage 1:
  - Accepts `POST /api/profiles` with `{ "name": "..." }`
  - Calls Genderize, Agify, and Nationalize APIs
  - Applies classification logic (age group and top country)
  - Stores profiles in Supabase Postgres with idempotent name handling
  - Exposes read/list/delete profile endpoints

## Tech Stack

- Python 3.13
- FastAPI
- httpx
- Supabase (official Python client)
- Uvicorn

## Project Structure

- `main.py` - app startup, CORS, global exception handlers
- `app/api/routes.py` - HTTP route/view layer
- `app/db.py` - database initialization
- `app/models/classify.py` - Stage 0 response models
- `app/models/profile.py` - Stage 1 profile models
- `app/repositories/profiles.py` - profile persistence access layer
- `app/services/classify.py` - Stage 0 validation/orchestration logic
- `app/services/genderize.py` - Genderize integration
- `app/services/agify.py` - Agify integration
- `app/services/nationalize.py` - Nationalize integration
- `app/services/profiles.py` - Stage 1 profile orchestration

## Run Locally

1. Create/activate virtual environment (if needed)
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure your Supabase credentials:

Windows PowerShell:

```powershell
$env:SUPABASE_URL="https://<project-ref>.supabase.co"
$env:SUPABASE_KEY="<service-role-or-anon-key>"
```

You can also use `SUPABASE_SERVICE_ROLE_KEY` instead of `SUPABASE_KEY`.

4. Start the app:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

5. Open docs:
- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

## Endpoints

### Stage 0

#### GET `/api/classify`

Query parameters:
- `name` (required)

Example request:

```bash
curl "http://localhost:8000/api/classify?name=bashir"
```

Success response example:

Status: `200 OK`

```json
{
  "status": "success",
  "data": {
    "name": "bashir",
    "gender": "male",
    "probability": 0.99,
    "sample_size": 1234,
    "is_confident": true,
    "processed_at": "2026-04-01T12:00:00Z"
  }
}
```

Confidence logic:

`is_confident` is `true` only when both conditions are met:
- `probability >= 0.7`
- `sample_size >= 100`

Otherwise, `is_confident` is `false`.

### Stage 1

#### POST `/api/profiles`
- Body: `{ "name": "ella" }`
- Creates and stores a profile from Genderize + Agify + Nationalize data
- Duplicate name returns existing profile with message `Profile already exists`

#### GET `/api/profiles/{id}`
- Returns a single persisted profile

#### GET `/api/profiles`
- Returns all profiles
- Optional filters: `gender`, `country_id`, `age_group`
- Filter values are case-insensitive

#### DELETE `/api/profiles/{id}`
- Returns `204 No Content` on success

## Error Format

All errors follow this structure:

```json
{
  "status": "error",
  "message": "<error message>"
}
```

## Validation and Error Cases

- Missing or empty `name` -> `400 Bad Request`
- Invalid `name` type -> `422 Unprocessable Entity`
- Profile not found -> `404 Not Found`
- Upstream failure (Genderize/Agify/Nationalize invalid payload) -> `502 Bad Gateway`
- Unexpected server error -> `500 Internal Server Error`

Stage 1 edge cases (returns `502`, does not persist):
- Genderize returns `gender: null` or `count: 0`
- Agify returns `age: null`
- Nationalize returns no country data

## CORS

CORS is enabled with wildcard origin support:
- `Access-Control-Allow-Origin: *`
