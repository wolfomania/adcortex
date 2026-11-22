import { AudioLines, Film, LoaderCircle, Upload, X } from 'lucide-react'
import { useId, useRef, useState, type DragEvent } from 'react'

import { Button } from '@/components/ui/button'
import { formatBytes, formatDuration } from '@/lib/format'
import { cn } from '@/lib/utils'

import { ACCEPT, FORMAT_HINT, type FileKind } from './validation'

export interface FileCheck {
  /** Duration read in the browser; null when unknown. */
  duration: number | null
  isProbing: boolean
  error: string | null
}

interface DropzoneProps {
  kind: FileKind
  file: File | null
  check: FileCheck
  maxMb: number
  durationRange: [number, number]
  isDisabled?: boolean
  onFile: (file: File) => void
  onClear: () => void
}

const ICONS = { video: Film, audio: AudioLines } as const

export function Dropzone({
  kind,
  file,
  check,
  maxMb,
  durationRange,
  isDisabled = false,
  onFile,
  onClear,
}: DropzoneProps) {
  const inputId = useId()
  const hintId = useId()
  const input = useRef<HTMLInputElement>(null)
  const [isOver, setIsOver] = useState(false)
  const Icon = ICONS[kind]
  const noun = kind === 'video' ? 'video' : 'audio file'

  const handleDrop = (event: DragEvent<HTMLElement>) => {
    event.preventDefault()
    setIsOver(false)
    const dropped = event.dataTransfer.files[0]
    if (dropped && !isDisabled) {
      onFile(dropped)
    }
  }

  const picker = (
    <input
      ref={input}
      id={inputId}
      type="file"
      accept={ACCEPT[kind]}
      className="sr-only"
      aria-describedby={hintId}
      disabled={isDisabled}
      onChange={(event) => {
        const picked = event.target.files?.[0]
        if (picked) {
          onFile(picked)
        }
        event.target.value = ''
      }}
    />
  )

  if (file) {
    return (
      <div
        className={cn(
          'flex items-center gap-4 rounded-xl border bg-sunken p-4',
          check.error ? 'border-destructive/50' : 'border-border',
        )}
        onDragOver={(event) => event.preventDefault()}
        onDrop={handleDrop}
      >
        {picker}
        <span className="grid size-11 shrink-0 place-items-center rounded-lg border border-border bg-card text-primary">
          <Icon aria-hidden className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium" title={file.name}>
            {file.name}
          </p>
          <p className="tabular mt-0.5 flex items-center gap-1.5 font-mono text-xs text-muted-foreground">
            {formatBytes(file.size)}
            <span aria-hidden>·</span>
            {check.isProbing ? (
              <span className="inline-flex items-center gap-1">
                <LoaderCircle aria-hidden className="size-3 animate-spin" />
                reading length
              </span>
            ) : check.duration !== null ? (
              formatDuration(check.duration)
            ) : (
              'length checked on upload'
            )}
          </p>
          {check.error ? (
            <p role="alert" className="mt-1.5 text-sm text-destructive">
              {check.error}
            </p>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={isDisabled}
            onClick={() => input.current?.click()}
          >
            Replace
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={`Remove ${file.name}`}
            disabled={isDisabled}
            onClick={onClear}
          >
            <X aria-hidden />
          </Button>
        </div>
        <p id={hintId} className="sr-only">
          {FORMAT_HINT[kind]}, up to {maxMb} MB.
        </p>
      </div>
    )
  }

  return (
    <label
      htmlFor={inputId}
      onDragOver={(event) => {
        event.preventDefault()
        setIsOver(true)
      }}
      onDragLeave={() => setIsOver(false)}
      onDrop={handleDrop}
      className={cn(
        'group relative flex cursor-pointer flex-col items-center justify-center overflow-hidden rounded-xl border border-dashed border-input bg-sunken px-6 py-12 text-center transition-colors',
        'hover:border-primary/60 hover:bg-primary/[0.03] has-[:focus-visible]:border-primary has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/40',
        isOver && 'border-primary bg-primary/[0.06]',
        isDisabled && 'pointer-events-none opacity-60',
      )}
    >
      {picker}
      <span className="lab-grid pointer-events-none absolute inset-0 opacity-60" aria-hidden />
      <span className="relative grid size-12 place-items-center rounded-xl border border-border bg-card text-primary shadow-sm transition-transform group-hover:-translate-y-0.5">
        <Upload aria-hidden className="size-5" />
      </span>
      <span className="relative mt-4 text-base font-medium">
        Drop {kind === 'video' ? 'a video' : 'an audio file'} here, or{' '}
        <span className="text-primary underline-offset-4 group-hover:underline">browse</span>
      </span>
      <span id={hintId} className="relative mt-1.5 text-sm text-muted-foreground">
        {FORMAT_HINT[kind]} · up to {maxMb} MB · {durationRange[0]} s to{' '}
        {formatDuration(durationRange[1])}
      </span>
      <span className="sr-only">Choose a {noun}</span>
    </label>
  )
}
