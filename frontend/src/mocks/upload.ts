// Validation of the upload form, as the backend does it (docs/api.md).
import type { AppConfig, ErrorCode, MediaKind } from '@/api/types'

const STATUS: Record<ErrorCode, number> = {
  invalid_input: 422,
  payload_too_large: 413,
  unauthorized: 401,
  not_found: 404,
  conflict: 409,
  rate_limited: 429,
  unavailable: 503,
  internal: 500,
}

/** An error the mock backend answers with (status from the error code). */
export class MockError extends Error {
  readonly code: ErrorCode
  readonly status: number

  constructor(code: ErrorCode, message: string) {
    super(message)
    this.name = 'MockError'
    this.code = code
    this.status = STATUS[code]
  }
}

export interface ParsedUpload {
  kind: MediaKind
  file: File | null
  script: string | null
  name: string | null
  language: string
}

const KINDS: readonly MediaKind[] = ['video', 'audio', 'text']
const MAX_NAME = 120

function megabytes(bytes: number): string {
  return `${Math.round(bytes / (1024 * 1024))} MB`
}

function checkFile(kind: MediaKind, value: FormDataEntryValue | null, config: AppConfig): File {
  if (!(value instanceof File) || value.size === 0) {
    throw new MockError(
      'invalid_input',
      `Attach ${kind === 'video' ? 'a video' : 'an audio'} file.`,
    )
  }
  const limit = config.limits.max_upload_mb * 1024 * 1024
  if (value.size > limit) {
    throw new MockError(
      'payload_too_large',
      `This file is ${megabytes(value.size)}; the limit is ${config.limits.max_upload_mb} MB.`,
    )
  }
  if (kind === 'video' && value.type.startsWith('audio/')) {
    throw new MockError(
      'invalid_input',
      'This file has no video track. Use the Audio tab for sound-only files.',
    )
  }
  if (/too-long/i.test(value.name)) {
    throw new MockError(
      'invalid_input',
      `This file is 4 min 12 s long; the limit is ${config.limits.max_duration_s} s.`,
    )
  }
  return value
}

function checkScript(value: FormDataEntryValue | null, config: AppConfig): string {
  const script = typeof value === 'string' ? value.trim() : ''
  const { min_script_chars: min, max_script_chars: max } = config.limits
  if (script.length < min || script.length > max) {
    throw new MockError(
      'invalid_input',
      `The script must be ${min}-${max} characters; it has ${script.length}.`,
    )
  }
  return script
}

function checkLanguage(value: FormDataEntryValue | null, config: AppConfig): string {
  const language = typeof value === 'string' && value.trim() ? value.trim().toLowerCase() : 'auto'
  if (language !== 'auto' && !config.languages.some((option) => option.code === language)) {
    throw new MockError('invalid_input', `Unsupported language '${language}'.`)
  }
  return language
}

export function parseUpload(form: FormData, config: AppConfig): ParsedUpload {
  const kind = form.get('kind')
  if (typeof kind !== 'string' || !KINDS.includes(kind as MediaKind)) {
    throw new MockError('invalid_input', 'Choose what to upload: video, audio, or text.')
  }
  const mediaKind = kind as MediaKind
  const rawName = form.get('name')
  const name = typeof rawName === 'string' && rawName.trim() ? rawName.trim() : null
  if (name && name.length > MAX_NAME) {
    throw new MockError('invalid_input', `Names can be at most ${MAX_NAME} characters.`)
  }
  return {
    kind: mediaKind,
    file: mediaKind === 'text' ? null : checkFile(mediaKind, form.get('file'), config),
    script: mediaKind === 'text' ? checkScript(form.get('script'), config) : null,
    name,
    language: checkLanguage(form.get('language'), config),
  }
}

/** The default name: the file name without extension, or the script's first words. */
export function defaultName(upload: ParsedUpload): string {
  if (upload.file) {
    return upload.file.name.replace(/\.[^.]+$/, '').slice(0, MAX_NAME) || 'Untitled'
  }
  const words = (upload.script ?? '').split(/\s+/).slice(0, 6).join(' ')
  return words.length > 60 ? `${words.slice(0, 57)}...` : words || 'Untitled script'
}
