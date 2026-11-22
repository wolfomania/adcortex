// Every analysis, newest first. Pick two to compare them.
import { useInfiniteQuery } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { CircleAlert, GitCompareArrows, Inbox } from 'lucide-react'
import { useState } from 'react'

import { errorMessage } from '@/api/errors'
import { historyQuery } from '@/api/queries'
import { StateMessage } from '@/components/StateMessage'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { isTerminal } from '@/features/analysis/status'
import { HistoryRow } from '@/features/history/HistoryRow'
import { COMPARE_SIZE, toggleSelection } from '@/features/history/selection'
import { useDocumentTitle } from '@/lib/useDocumentTitle'

/** How often the list refreshes while an analysis on it is still running. */
const RUNNING_REFRESH_MS = 5000

export const Route = createFileRoute('/history')({
  loader: ({ context }) => context.queryClient.prefetchInfiniteQuery(historyQuery()),
  component: HistoryPage,
})

function HistoryPage() {
  const navigate = useNavigate()
  const [selected, setSelected] = useState<string[]>([])
  useDocumentTitle('History')
  const history = useInfiniteQuery({
    ...historyQuery(),
    refetchInterval: (query) =>
      query.state.data?.pages.some((page) =>
        page.items.some((item) => !isTerminal(item.state.status)),
      )
        ? RUNNING_REFRESH_MS
        : false,
  })

  let body: React.ReactNode
  if (history.isPending) {
    body = (
      <div className="flex flex-col gap-2" aria-busy>
        {[0, 1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-14" />
        ))}
      </div>
    )
  } else if (history.isError) {
    body = (
      <StateMessage
        icon={CircleAlert}
        tone="error"
        title="History could not load"
        actions={<Button onClick={() => void history.refetch()}>Try again</Button>}
      >
        {errorMessage(history.error)}
      </StateMessage>
    )
  } else {
    const items = history.data.pages.flatMap((page) => page.items)
    body = items.length ? (
      <>
        <ul className="flex flex-col divide-y overflow-hidden rounded-lg border bg-card">
          {items.map((analysis) => (
            <HistoryRow
              key={analysis.meta.id}
              analysis={analysis}
              selected={selected.includes(analysis.meta.id)}
              onToggle={(id) => setSelected((current) => toggleSelection(current, id))}
              onDeleted={(id) => setSelected((current) => current.filter((item) => item !== id))}
            />
          ))}
        </ul>
        {history.hasNextPage ? (
          <Button
            variant="outline"
            className="self-center"
            disabled={history.isFetchingNextPage}
            onClick={() => void history.fetchNextPage()}
          >
            {history.isFetchingNextPage ? 'Loading…' : 'Show older analyses'}
          </Button>
        ) : null}
      </>
    ) : (
      <StateMessage
        icon={Inbox}
        title="No analyses yet"
        actions={
          <Button asChild>
            <Link to="/">Analyze an ad</Link>
          </Button>
        }
      >
        Upload a video, an audio spot, or a script to see how a brain would respond.
      </StateMessage>
    )
  }

  const [a, b] = selected
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-8 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight">History</h1>
          <p className="text-sm text-muted-foreground">
            Select two completed analyses to compare them side by side.
          </p>
        </div>
        <Button
          disabled={selected.length !== COMPARE_SIZE}
          onClick={() => void navigate({ to: '/compare', search: { a, b } })}
        >
          <GitCompareArrows aria-hidden />
          Compare{selected.length ? ` (${selected.length}/${COMPARE_SIZE})` : ''}
        </Button>
      </div>
      {body}
    </div>
  )
}
