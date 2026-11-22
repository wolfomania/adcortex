// Choosing the two analyses to compare.
import { useInfiniteQuery } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import { ChevronDown } from 'lucide-react'
import { useId } from 'react'

import { historyQuery } from '@/api/queries'
import type { Analysis } from '@/api/types'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

import { Swatch } from './CompareCharts'

function Picker({
  side,
  value,
  options,
  onChange,
}: {
  side: 'a' | 'b'
  value: string | undefined
  options: Analysis[]
  onChange: (id: string | undefined) => void
}) {
  const id = useId()
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="flex items-center gap-1.5 text-sm font-medium">
        <Swatch side={side} />
        {side.toUpperCase()}
      </label>
      <div className="relative">
        <select
          id={id}
          value={value ?? ''}
          onChange={(event) => onChange(event.target.value || undefined)}
          className={cn(
            'h-9 w-full appearance-none rounded-lg border border-input bg-input/20 pr-9 pl-3 text-sm text-foreground outline-none',
            'hover:bg-input/30 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/40',
          )}
        >
          <option value="">Choose an analysis</option>
          {options.map((analysis) => (
            <option key={analysis.meta.id} value={analysis.meta.id}>
              {analysis.meta.name}
            </option>
          ))}
        </select>
        <ChevronDown
          aria-hidden
          className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-muted-foreground"
        />
      </div>
    </div>
  )
}

export function ComparePicker({ a, b }: { a: string | undefined; b: string | undefined }) {
  const navigate = useNavigate()
  const history = useInfiniteQuery(historyQuery())
  const completed = (history.data?.pages ?? [])
    .flatMap((page) => page.items)
    .filter((analysis) => analysis.state.status === 'completed')

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-4 py-12 sm:px-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Compare two analyses</h1>
        <p className="text-sm text-muted-foreground">
          See their scores, responses over time, and brain systems side by side.
        </p>
      </div>
      {history.isPending ? (
        <Skeleton className="h-24 w-full" />
      ) : completed.length < 2 ? (
        <p className="text-sm text-muted-foreground">
          Comparing needs two completed analyses.{' '}
          <Link to="/" className="underline underline-offset-4 hover:text-foreground">
            Analyze another ad
          </Link>{' '}
          first.
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          <Picker
            side="a"
            value={a}
            options={completed.filter((analysis) => analysis.meta.id !== b)}
            onChange={(next) => void navigate({ to: '/compare', search: { a: next, b } })}
          />
          <Picker
            side="b"
            value={b}
            options={completed.filter((analysis) => analysis.meta.id !== a)}
            onChange={(next) => void navigate({ to: '/compare', search: { a, b: next } })}
          />
        </div>
      )}
    </div>
  )
}
