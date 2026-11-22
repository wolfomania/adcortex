// Low-level HTTP helpers for the `/api` routes: JSON envelopes, binary
// downloads, and multipart uploads with progress.
import { ApiRequestError, codeForStatus, NETWORK_MESSAGE, UNEXPECTED_MESSAGE } from './errors'
import type { Envelope, PageMeta } from './types'

export const API_BASE = '/api'

export interface ApiResult<T> {
  data: T
  meta: PageMeta | null
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  json?: unknown
  signal?: AbortSignal
}

/** Absolute URL of an API path, so requests work outside a browser page too. */
export function apiUrl(path: string): string {
  return new URL(`${API_BASE}${path}`, window.location.origin).toString()
}

function isEnvelope(value: unknown): value is Envelope<unknown> {
  return typeof value === 'object' && value !== null && 'ok' in value
}

/** Turn a parsed body into data, or throw the error it describes. */
export function unwrap<T>(status: number, body: unknown): ApiResult<T> {
  if (!isEnvelope(body)) {
    throw new ApiRequestError(codeForStatus(status), UNEXPECTED_MESSAGE, status)
  }
  if (!body.ok || status >= 400) {
    const error = body.error
    throw new ApiRequestError(
      error?.code ?? codeForStatus(status),
      error?.message ?? UNEXPECTED_MESSAGE,
      status,
    )
  }
  return { data: body.data as T, meta: body.meta ?? null }
}

async function send(path: string, options: RequestOptions, accept: string): Promise<Response> {
  const headers: Record<string, string> = { Accept: accept }
  let body: BodyInit | undefined
  if (options.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.json)
  }
  try {
    return await fetch(apiUrl(path), {
      method: options.method ?? 'GET',
      headers,
      body,
      credentials: 'same-origin',
      signal: options.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiRequestError('aborted', 'The request was cancelled.', 0)
    }
    throw new ApiRequestError('network', NETWORK_MESSAGE, 0)
  }
}

/** The response's JSON body, or null when it has none. */
async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    return null
  }
}

/** Parsed JSON, or null when the text is not JSON. */
function parseJson(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

/** Call a JSON route and return its envelope's data and meta. */
export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<ApiResult<T>> {
  const response = await send(path, options, 'application/json')
  const body = await readJson(response)
  return unwrap<T>(response.status, body)
}

/** Call a JSON route and return only its data. */
export async function requestData<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return (await request<T>(path, options)).data
}

/** Download a binary route (brain frames). Errors still arrive as envelopes. */
export async function requestBinary(path: string, signal?: AbortSignal): Promise<ArrayBuffer> {
  const response = await send(path, { signal }, 'application/octet-stream, application/json')
  if (!response.ok) {
    const body = await readJson(response)
    unwrap(response.status, body)
  }
  return response.arrayBuffer()
}

export interface UploadOptions {
  onProgress?: (fraction: number) => void
  signal?: AbortSignal
}

/**
 * POST a multipart form with upload progress. `fetch` cannot report upload
 * progress, so this uses XMLHttpRequest.
 */
export function uploadForm<T>(
  path: string,
  form: FormData,
  options: UploadOptions = {},
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', apiUrl(path))
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.withCredentials = false
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        options.onProgress?.(event.loaded / event.total)
      }
    }
    xhr.onload = () => {
      const body = parseJson(xhr.responseText)
      try {
        resolve(unwrap<T>(xhr.status, body).data)
      } catch (error) {
        reject(error)
      }
    }
    xhr.onerror = () => reject(new ApiRequestError('network', NETWORK_MESSAGE, 0))
    xhr.onabort = () => reject(new ApiRequestError('aborted', 'The upload was cancelled.', 0))
    if (options.signal) {
      if (options.signal.aborted) {
        reject(new ApiRequestError('aborted', 'The upload was cancelled.', 0))
        return
      }
      options.signal.addEventListener('abort', () => xhr.abort(), { once: true })
    }
    xhr.send(form)
  })
}
