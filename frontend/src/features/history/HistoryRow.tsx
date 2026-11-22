import { Link } from '@tanstack/react-router'
import { AudioLines, Ellipsis, FileText, Film, LoaderCircle, Pencil, Trash2 } from 'lucide-react'
import { useState } from 'react'

import type { Analysis, MediaKind } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { STATUS_LABELS } from '@/features/analysis/status'
import { formatDateTime, formatDuration, formatRelative } from '@/lib/format'
import { cn } from '@/lib/utils'

import { DeleteDialog } from './DeleteDialog'
import { RenameDialog } from './RenameDialog'

const KIND_ICONS: Record<MediaKind, typeof Film> = {
  video: Film,
  audio: AudioLines,
  text: FileText,
}
const KIND_LABELS: Record<MediaKind, string> = { video: 'Video', audio: 'Audio', text: 'Script' }

function Outcome({ analysis }: { analysis: Analysis }) {
  const { status, summary } = analysis.state
  if (status === 'completed') {
    const index = summary?.response_index
    return (
      <span className="flex flex-col items-end">
        <span className="font-mono text-lg font-semibold tabular-nums">
          {typeof index === 'number' ? Math.round(index) : '–'}
        </span>
        <span className="text-[0.68rem] text-muted-foreground">response index</span>
      </span>
    )
  }
  if (status === 'failed') {
    return <Badge variant="destructive">Failed</Badge>
  }
  return (
    <Badge variant="secondary">
      <LoaderCircle className="animate-spin" aria-hidden />
      {STATUS_LABELS[status]}
    </Badge>
  )
}

export interface HistoryRowProps {
  analysis: Analysis
  selected: boolean
  onToggle: (id: string) => void
  onDeleted: (id: string) => void
}

export function HistoryRow({ analysis, selected, onToggle, onDeleted }: HistoryRowProps) {
  const [dialog, setDialog] = useState<'rename' | 'delete' | null>(null)
  const { meta, state } = analysis
  const Icon = KIND_ICONS[meta.kind]
  const duration = state.summary?.duration_s ?? state.media?.duration_s
  const isCompleted = state.status === 'completed'

  return (
    <li
      className={cn(
        'flex items-center gap-3 px-4 py-3 transition-colors hover:bg-accent/40',
        selected && 'bg-accent/60',
      )}
    >
      <input
        type="checkbox"
        className="size-4 shrink-0 accent-primary disabled:opacity-30"
        checked={selected}
        disabled={!isCompleted}
        onChange={() => onToggle(meta.id)}
        aria-label={`Select “${meta.name}” to compare`}
        title={isCompleted ? 'Select to compare' : 'Only completed analyses can be compared'}
      />
      <Icon className="size-4 shrink-0 text-muted-foreground" aria-label={KIND_LABELS[meta.kind]} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <Link
          to="/a/$id"
          params={{ id: meta.id }}
          className="truncate text-sm font-medium hover:underline focus-visible:underline focus-visible:outline-none"
        >
          {meta.name}
        </Link>
        <span className="truncate text-xs text-muted-foreground">
          <time dateTime={meta.created_at} title={formatDateTime(meta.created_at)}>
            {formatRelative(meta.created_at)}
          </time>
          {typeof duration === 'number' ? ` · ${formatDuration(duration)}` : ''}
          {state.summary?.headline ? ` · ${state.summary.headline}` : ''}
        </span>
      </div>
      <Outcome analysis={analysis} />
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" aria-label={`Actions for “${meta.name}”`}>
            <Ellipsis aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => setDialog('rename')}>
            <Pencil aria-hidden />
            Rename
          </DropdownMenuItem>
          <DropdownMenuItem variant="destructive" onSelect={() => setDialog('delete')}>
            <Trash2 aria-hidden />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <RenameDialog
        analysis={analysis}
        open={dialog === 'rename'}
        onOpenChange={(open) => setDialog(open ? 'rename' : null)}
      />
      <DeleteDialog
        analysis={analysis}
        open={dialog === 'delete'}
        onOpenChange={(open) => setDialog(open ? 'delete' : null)}
        onDeleted={onDeleted}
      />
    </li>
  )
}
