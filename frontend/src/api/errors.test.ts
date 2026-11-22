import { describe, expect, it } from 'vitest'

import { ApiRequestError, codeForStatus, errorMessage, isApiError } from './errors'

describe('API errors', () => {
  it('maps bare statuses to codes', () => {
    expect(codeForStatus(429)).toBe('rate_limited')
    expect(codeForStatus(418)).toBe('internal')
  })

  it('shows API messages and hides anything else', () => {
    const refused = new ApiRequestError('conflict', 'Not yet.', 409)

    expect(errorMessage(refused)).toBe('Not yet.')
    expect(errorMessage(new Error('stack trace'))).not.toContain('stack trace')
    expect(isApiError(refused)).toBe(true)
    expect(isApiError(refused, 'not_found')).toBe(false)
    expect(isApiError('conflict')).toBe(false)
  })
})
