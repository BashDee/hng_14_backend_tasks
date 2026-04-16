# API Implementation Overview

This document explains how the codebase handles the `/api/classify` endpoint concerns.

## Query Parameter Handling
- The route reads query values with `request.query_params.getlist("name")` in `app/api/routes.py`.
- Validation is centralized in `ClassifyService._validate_name(...)` in `app/services/classify.py`.
- Validation outcomes:
  - Missing parameter or blank string -> `400` with `{"status":"error","message":"Missing or empty name"}`.
  - Multiple `name` values -> `422` with `{"status":"error","message":"name must be a single string"}`.
  - Non-string guard path -> `422` with `{"status":"error","message":"name must be a string"}`.

## External API Integration
- Genderize integration is encapsulated in `GenderizeService` in `app/services/genderize.py`.
- Endpoint used: `https://api.genderize.io`.
- Request pattern: async GET with query params `{"name": <value>}`.
- HTTP client lifecycle is managed in FastAPI lifespan (`app/main.py`) so one shared async client is reused across requests.
- Network and parsing errors are translated into `UpstreamServiceError` to avoid leaking low-level exceptions.

## Data Extraction Accuracy
- The service extracts these fields from Genderize response JSON:
  - `gender`
  - `probability`
  - `count`
- `count` is converted and stored as `sample_size` in `GenderizePayload` and then returned in response model.
- `probability` is converted to float and constrained by model schema (`0.0 <= probability <= 1.0`).
- `sample_size` is converted to int and constrained by model schema (`sample_size >= 0`).
- If payload is malformed (non-object JSON, missing required keys, non-castable values), the request is treated as upstream failure.

## Confidence Logic
- Implemented in `GenderizeService._build_payload(...)` in `app/services/genderize.py`.
- Rule:
  - `is_confident = (probability >= 0.7) AND (sample_size >= 100)`
- Both conditions must pass; otherwise `is_confident` is `false`.

## Error Handling
- Route-level domain errors are returned in the required shape via `_build_error_response(...)` in `app/api/routes.py`.
- Global exception handlers are defined in `app/main.py` and normalize fallback errors into:
  - `{"status":"error","message":"..."}`
- Status mapping:
  - `400`: missing/empty `name`
  - `422`: invalid `name` form (for example repeated value)
  - `502`: upstream API failures (`UpstreamServiceError`)
  - `500`: unexpected unhandled server errors

## Edge Case Handling
- No prediction case from Genderize (`gender is null` or `count == 0`) raises `NoPredictionAvailableError`.
- That is mapped by `ClassifyService.classify(...)` to:
  - `200` with `{"status":"error","message":"No prediction available for the provided name"}`
- Additional edge guards:
  - non-dict JSON body from upstream -> upstream invalid payload error
  - missing `count` or `probability` -> upstream incomplete payload error
  - non-numeric `count`/`probability` -> upstream invalid payload error

## Response Format and Structure
- Success schema is defined by `SuccessResponse` and `ClassifyData` in `app/models/classify.py`.
- Error schema is defined by `ErrorResponse` in `app/models/classify.py`.
- Success response shape:

```json
{
  "status": "success",
  "data": {
    "name": "<name>",
    "gender": "male",
    "probability": 0.99,
    "sample_size": 1234,
    "is_confident": true,
    "processed_at": "2026-04-01T12:00:00Z"
  }
}
```

- `processed_at` is generated per request in UTC ISO-8601 format by `GenderizeService._processed_at(...)`.

## API Documentation and CORS
- Swagger/OpenAPI metadata is provided on the route decorator in `app/api/routes.py` (`summary`, `responses`, response model union).
- Global app metadata (`title`, `version`, `description`) is configured in `app/main.py`.
- CORS is enabled in `app/main.py` with wildcard origin support (`allow_origins=["*"]`) to satisfy external grader access.

## Stage 1 Implementation Overview

### Persistence and Storage
- Profiles are stored in Supabase and accessed via the official Supabase Python client.
- Credentials are resolved from `SUPABASE_URL` and `SUPABASE_KEY` (or `SUPABASE_SERVICE_ROLE_KEY`).
- The `profiles` table stores both the public profile fields and normalized filter keys so duplicate detection and filtering remain deterministic.
- The `normalized_name` column is unique, which enforces idempotent profile creation by name.

### Profile Creation Flow
- `POST /api/profiles` accepts a JSON body with a `name` field.
- Validation returns:
  - `400` for missing or blank names
  - `422` for non-string values
- On a new name, the service calls three upstream APIs in sequence:
  - Genderize for `gender`, `probability`, and `count`
  - Agify for `age`
  - Nationalize for the highest-probability country
- The created profile response includes:
  - `id` as UUID v7
  - `name`
  - `gender`
  - `gender_probability`
  - `sample_size` from Genderize `count`
  - `age`
  - `age_group`
  - `country_id`
  - `country_probability`
  - `created_at` in UTC ISO-8601 format
- If the same normalized name already exists, the API returns the existing record with:
  - `status: "success"`
  - `message: "Profile already exists"`

### Classification Rules
- Age group mapping is derived from the Agify `age` field:
  - `0-12` -> `child`
  - `13-19` -> `teenager`
  - `20-59` -> `adult`
  - `60+` -> `senior`
- Nationality is selected by the highest `probability` value in the Nationalize `country` array.
- The list endpoint filters on `gender`, `country_id`, and `age_group` using case-insensitive matching.

### Upstream Failure Handling
- `Genderize` returning `gender: null` or `count: 0` is treated as invalid and returns `502` with `Genderize returned an invalid response`.
- `Agify` returning `age: null` is treated as invalid and returns `502` with `Agify returned an invalid response`.
- `Nationalize` returning no country data is treated as invalid and returns `502` with `Nationalize returned an invalid response`.
- Upstream failure responses do not persist a profile.

### Profile Retrieval and Deletion
- `GET /api/profiles/{id}` returns a single stored profile or `404` if not found.
- `GET /api/profiles` returns:
  - `status: "success"`
  - `count`
  - `data` as a list of profile summaries
- `DELETE /api/profiles/{id}` returns `204 No Content` on success and `404` if the profile does not exist.

### Response and Infrastructure Guarantees
- All error responses use the shared envelope:
  - `{ "status": "error", "message": "..." }`
- All timestamps are generated in UTC ISO-8601 format.
- All profile IDs are generated as UUID v7.
- CORS remains enabled with `Access-Control-Allow-Origin: *`.

### Validation Coverage
- The test suite should cover:
  - create success and duplicate-name idempotency
  - get-by-id success and not-found handling
  - list filtering with case-insensitive values
  - delete success and not-found handling
  - Stage 0 validation/status mappings for `GET /api/classify`
  - `502` upstream edge cases for Genderize, Agify, and Nationalize
  - exact response envelopes, timestamps, and UUID formatting
