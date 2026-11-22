// The media behind the mock analyses (rendered by scripts/make-mock-media.mjs).
import type { MediaKind } from '@/api/types'

import lumen15Video from '../media/lumen-15s.mp4?url'
import lumen15Strip from '../media/lumen-15s-strip.jpg?url'
import lumen30Video from '../media/lumen-30s.mp4?url'
import lumen30Strip from '../media/lumen-30s-strip.jpg?url'
import radioAudio from '../media/radio-20s.m4a?url'
import scriptAudio from '../media/script-15s.m4a?url'
import timeline from '../media/timeline.json'

const keyframeUrls = import.meta.glob<string>('../media/keyframes/*.jpg', {
  query: '?url',
  import: 'default',
  eager: true,
})

export type ClipId = 'lumen-30s' | 'lumen-15s' | 'radio-20s' | 'script-15s'

/** What a scene shows; drives the synthetic brain response. */
export type SceneKind =
  'title' | 'city' | 'presenter' | 'product' | 'lifestyle' | 'endcard' | 'audio'

export interface ClipScene {
  start: number
  end: number
  kind: SceneKind
}

export interface Sentence {
  text: string
  start: number
  end: number
}

export interface Clip {
  id: ClipId
  kind: MediaKind
  filename: string
  sizeBytes: number
  duration: number
  width: number | null
  height: number | null
  mediaUrl: string
  mediaType: string
  stripUrl: string | null
  keyframeUrls: string[]
  scenes: ClipScene[]
  sentences: Sentence[]
  /** Loudness at 10 Hz, 0-1. */
  envelope: number[]
}

interface VideoTimeline {
  duration: number
  width: number
  height: number
  /** [start, end] pairs in seconds. */
  scenes: number[][]
  sentences: Sentence[]
  envelope: number[]
}

interface AudioTimeline {
  duration: number
  sentences: Sentence[]
  envelope: number[]
}

const SEGMENT_S = 5

/** Equal segments of at most 5 s, as the backend makes for audio and scripts. */
export function uniformScenes(duration: number): ClipScene[] {
  const count = Math.max(1, Math.ceil(duration / SEGMENT_S - 1e-9))
  const step = duration / count
  return Array.from({ length: count }, (_, i) => ({
    start: Math.round(i * step * 1000) / 1000,
    end: i === count - 1 ? duration : Math.round((i + 1) * step * 1000) / 1000,
    kind: 'audio' as const,
  }))
}

function keyframesOf(name: string, count: number): string[] {
  return Array.from({ length: count }, (_, i) => {
    const url = keyframeUrls[`../media/keyframes/${name}-${i}.jpg`]
    if (!url) {
      throw new Error(`Missing mock keyframe ${name}-${i}.jpg; run pnpm gen:mock-media`)
    }
    return url
  })
}

function videoClip(
  id: ClipId,
  data: VideoTimeline,
  urls: { media: string; strip: string },
  kinds: SceneKind[],
  file: { filename: string; sizeBytes: number },
): Clip {
  return {
    id,
    kind: 'video',
    ...file,
    duration: data.duration,
    width: data.width,
    height: data.height,
    mediaUrl: urls.media,
    mediaType: 'video/mp4',
    stripUrl: urls.strip,
    keyframeUrls: keyframesOf(id, data.scenes.length),
    scenes: data.scenes.map(([start = 0, end = 0], i) => ({
      start,
      end,
      kind: kinds[i] ?? 'title',
    })),
    sentences: data.sentences,
    envelope: data.envelope,
  }
}

function audioClip(
  id: ClipId,
  kind: MediaKind,
  data: AudioTimeline,
  media: string,
  file: { filename: string; sizeBytes: number },
): Clip {
  return {
    id,
    kind,
    ...file,
    duration: data.duration,
    width: null,
    height: null,
    mediaUrl: media,
    mediaType: 'audio/mp4',
    stripUrl: null,
    keyframeUrls: [],
    scenes: uniformScenes(data.duration),
    sentences: data.sentences,
    envelope: data.envelope,
  }
}

export const CLIPS: Record<ClipId, Clip> = {
  'lumen-30s': videoClip(
    'lumen-30s',
    timeline['lumen-30s'],
    { media: lumen30Video, strip: lumen30Strip },
    ['title', 'city', 'presenter', 'product', 'lifestyle', 'endcard'],
    { filename: 'lumen_launch_30s_master.mp4', sizeBytes: 48_213_504 },
  ),
  'lumen-15s': videoClip(
    'lumen-15s',
    timeline['lumen-15s'],
    { media: lumen15Video, strip: lumen15Strip },
    ['title', 'product', 'lifestyle', 'endcard'],
    { filename: 'lumen_cutdown_15s.mp4', sizeBytes: 22_806_118 },
  ),
  'radio-20s': audioClip('radio-20s', 'audio', timeline['radio-20s'], radioAudio, {
    filename: 'lumen_radio_20s.wav',
    sizeBytes: 3_528_044,
  }),
  'script-15s': audioClip('script-15s', 'text', timeline['script-15s'], scriptAudio, {
    filename: 'script.txt',
    sizeBytes: 214,
  }),
}

/** The script a text analysis was made from. */
export function scriptText(clip: Clip): string {
  return clip.sentences.map((sentence) => sentence.text).join(' ')
}
