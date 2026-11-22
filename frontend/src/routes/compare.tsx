// Two analyses side by side, with an optional written verdict.
import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { ArrowLeftRight, CircleAlert } from 'lucide-react'

import { errorMessage } from '@/api/errors'
import { analysisQuery } from '@/api/queries'
import { StateMessage } from '@/components/StateMessage'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  ResponseChart,
  ScoreComparison,
  Swatch,
  SystemComparison,
} from '@/features/compare/CompareCharts'
import { ComparePicker } from '@/features/compare/ComparePicker'
import { ComparisonReportPanel } from '@/features/compare/ComparisonReportPanel'
import { useDocumentTitle } from '@/lib/useDocumentTitle'

interface CompareSearch {
  a?: string
  b?: string
}

const text = (value: unknown) => (typeof value === 'string' && value ? value : undefined)

export const Route = createFileRoute('/compare')({
  validateSearch: (search: Record<string, unknown>): CompareSearch => ({
    a: text(search.a),
    b: text(search.b),
  }),
  component: ComparePage,
})

function ComparePage() {
  const { a, b } = Route.useSearch()
  useDocumentTitle('Compare')
  if (!a || !b || a === b) {
    return <ComparePicker a={a} b={b === a ? undefined : b} />
  }
  return <Comparison aId={a} bId={b} />
}

function Comparison({ aId, bId }: { aId: string; bId: string }) {
  const a = useQuery(analysisQuery(aId))
  const b = useQuery(analysisQuery(bId))

  if (a.isPending || b.isPending) {
    return (
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6" aria-busy>
        <Skeleton className="h-12 w-96 max-w-full" />
        <Skeleton className="h-48" />
        <Skeleton className="h-64" />
      </div>
    )
  }
  if (a.isError || b.isError) {
    return (
      <StateMessage
        icon={CircleAlert}
        tone="error"
        title="The comparison could not load"
        actions={
          <Button asChild>
            <Link to="/compare">Choose other analyses</Link>
          </Button>
        }
      >
        {errorMessage(a.error ?? b.error)}
      </StateMessage>
    )
  }
  const left = a.data
  const right = b.data
  if (!left.result || !right.result) {
    return (
      <StateMessage
        icon={CircleAlert}
        title="Both analyses must be complete"
        actions={
          <Button asChild>
            <Link to="/compare">Choose other analyses</Link>
          </Button>
        }
      >
        Wait for both to finish, then compare them.
      </StateMessage>
    )
  }
  const named = {
    a: { name: left.analysis.meta.name, result: left.result },
    b: { name: right.analysis.meta.name, result: right.result },
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-4 py-8 sm:px-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">Comparison</h1>
          <ul className="flex flex-col gap-1 text-sm">
            {(['a', 'b'] as const).map((side) => (
              <li key={side} className="flex min-w-0 items-center gap-2">
                <Swatch side={side} />
                <span className="font-mono text-xs text-muted-foreground">
                  {side.toUpperCase()}
                </span>
                <Link
                  to="/a/$id"
                  params={{ id: side === 'a' ? aId : bId }}
                  className="truncate hover:underline"
                >
                  {named[side].name}
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <div className="flex gap-2 print:hidden">
          <Button variant="outline" size="sm" asChild>
            <Link to="/compare" search={{ a: bId, b: aId }}>
              <ArrowLeftRight aria-hidden />
              Swap
            </Link>
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link to="/compare" search={{}}>
              Change
            </Link>
          </Button>
        </div>
      </header>
      <ScoreComparison a={named.a} b={named.b} />
      <ResponseChart a={named.a} b={named.b} />
      <div className="grid items-start gap-8 lg:grid-cols-2">
        <SystemComparison a={named.a} b={named.b} />
        <ComparisonReportPanel aId={aId} bId={bId} nameA={named.a.name} nameB={named.b.name} />
      </div>
    </div>
  )
}
