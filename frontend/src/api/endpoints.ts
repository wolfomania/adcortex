// One function per route of the HTTP API (docs/api.md).
import {
  API_BASE,
  request,
  requestBinary,
  requestData,
  uploadForm,
  type UploadOptions,
} from './client'
import type {
  Analysis,
  AnalysisDetail,
  AppConfig,
  ComparisonState,
  MediaSource,
  SessionInfo,
  ShareLink,
  UploadForm,
  WarmupState,
} from './types'

const enc = encodeURIComponent

export interface HistoryPage {
  items: Analysis[]
  nextBefore: string | null
}

/** Build the multipart body for `POST /api/analyses`. */
export function toFormData(form: UploadForm): FormData {
  const data = new FormData()
  data.set('kind', form.kind)
  if (form.file) {
    data.set('file', form.file, form.file.name)
  }
  if (form.script !== undefined) {
    data.set('script', form.script)
  }
  const name = form.name?.trim()
  if (name) {
    data.set('name', name)
  }
  if (form.language) {
    data.set('language', form.language)
  }
  return data
}

export const api = {
  config: () => requestData<AppConfig>('/config'),
  login: (password: string) =>
    requestData<SessionInfo>('/auth/login', { method: 'POST', json: { password } }),
  logout: () => requestData<SessionInfo>('/auth/logout', { method: 'POST' }),
  warmup: () => requestData<WarmupState>('/warmup', { method: 'POST' }),

  history: async (
    options: { limit?: number; before?: string | null } = {},
  ): Promise<HistoryPage> => {
    const params = new URLSearchParams()
    params.set('limit', String(options.limit ?? 30))
    if (options.before) {
      params.set('before', options.before)
    }
    const { data, meta } = await request<Analysis[]>(`/analyses?${params.toString()}`)
    return { items: data, nextBefore: meta?.next_before ?? null }
  },
  analysis: (id: string) => requestData<AnalysisDetail>(`/analyses/${enc(id)}`),
  status: (id: string) => requestData<Analysis>(`/analyses/${enc(id)}/status`),
  rename: (id: string, name: string) =>
    requestData<Analysis>(`/analyses/${enc(id)}`, { method: 'PATCH', json: { name } }),
  remove: (id: string) => requestData<null>(`/analyses/${enc(id)}`, { method: 'DELETE' }),
  retry: (id: string) => requestData<Analysis>(`/analyses/${enc(id)}/retry`, { method: 'POST' }),
  regenerateReport: (id: string) =>
    requestData<Analysis>(`/analyses/${enc(id)}/report`, { method: 'POST' }),
  share: (id: string) => requestData<ShareLink>(`/analyses/${enc(id)}/share`, { method: 'POST' }),
  create: (form: UploadForm, options?: UploadOptions) =>
    uploadForm<Analysis>('/analyses', toFormData(form), options),

  shared: (token: string) => requestData<AnalysisDetail>(`/shared/${enc(token)}`),

  compare: (aId: string, bId: string) =>
    requestData<ComparisonState>('/compare', { method: 'POST', json: { a_id: aId, b_id: bId } }),
  comparison: (aId: string, bId: string) =>
    requestData<ComparisonState>(`/compare/${enc(aId)}/${enc(bId)}`),

  frames: (source: MediaSource, signal?: AbortSignal) =>
    requestBinary(`${sourcePath(source)}/frames`, signal),
}

/** API path of an analysis's binary routes, for its owner or a share link. */
export function sourcePath(source: MediaSource): string {
  return source.kind === 'analysis' ? `/analyses/${enc(source.id)}` : `/shared/${enc(source.token)}`
}

/** Same-origin URLs for `<video>`, `<audio>`, and `<img>` elements. */
export const mediaUrls = {
  media: (source: MediaSource) => `${API_BASE}${sourcePath(source)}/media`,
  strip: (source: MediaSource) => `${API_BASE}${sourcePath(source)}/strip`,
  keyframe: (source: MediaSource, sceneIndex: number) =>
    `${API_BASE}${sourcePath(source)}/keyframes/${sceneIndex}`,
}

/** A stable cache-key fragment for a media source. */
export function sourceKey(source: MediaSource): string {
  return source.kind === 'analysis' ? `a:${source.id}` : `s:${source.token}`
}
