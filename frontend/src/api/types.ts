// Types of the HTTP API (see docs/api.md).
//
// Domain and response models are generated from the backend's JSON Schema
// (./schema.ts). The envelope and the upload form are not part of that
// schema, so they are declared here.
import type { ApiError, MediaKind, PageMeta } from './schema'

export type * from './schema'

export type ErrorCode = ApiError['code']

/** Every JSON response: `{ ok, data, error, meta }`. */
export interface Envelope<T> {
  ok: boolean
  data: T | null
  error: ApiError | null
  meta?: PageMeta | null
}

/** Fields of the multipart form sent to `POST /api/analyses`. */
export interface UploadForm {
  kind: MediaKind
  /** Video or audio file; required for `video` and `audio`. */
  file?: File
  /** Script read aloud by text-to-speech; required for `text`. */
  script?: string
  name?: string
  /** `auto` or a language code from `AppConfig.languages`. */
  language?: string
}

/** Where the binary routes of an analysis live: owner access or a share link. */
export type MediaSource = { kind: 'analysis'; id: string } | { kind: 'shared'; token: string }

export type LlmStatus = 'ok' | 'skipped' | 'failed'
