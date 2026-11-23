import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { ArrowRight, AudioLines, Film, FileText, LoaderCircle } from 'lucide-react'
import { useId, useRef, useState } from 'react'

import { api } from '@/api/endpoints'
import { errorMessage, isApiError } from '@/api/errors'
import { queryKeys } from '@/api/queries'
import type { AppConfig, MediaKind, UploadForm as UploadBody } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

import { Dropzone } from './Dropzone'
import { GpuStatus } from './GpuStatus'
import { LanguageSelect } from './LanguageSelect'
import { ScriptField } from './ScriptField'
import { toUploadForm, useUploadDraft } from './useUploadDraft'
import { useWarmup } from './useWarmup'
import { defaultName, MAX_NAME_LENGTH } from './validation'

const TABS = [
  { kind: 'video', label: 'Video', icon: Film },
  { kind: 'audio', label: 'Audio', icon: AudioLines },
  { kind: 'text', label: 'Script', icon: FileText },
] as const

interface UploadFormProps {
  config: AppConfig
}

export function UploadForm({ config }: UploadFormProps) {
  const { limits, languages } = config
  const { draft, update, setFile, blocker } = useUploadDraft(limits)
  const gpu = useWarmup()
  const nameId = useId()
  const languageId = useId()
  const languageHintId = useId()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const abort = useRef<AbortController | null>(null)
  const [progress, setProgress] = useState<number | null>(null)

  const upload = useMutation({
    mutationFn: (body: UploadBody) => {
      abort.current = new AbortController()
      return api.create(body, { onProgress: setProgress, signal: abort.current.signal })
    },
    onSuccess: async (analysis) => {
      queryClient.setQueryData(queryKeys.status(analysis.meta.id), analysis)
      void queryClient.invalidateQueries({ queryKey: queryKeys.history })
      await navigate({ to: '/a/$id', params: { id: analysis.meta.id } })
    },
    onSettled: () => setProgress(null),
  })

  const isBusy = upload.isPending
  const selected = languages.find((language) => language.code === draft.language)
  const isLimited = selected !== undefined && !selected.full_support
  const placeholder =
    draft.kind === 'text'
      ? defaultName({ script: draft.script }) || 'Named after the script'
      : (draft.files[draft.kind] && defaultName({ file: draft.files[draft.kind] })) ||
        'Named after the file'
  const failure =
    upload.error && !isApiError(upload.error, 'aborted') ? errorMessage(upload.error) : null

  return (
    <form
      noValidate
      aria-label="New analysis"
      className="relative rounded-2xl border border-border bg-card shadow-2xl shadow-black/40"
      onSubmit={(event) => {
        event.preventDefault()
        if (!blocker && !isBusy) {
          upload.mutate(toUploadForm(draft))
        }
      }}
    >
      <Tabs
        value={draft.kind}
        onValueChange={(value) => update({ kind: value as MediaKind })}
        className="gap-0"
      >
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3">
          <TabsList aria-label="What to analyze">
            {TABS.map(({ kind, label, icon: Icon }) => (
              <TabsTrigger key={kind} value={kind} disabled={isBusy} className="px-3">
                <Icon aria-hidden />
                {label}
              </TabsTrigger>
            ))}
          </TabsList>
          <GpuStatus state={gpu} />
        </div>
        <div className="space-y-5 p-5">
          {(['video', 'audio'] as const).map((kind) => (
            <TabsContent key={kind} value={kind} className="mt-0">
              <Dropzone
                kind={kind}
                file={draft.files[kind]}
                check={draft.checks[kind]}
                maxMb={limits.max_upload_mb}
                durationRange={[limits.min_duration_s, limits.max_duration_s]}
                isDisabled={isBusy}
                onFile={(file) => setFile(kind, file)}
                onClear={() => setFile(kind, null)}
              />
            </TabsContent>
          ))}
          <TabsContent value="text" className="mt-0">
            <ScriptField
              value={draft.script}
              limits={limits}
              isDisabled={isBusy}
              onChange={(script) => update({ script })}
            />
          </TabsContent>

          <div className="grid gap-4 sm:grid-cols-[1fr_15rem]">
            <div className="space-y-1.5">
              <Label htmlFor={nameId}>
                Name <span className="font-normal text-muted-foreground">(optional)</span>
              </Label>
              <Input
                id={nameId}
                value={draft.name}
                maxLength={MAX_NAME_LENGTH}
                placeholder={placeholder}
                disabled={isBusy}
                autoComplete="off"
                onChange={(event) => update({ name: event.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={languageId}>
                {draft.kind === 'text' ? 'Script language' : 'Spoken language'}
              </Label>
              <LanguageSelect
                id={languageId}
                value={draft.language}
                languages={languages}
                isDisabled={isBusy}
                describedBy={isLimited ? languageHintId : undefined}
                onChange={(language) => update({ language })}
              />
            </div>
          </div>
          {isLimited ? (
            <p
              id={languageHintId}
              className="rounded-lg border border-status-warning/30 bg-status-warning/10 px-3 py-2 text-sm"
            >
              TRIBE v2 learned from English speech. Results for {selected.name} carry a
              lower-reliability note.
            </p>
          ) : null}
        </div>
      </Tabs>

      <div className="flex flex-col gap-3 border-t border-border px-5 py-4 sm:flex-row sm:items-center">
        <p className="flex-1 text-sm text-muted-foreground" aria-live="polite">
          {isBusy && progress !== null
            ? `Uploading… ${Math.round(progress * 100)}%`
            : (blocker ?? 'Ready. The analysis keeps running if you leave this page.')}
        </p>
        {isBusy ? (
          <Button type="button" variant="ghost" onClick={() => abort.current?.abort()}>
            Cancel upload
          </Button>
        ) : null}
        <Button type="submit" size="lg" disabled={blocker !== null || isBusy} className="px-4">
          {isBusy ? <LoaderCircle aria-hidden className="animate-spin" /> : null}
          Analyze
          {isBusy ? null : <ArrowRight aria-hidden />}
        </Button>
      </div>
      {isBusy && progress !== null ? (
        <div
          className="absolute inset-x-0 bottom-0 h-0.5 overflow-hidden rounded-b-2xl"
          role="progressbar"
          aria-label="Upload progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(progress * 100)}
        >
          <div
            className="h-full bg-primary transition-[width]"
            style={{ width: `${Math.round(progress * 100)}%` }}
          />
        </div>
      ) : null}
      {failure ? (
        <p
          role="alert"
          className="border-t border-destructive/30 bg-destructive/10 px-5 py-3 text-sm"
        >
          {failure}
        </p>
      ) : null}
    </form>
  )
}
