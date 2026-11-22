// One analysis: its progress while it runs, then its results.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { CircleAlert, GitCompareArrows, RotateCcw, SearchX } from 'lucide-react'
import { useEffect, useRef } from 'react'

import { api } from '@/api/endpoints'
import { errorMessage } from '@/api/errors'
import { analysisQuery, queryKeys, statusQuery } from '@/api/queries'
import type { Analysis, AnalysisDetail, Status } from '@/api/types'
import { StateMessage } from '@/components/StateMessage'
import { toast } from '@/components/toast-store'
import { Button } from '@/components/ui/button'
import { LoadFailure } from '@/features/analysis/LoadFailure'
import { ProcessingView } from '@/features/analysis/ProcessingView'
import { ResultsSkeleton } from '@/features/results/ResultsSkeleton'
import { ResultsView } from '@/features/results/ResultsView'
import { ShareDialog } from '@/features/results/ShareDialog'
import { useDocumentTitle } from '@/lib/useDocumentTitle'

export const Route = createFileRoute('/a/$id')({
  loader: ({ context, params }) => context.queryClient.prefetchQuery(statusQuery(params.id)),
  component: AnalysisPage,
})

function AnalysisPage() {
  const { id } = Route.useParams()
  const status = useQuery(statusQuery(id))
  useDocumentTitle(status.data?.meta.name)

  if (status.isPending) {
    return <ResultsSkeleton />
  }
  if (status.isError) {
    return <LoadFailure error={status.error} onRetry={() => void status.refetch()} />
  }
  const stage = status.data.state.status
  if (stage === 'failed') {
    return <FailedView analysis={status.data} />
  }
  if (stage === 'interpreting' || stage === 'completed') {
    return <AnalysisResults id={id} stage={stage} />
  }
  return <ProcessingView analysis={status.data} />
}

function FailedView({ analysis }: { analysis: Analysis }) {
  const queryClient = useQueryClient()
  const retry = useMutation({
    mutationFn: () => api.retry(analysis.meta.id),
    onSuccess: (next) => queryClient.setQueryData(queryKeys.status(next.meta.id), next),
    onError: (error) =>
      toast({ title: 'Could not start again', description: errorMessage(error), tone: 'error' }),
  })
  return (
    <StateMessage
      icon={CircleAlert}
      tone="error"
      title="This analysis failed"
      actions={
        <>
          <Button onClick={() => retry.mutate()} disabled={retry.isPending}>
            <RotateCcw aria-hidden />
            Try again
          </Button>
          <Button variant="outline" asChild>
            <Link to="/">New analysis</Link>
          </Button>
        </>
      }
    >
      {analysis.state.error ?? 'Something went wrong during the analysis.'}
    </StateMessage>
  )
}

/** Fetches the report once the status poll sees it finished. */
function useRefreshWhenCompleted(id: string, stage: Status): void {
  const queryClient = useQueryClient()
  const previous = useRef(stage)
  useEffect(() => {
    if (previous.current !== stage && stage === 'completed') {
      void queryClient.invalidateQueries({ queryKey: queryKeys.analysis(id) })
    }
    previous.current = stage
  }, [id, stage, queryClient])
}

function AnalysisResults({ id, stage }: { id: string; stage: Status }) {
  const queryClient = useQueryClient()
  const detail = useQuery(analysisQuery(id))
  useRefreshWhenCompleted(id, stage)
  const rewrite = useMutation({
    mutationFn: () => api.regenerateReport(id),
    onSuccess: (next) => {
      queryClient.setQueryData(queryKeys.status(id), next)
      queryClient.setQueryData(queryKeys.analysis(id), (old: AnalysisDetail | undefined) =>
        old ? { ...old, analysis: next } : old,
      )
    },
    onError: (error) =>
      toast({
        title: 'Could not rewrite the report',
        description: errorMessage(error),
        tone: 'error',
      }),
  })

  if (detail.isPending) {
    return <ResultsSkeleton />
  }
  if (detail.isError) {
    return <LoadFailure error={detail.error} onRetry={() => void detail.refetch()} />
  }
  const { analysis, result, report } = detail.data
  if (!result) {
    return (
      <StateMessage icon={SearchX} title="The results are missing">
        The analysis finished, but its results are no longer in storage. Upload the file again to
        rerun it.
      </StateMessage>
    )
  }
  const isCompleted = analysis.state.status === 'completed'
  return (
    <ResultsView
      analysis={analysis}
      result={result}
      report={report}
      source={{ kind: 'analysis', id }}
      onRewrite={() => rewrite.mutate()}
      rewriting={rewrite.isPending}
      actions={
        isCompleted ? (
          <>
            <Button variant="outline" size="sm" asChild>
              <Link to="/compare" search={{ a: id }}>
                <GitCompareArrows aria-hidden />
                Compare
              </Link>
            </Button>
            <ShareDialog id={id} />
          </>
        ) : null
      }
    />
  )
}
