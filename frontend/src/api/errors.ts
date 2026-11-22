import type { ErrorCode } from './types'

/** `network` means the request never got an HTTP response. */
export type RequestErrorCode = ErrorCode | 'network' | 'aborted'

/**
 * A failed API call. `message` comes from the server's envelope and is
 * written for the person using the app, so the UI shows it as is.
 */
export class ApiRequestError extends Error {
  readonly code: RequestErrorCode
  readonly status: number

  constructor(code: RequestErrorCode, message: string, status: number) {
    super(message)
    this.name = 'ApiRequestError'
    this.code = code
    this.status = status
  }
}

export const NETWORK_MESSAGE = 'Cannot reach the server. Check your connection and try again.'
export const UNEXPECTED_MESSAGE = 'The server sent an unexpected response. Try again in a moment.'

const FALLBACK_CODES: Record<number, ErrorCode> = {
  401: 'unauthorized',
  404: 'not_found',
  409: 'conflict',
  413: 'payload_too_large',
  422: 'invalid_input',
  429: 'rate_limited',
  503: 'unavailable',
}

/** The error code to assume when a response carries no envelope. */
export function codeForStatus(status: number): ErrorCode {
  return FALLBACK_CODES[status] ?? 'internal'
}

export function isApiError(error: unknown, code?: RequestErrorCode): error is ApiRequestError {
  return error instanceof ApiRequestError && (code === undefined || error.code === code)
}

/** A message that is safe to show for any thrown value. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    return error.message
  }
  return UNEXPECTED_MESSAGE
}
