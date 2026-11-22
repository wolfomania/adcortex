# HTTP API

The single-page app and the backend share this contract. Request and response
models live in `backend/src/neuromarketing/api/schemas.py` and
`backend/src/neuromarketing/domain/models.py`. The frontend generates its
TypeScript types from them:

```sh
cd backend && uv run python scripts/export_api_schema.py ../frontend/src/api/schema.json
```

## Conventions

- All routes live under `/api`. Every other path serves the app (`index.html` for
  client routes, hashed assets with `Cache-Control: immutable`).
- JSON responses use one envelope:

  ```json
  { "ok": true, "data": { "...": "..." }, "error": null, "meta": null }
  { "ok": false, "data": null, "error": { "code": "not_found", "message": "Analysis not found." } }
  ```

  `error.message` is written for the person using the app; show it as is.
- Error codes and statuses: `invalid_input` 422, `payload_too_large` 413,
  `unauthorized` 401, `not_found` 404, `conflict` 409, `rate_limited` 429,
  `unavailable` 503, `internal` 500.
- Times are ISO 8601 in UTC. Media times are seconds from the start of the clip.
- Analysis ids match `^\d{8}-\d{6}-[0-9a-f]{6}$` and sort by creation time.

## Authentication

Authentication is optional. With `NM_PASSWORD` set, every route except
`/api/health`, `/api/config`, `/api/auth/*`, and `/api/shared/*` requires the
session cookie and otherwise returns `401 unauthorized`. The app then sends
the person to `/login?next=<path>`.

| Method | Path | Body | Response `data` |
|---|---|---|---|
| GET | `/api/config` | | `AppConfig` |
| POST | `/api/auth/login` | `LoginRequest` | `SessionInfo`; sets the `nm_session` cookie (HttpOnly, SameSite=Lax) |
| POST | `/api/auth/logout` | | `SessionInfo`; clears the cookie |
| GET | `/api/health` | | `Health` |

A wrong password returns `401`. More than 5 attempts per minute from one
address return `429`.

## Analyses

| Method | Path | Body | Response `data` |
|---|---|---|---|
| POST | `/api/analyses` | multipart form, see below | `Analysis` (202) |
| GET | `/api/analyses?limit=&before=` | | `Analysis[]`, newest first; `meta.next_before` pages |
| GET | `/api/analyses/{id}` | | `AnalysisDetail` |
| GET | `/api/analyses/{id}/status` | | `Analysis` |
| PATCH | `/api/analyses/{id}` | `RenameRequest` | `Analysis` |
| DELETE | `/api/analyses/{id}` | | `null`; cancels a running job |
| POST | `/api/analyses/{id}/retry` | | `Analysis` (202); only when `failed` |
| POST | `/api/analyses/{id}/report` | | `Analysis` (202); regenerates the report of a `completed` analysis |
| POST | `/api/analyses/{id}/share` | | `ShareLink` |
| POST | `/api/warmup` | | `WarmupState`; starts the GPU worker ahead of an upload |

`limit` is 1–100 (default 30). History items carry `progress: null`; poll
`/status` for live progress.

### Upload form (`POST /api/analyses`)

| Field | Required | Notes |
|---|---|---|
| `kind` | yes | `video`, `audio`, or `text` (the upload tab) |
| `file` | for `video` and `audio` | at most `AppConfig.limits.max_upload_mb` |
| `script` | for `text` | `min_script_chars`–`max_script_chars` characters; read aloud by text-to-speech |
| `name` | no | 1–120 characters; defaults to the file name or the script's first words |
| `language` | no | `auto` (default) or a code from `AppConfig.languages`; scripts default to `en` |

The server probes the media before accepting it. Wrong track types and
durations outside `min_duration_s`–`max_duration_s` return `422` at once.

### Processing

`Analysis.state.status` moves through `queued → preparing → (waiting_for_gpu)
→ predicting → analyzing → (interpreting) → completed`, or ends in `failed`
with `state.error`. While the analysis runs, `Analysis.progress` carries a
`message` and an overall `fraction` (0–1). Poll `/status` about every 1.5 s
until the status is `completed` or `failed`, then load the detail.

`state.llm` describes the written report: `ok`, `skipped` (no model
configured), or `failed` with `error`. A failed report leaves the metrics in
place, and `POST /report` regenerates it. `state.reused_from` names an earlier
analysis of the identical file whose prediction was reused.

### Media and brain data

These routes return binary data with `ETag` and `Cache-Control: private,
max-age=31536000, immutable`. Media supports HTTP range requests.

| Path | Content |
|---|---|
| `/api/analyses/{id}/media` | `video/mp4` (H.264/AAC, ≤720p) or `audio/mp4` (AAC) |
| `/api/analyses/{id}/frames` | `application/octet-stream`, see below |
| `/api/analyses/{id}/keyframes/{scene_index}` | `image/jpeg`, one frame from the middle of the scene (video only) |
| `/api/analyses/{id}/strip` | `image/jpeg` thumbnail strip (video only) |

**Brain frames.** The body holds `result.frames.n_frames × n_vertices` bytes,
row-major. Frame `k` covers second `[k, k+1)`. Vertices follow fsaverage5:
left hemisphere `0–10241`, then right `10242–20483`, matching
`/brain/mesh.bin`. Byte `b` maps to `z = vmin + b / 255 × (vmax − vmin)`
(`vmin = −3`, `vmax = 3`, so 128 ≈ the average response).

**Thumbnail strip.** A grid with `result.strip_columns` columns of 160 px wide
tiles. Tile `k` (row `k // columns`, column `k % columns`) shows second `k`.
There are `floor(duration_s) + 1` tiles.

**Audio envelope.** `result.envelope` samples loudness at `result.envelope_hz`
(10 Hz), scaled to 0–1.

## Sharing

A share link gives read-only access to one analysis without the password.
The token is signed, expires after 30 days, and stops working when the
analysis is deleted.

| Method | Path | Response |
|---|---|---|
| GET | `/api/shared/{token}` | `AnalysisDetail` |
| GET | `/api/shared/{token}/media`, `/frames`, `/keyframes/{i}`, `/strip` | as for analyses |

The app's read-only view lives at `/s/{token}`.

## Comparison

| Method | Path | Body | Response `data` |
|---|---|---|---|
| POST | `/api/compare` | `CompareRequest` | `ComparisonState`: `completed` with the stored comparison (200), or `running` (202) |
| GET | `/api/compare/{a_id}/{b_id}` | | `ComparisonState` |

Both analyses must be `completed`; otherwise the server returns `409`. Without a
report model it returns `503 unavailable`; the compare view still shows both
analyses' metrics side by side. Poll the GET route while `running`. A
`failed` state carries `error`.
