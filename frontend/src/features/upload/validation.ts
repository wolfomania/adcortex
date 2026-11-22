// Client-side checks that mirror the backend's, so mistakes show before upload.
import type { Limits } from '@/api/types'
import { formatBytes } from '@/lib/format'

export type FileKind = 'video' | 'audio'

const EXTENSIONS: Record<FileKind, readonly string[]> = {
  video: ['.mp4', '.mov', '.m4v', '.webm', '.mkv', '.avi', '.mpeg', '.mpg'],
  audio: ['.mp3', '.wav', '.m4a', '.aac', '.ogg', '.oga', '.flac', '.opus', '.weba'],
}

/** `accept` attribute values for the file pickers. */
export const ACCEPT: Record<FileKind, string> = {
  video: ['video/*', ...EXTENSIONS.video].join(','),
  audio: ['audio/*', ...EXTENSIONS.audio].join(','),
}

export const FORMAT_HINT: Record<FileKind, string> = {
  video: 'MP4, MOV, WebM, or MKV',
  audio: 'MP3, WAV, M4A, AAC, OGG, or FLAC',
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot < 0 ? '' : name.slice(dot).toLowerCase()
}

/** Does the file look like the kind of media the tab asks for? */
export function matchesKind(kind: FileKind, file: Pick<File, 'name' | 'type'>): boolean {
  if (file.type.startsWith(`${kind}/`)) {
    return true
  }
  if (kind === 'audio' && file.type.startsWith('video/')) {
    // A video's sound track can be analyzed on its own.
    return true
  }
  return !file.type && EXTENSIONS[kind].includes(extensionOf(file.name))
}

/** The first problem with a picked file, or null. */
export function checkFile(
  kind: FileKind,
  file: Pick<File, 'name' | 'type' | 'size'>,
  limits: Limits,
): string | null {
  if (file.size === 0) {
    return 'This file is empty.'
  }
  if (kind === 'video' && file.type.startsWith('audio/')) {
    return 'This is an audio file. Use the Audio tab for sound-only spots.'
  }
  if (!matchesKind(kind, file)) {
    return `This does not look like ${kind === 'video' ? 'a video' : 'an audio'} file. Use ${FORMAT_HINT[kind]}.`
  }
  if (file.size > limits.max_upload_mb * 1024 * 1024) {
    return `This file is ${formatBytes(file.size)}; the limit is ${limits.max_upload_mb} MB.`
  }
  return null
}

/** The problem with a media duration (seconds), or null. */
export function checkDuration(seconds: number, limits: Limits): string | null {
  if (seconds < limits.min_duration_s) {
    return `This clip is ${seconds.toFixed(1)} s long; it must be at least ${limits.min_duration_s} s.`
  }
  if (seconds > limits.max_duration_s) {
    return `This clip is ${Math.round(seconds)} s long; the limit is ${limits.max_duration_s} s.`
  }
  return null
}

/** The problem with a script, or null; `null` while it is still empty. */
export function checkScript(text: string, limits: Limits): string | null {
  const length = text.trim().length
  if (length === 0) {
    return null
  }
  if (length < limits.min_script_chars) {
    return `Write at least ${limits.min_script_chars} characters.`
  }
  if (length > limits.max_script_chars) {
    return `Scripts can be at most ${limits.max_script_chars} characters; this one has ${length}.`
  }
  return null
}

export const MAX_NAME_LENGTH = 120

/** The name the backend gives an analysis without one: the file name, or the script's first words. */
export function defaultName(source: { file?: Pick<File, 'name'> | null; script?: string }): string {
  if (source.file) {
    return source.file.name.replace(/\.[^.]+$/, '').slice(0, MAX_NAME_LENGTH)
  }
  const words = (source.script ?? '').trim().split(/\s+/).slice(0, 6).join(' ')
  return words.length > 60 ? `${words.slice(0, 57)}...` : words
}
