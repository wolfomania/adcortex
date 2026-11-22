// Mock Service Worker handlers for every route in docs/api.md.
import {
  bypass,
  delay,
  http,
  HttpResponse,
  type HttpResponseResolver,
  type JsonBodyType,
} from 'msw'

import type { ApiError, ErrorCode, PageMeta } from '@/api/types'

import type { MockDb } from './db'
import { parseMultipart } from './multipart'
import { clipOf, type MockRecord } from './records'
import { MockError, parseUpload } from './upload'

const API = '*/api'
const PUBLIC_PREFIXES = ['/api/health', '/api/config', '/api/auth/', '/api/shared/']
const BINARY_CACHE = 'private, max-age=31536000, immutable'

type Params = Record<string, string | readonly string[] | undefined>

function ok<T>(data: T, status = 200, meta: PageMeta | null = null): Response {
  const body = { ok: true, data, error: null, meta }
  return HttpResponse.json(body as JsonBodyType, { status })
}

function fail(code: ErrorCode, message: string, status: number): Response {
  const error: ApiError = { code, message }
  const body = { ok: false, data: null, error, meta: null }
  return HttpResponse.json(body as JsonBodyType, { status })
}

function param(params: Params, name: string): string {
  const value = params[name]
  return typeof value === 'string' ? value : ''
}

async function readJson(request: Request): Promise<Record<string, unknown>> {
  try {
    const body: unknown = await request.json()
    if (typeof body === 'object' && body !== null && !Array.isArray(body)) {
      return body as Record<string, unknown>
    }
  } catch {
    // Fall through to the validation error.
  }
  throw new MockError('invalid_input', 'The request body must be a JSON object.')
}

async function readForm(request: Request): Promise<FormData> {
  const copy = request.clone()
  try {
    return await request.formData()
  } catch {
    try {
      return parseMultipart(await copy.arrayBuffer(), request.headers.get('content-type'))
    } catch {
      throw new MockError('invalid_input', 'Send the upload as a multipart form.')
    }
  }
}

function stringField(body: Record<string, unknown>, name: string): string {
  const value = body[name]
  if (typeof value !== 'string') {
    throw new MockError('invalid_input', `Field '${name}' is required.`)
  }
  return value
}

/** Forward a request for a fixture file to the dev server, keeping its Range header. */
async function serveAsset(url: string, request: Request, contentType: string): Promise<Response> {
  const headers = new Headers()
  const range = request.headers.get('range')
  if (range) {
    headers.set('range', range)
  }
  const upstream = await fetch(bypass(new Request(new URL(url, request.url), { headers })))
  if (!upstream.ok) {
    return fail('not_found', 'Media not found.', 404)
  }
  const out = new Headers(upstream.headers)
  out.set('Content-Type', contentType)
  out.set('Cache-Control', BINARY_CACHE)
  out.set('Accept-Ranges', 'bytes')
  return new HttpResponse(upstream.body, { status: upstream.status, headers: out })
}

function requireVideo(record: MockRecord): void {
  if (clipOf(record).kind !== 'video') {
    throw new MockError('not_found', 'This analysis has no video.')
  }
}

/** Binary routes, shared by owners (`/analyses/:id`) and share links (`/shared/:token`). */
function binaryHandlers(
  prefix: string,
  resolveId: (db: MockDb, params: Params) => string,
  getDb: () => MockDb,
) {
  const record = (params: Params) => {
    const db = getDb()
    return db.record(resolveId(db, params))
  }
  return [
    http.get(
      `${API}/${prefix}/media`,
      guard(
        getDb,
        ({ params, request }) => {
          const clip = clipOf(record(params))
          return serveAsset(clip.mediaUrl, request, clip.mediaType)
        },
        { latency: false },
      ),
    ),
    http.get(
      `${API}/${prefix}/strip`,
      guard(
        getDb,
        ({ params, request }) => {
          const found = record(params)
          requireVideo(found)
          return serveAsset(clipOf(found).stripUrl ?? '', request, 'image/jpeg')
        },
        { latency: false },
      ),
    ),
    http.get(
      `${API}/${prefix}/keyframes/:index`,
      guard(
        getDb,
        ({ params, request }) => {
          const found = record(params)
          requireVideo(found)
          const url = clipOf(found).keyframeUrls[Number(param(params, 'index'))]
          if (!/^\d+$/.test(param(params, 'index')) || !url) {
            throw new MockError('not_found', 'Scene not found.')
          }
          return serveAsset(url, request, 'image/jpeg')
        },
        { latency: false },
      ),
    ),
    http.get(
      `${API}/${prefix}/frames`,
      guard(getDb, async ({ params }) => {
        const db = getDb()
        const id = resolveId(db, params)
        const bytes = await db.frames(id)
        const body = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
        return HttpResponse.arrayBuffer(body as ArrayBuffer, {
          headers: {
            'Content-Type': 'application/octet-stream',
            'Cache-Control': BINARY_CACHE,
            ETag: `"${id}-frames"`,
          },
        })
      }),
    ),
  ]
}

interface GuardOptions {
  /** Add the scenario's latency (JSON routes); media streams skip it. */
  latency?: boolean
}

/** Add latency, the password gate, and the error envelope to a resolver. */
function guard(
  getDb: () => MockDb,
  resolver: (info: { params: Params; request: Request }) => Response | Promise<Response>,
  options: GuardOptions = {},
): HttpResponseResolver<Params> {
  return async ({ request, params }) => {
    const db = getDb()
    if (options.latency !== false && db.scenario.latencyMs > 0) {
      await delay(db.scenario.latencyMs)
    }
    const path = new URL(request.url).pathname
    const open = PUBLIC_PREFIXES.some((prefix) => path.startsWith(prefix))
    if (!open && !db.isAuthenticated()) {
      return fail('unauthorized', 'Log in to continue.', 401)
    }
    try {
      return await resolver({ params, request })
    } catch (error) {
      if (error instanceof MockError) {
        return fail(error.code, error.message, error.status)
      }
      console.error('Mock backend error', error)
      return fail('internal', 'Something went wrong on our side. Try again.', 500)
    }
  }
}

function parseLimit(url: URL): number {
  const raw = url.searchParams.get('limit')
  const limit = raw === null ? 30 : Number(raw)
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new MockError('invalid_input', 'limit must be a whole number from 1 to 100.')
  }
  return limit
}

/** All mock routes. `getDb` is read per request, so tests can swap the backend. */
export function createHandlers(getDb: () => MockDb) {
  const route = (
    resolver: Parameters<typeof guard>[1],
    options?: GuardOptions,
  ): HttpResponseResolver<Params> => guard(getDb, resolver, options)
  const id = (params: Params) => param(params, 'id')

  return [
    http.get(
      `${API}/health`,
      route(() => ok({ status: 'ok', version: getDb().config().version })),
    ),
    http.get(
      `${API}/config`,
      route(() => ok(getDb().config())),
    ),
    http.post(
      `${API}/auth/login`,
      route(async ({ request }) => {
        const body = await readJson(request)
        return ok(getDb().login(stringField(body, 'password')))
      }),
    ),
    http.post(
      `${API}/auth/logout`,
      route(() => ok(getDb().logout())),
    ),
    http.post(
      `${API}/warmup`,
      route(() => ok(getDb().warmup())),
    ),

    http.get(
      `${API}/analyses`,
      route(({ request }) => {
        const url = new URL(request.url)
        const page = getDb().list(parseLimit(url), url.searchParams.get('before'))
        return ok(page.items, 200, { next_before: page.nextBefore })
      }),
    ),
    http.post(
      `${API}/analyses`,
      route(async ({ request }) => {
        const db = getDb()
        return ok(db.create(parseUpload(await readForm(request), db.config())), 202)
      }),
    ),
    http.get(
      `${API}/analyses/:id`,
      route(({ params }) => ok(getDb().detail(id(params)))),
    ),
    http.get(
      `${API}/analyses/:id/status`,
      route(({ params }) => ok(getDb().status(id(params)))),
    ),
    http.patch(
      `${API}/analyses/:id`,
      route(async ({ params, request }) => {
        const body = await readJson(request)
        return ok(getDb().rename(id(params), stringField(body, 'name')))
      }),
    ),
    http.delete(
      `${API}/analyses/:id`,
      route(({ params }) => {
        getDb().remove(id(params))
        return ok(null)
      }),
    ),
    http.post(
      `${API}/analyses/:id/retry`,
      route(({ params }) => ok(getDb().retry(id(params)), 202)),
    ),
    http.post(
      `${API}/analyses/:id/report`,
      route(({ params }) => ok(getDb().regenerateReport(id(params)), 202)),
    ),
    http.post(
      `${API}/analyses/:id/share`,
      route(({ params }) => ok(getDb().share(id(params)))),
    ),
    ...binaryHandlers('analyses/:id', (_db, params) => id(params), getDb),

    http.get(
      `${API}/shared/:token`,
      route(({ params }) => {
        const db = getDb()
        const detail = db.detail(db.sharedId(param(params, 'token')))
        return ok(detail)
      }),
    ),
    ...binaryHandlers('shared/:token', (db, params) => db.sharedId(param(params, 'token')), getDb),

    http.post(
      `${API}/compare`,
      route(async ({ request }) => {
        const body = await readJson(request)
        const state = getDb().compare(stringField(body, 'a_id'), stringField(body, 'b_id'))
        return ok(state, state.status === 'running' ? 202 : 200)
      }),
    ),
    http.get(
      `${API}/compare/:a/:b`,
      route(({ params }) => ok(getDb().comparison(param(params, 'a'), param(params, 'b')))),
    ),

    http.all(
      `${API}/*`,
      route(() => {
        throw new MockError('not_found', 'No such API route.')
      }),
    ),
  ]
}
