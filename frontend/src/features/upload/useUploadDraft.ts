import { useCallback, useRef, useState } from 'react'

import type { Limits, MediaKind, UploadForm } from '@/api/types'

import type { FileCheck } from './Dropzone'
import { probeDuration } from './probe'
import { checkDuration, checkFile, checkScript, MAX_NAME_LENGTH, type FileKind } from './validation'

const EMPTY_CHECK: FileCheck = { duration: null, isProbing: false, error: null }

export interface UploadDraft {
  kind: MediaKind
  files: Record<FileKind, File | null>
  checks: Record<FileKind, FileCheck>
  script: string
  name: string
  language: string
}

const INITIAL: UploadDraft = {
  kind: 'video',
  files: { video: null, audio: null },
  checks: { video: EMPTY_CHECK, audio: EMPTY_CHECK },
  script: '',
  name: '',
  language: 'auto',
}

/** Why the draft cannot be sent yet, or null when it can. */
export function draftBlocker(draft: UploadDraft, limits: Limits): string | null {
  if (draft.name.trim().length > MAX_NAME_LENGTH) {
    return `Names can be at most ${MAX_NAME_LENGTH} characters.`
  }
  if (draft.kind === 'text') {
    if (!draft.script.trim()) {
      return 'Write or paste a script.'
    }
    return checkScript(draft.script, limits)
  }
  const check = draft.checks[draft.kind]
  if (!draft.files[draft.kind]) {
    return `Choose ${draft.kind === 'video' ? 'a video' : 'an audio file'}.`
  }
  if (check.isProbing) {
    return 'Reading the file…'
  }
  return check.error
}

/** The request body for a ready draft. */
export function toUploadForm(draft: UploadDraft): UploadForm {
  const base = { kind: draft.kind, name: draft.name.trim() || undefined, language: draft.language }
  if (draft.kind === 'text') {
    return { ...base, script: draft.script.trim() }
  }
  return { ...base, file: draft.files[draft.kind] ?? undefined }
}

/** Form state for the upload page, including the in-browser duration check. */
export function useUploadDraft(limits: Limits) {
  const [draft, setDraft] = useState<UploadDraft>(INITIAL)
  // The file each probe was started for; late results for replaced files are dropped.
  const probing = useRef<Record<FileKind, File | null>>({ video: null, audio: null })

  const update = useCallback((change: Partial<UploadDraft>) => {
    setDraft((current) => ({ ...current, ...change }))
  }, [])

  const setCheck = useCallback((kind: FileKind, check: FileCheck) => {
    setDraft((current) => ({ ...current, checks: { ...current.checks, [kind]: check } }))
  }, [])

  const setFile = useCallback(
    (kind: FileKind, file: File | null) => {
      setDraft((current) => ({ ...current, files: { ...current.files, [kind]: file } }))
      probing.current = { ...probing.current, [kind]: file }
      if (!file) {
        setCheck(kind, EMPTY_CHECK)
        return
      }
      const error = checkFile(kind, file, limits)
      setCheck(kind, { duration: null, isProbing: error === null, error })
      if (error !== null) {
        return
      }
      void probeDuration(file, kind).then((duration) => {
        if (probing.current[kind] !== file) {
          return
        }
        const tooLong = duration === null ? null : checkDuration(duration, limits)
        setCheck(kind, { duration, isProbing: false, error: tooLong })
      })
    },
    [limits, setCheck],
  )

  return { draft, update, setFile, blocker: draftBlocker(draft, limits) }
}
