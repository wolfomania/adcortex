// A shared, read-only analysis. Works without a session.
import { useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import { CircleAlert, Link2Off } from 'lucide-react'

import { errorMessage, isApiError } from '@/api/errors'
import { sharedQuery } from '@/api/queries'
import { StateMessage } from '@/components/StateMessage'
import { Button } from '@/components/ui/button'
import { ResultsSkeleton } from '@/features/results/ResultsSkeleton'
import { ResultsView } from '@/features/results/ResultsView'
import { useDocumentTitle } from '@/lib/useDocumentTitle'

export const Route = createFileRoute('/s/$token')({
  loader: ({ context, params }) => context.queryClient.prefetchQuery(sharedQuery(params.token)),
  component: SharedPage,
})

function SharedPage() {
  const { token } = Route.useParams()
  const shared = useQuery(sharedQuery(token))
  useDocumentTitle(shared.data?.analysis.meta.name)

  if (shared.isPending) {
    return <ResultsSkeleton />
  }
  if (shared.isError) {
    return isApiError(shared.error, 'network') || isApiError(shared.error, 'internal') ? (
      <StateMessage
        icon={CircleAlert}
        tone="error"
        title="The analysis could not load"
        actions={<Button onClick={() => void shared.refetch()}>Try again</Button>}
      >
        {errorMessage(shared.error)}
      </StateMessage>
    ) : (
      <StateMessage icon={Link2Off} title="This link no longer works">
        It may have expired, been mistyped, or the analysis was deleted. Ask the person who sent it
        for a new link.
      </StateMessage>
    )
  }
  const { analysis, result, report } = shared.data
  if (!result) {
    return (
      <StateMessage icon={Link2Off} title="The results are missing">
        The shared analysis has no results in storage.
      </StateMessage>
    )
  }
  return (
    <ResultsView
      analysis={analysis}
      result={result}
      report={report}
      source={{ kind: 'shared', token }}
    />
  )
}
