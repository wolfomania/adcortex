// The language model's comparison: started on request, then polled.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle, Sparkles } from 'lucide-react'

import { api } from '@/api/endpoints'
import { errorMessage } from '@/api/errors'
import { comparisonQuery, configQuery, queryKeys } from '@/api/queries'
import { toast } from '@/components/toast-store'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

import { Swatch } from './CompareCharts'

function Strengths({ side, name, items }: { side: 'a' | 'b'; name: string; items: string[] }) {
  return (
    <div className="flex flex-col gap-2">
      <h4 className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Swatch side={side} />
        Where {name} is stronger
      </h4>
      {items.length ? (
        <ul className="flex list-disc flex-col gap-1.5 pl-4 text-sm">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">Nothing stands out.</p>
      )}
    </div>
  )
}

export function ComparisonReportPanel({
  aId,
  bId,
  nameA,
  nameB,
}: {
  aId: string
  bId: string
  nameA: string
  nameB: string
}) {
  const queryClient = useQueryClient()
  const config = useQuery(configQuery())
  const state = useQuery({
    ...comparisonQuery(aId, bId),
    enabled: config.data?.llm.enabled === true,
  })
  const start = useMutation({
    mutationFn: () => api.compare(aId, bId),
    onSuccess: (next) => queryClient.setQueryData(queryKeys.comparison(aId, bId), next),
    onError: (error) =>
      toast({
        title: 'Could not start the comparison',
        description: errorMessage(error),
        tone: 'error',
      }),
  })

  let body: React.ReactNode
  if (config.data && !config.data.llm.enabled) {
    body = (
      <p className="text-sm text-muted-foreground">
        No report model is configured, so there is no written comparison.
      </p>
    )
  } else if (!state.data) {
    body = state.isError ? (
      <p role="alert" className="text-sm text-destructive">
        {errorMessage(state.error)}
      </p>
    ) : (
      <Skeleton className="h-16 w-full" />
    )
  } else if (state.data.status === 'running' || start.isPending) {
    body = (
      <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" aria-hidden />
        Writing the comparison…
      </p>
    )
  } else if (state.data.status === 'completed' && state.data.comparison) {
    const { report, model } = state.data.comparison
    body = (
      <div className="flex flex-col gap-5">
        <h3 className="text-xl font-semibold tracking-tight text-balance">{report.headline}</h3>
        <div className="grid gap-6 sm:grid-cols-2">
          <Strengths side="a" name={nameA} items={report.a_strengths} />
          <Strengths side="b" name={nameB} items={report.b_strengths} />
        </div>
        <div className="flex flex-col gap-2 rounded-md bg-sunken p-4">
          <h4 className="text-xs font-medium text-muted-foreground">Recommendation</h4>
          <p className="text-sm">{report.recommendation}</p>
        </div>
        <p className="border-t pt-3 text-xs text-muted-foreground">
          Written by {model} from the metrics of both.
        </p>
      </div>
    )
  } else {
    body = (
      <div className="flex flex-col items-start gap-3">
        {state.data.status === 'failed' ? (
          <p role="alert" className="text-sm text-destructive">
            {state.data.error ?? 'Writing the comparison failed.'}
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">
            A language model can read both sets of metrics and say which ad works better, and why.
          </p>
        )}
        <Button onClick={() => start.mutate()}>
          <Sparkles aria-hidden />
          {state.data.status === 'failed' ? 'Try again' : 'Write the comparison'}
        </Button>
      </div>
    )
  }

  return (
    <section
      aria-labelledby="verdict-title"
      className="flex flex-col gap-4 rounded-lg border bg-card p-5"
    >
      <h2 id="verdict-title" className="text-sm font-medium">
        Written comparison
      </h2>
      {body}
    </section>
  )
}
