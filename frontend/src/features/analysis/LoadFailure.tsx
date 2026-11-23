import { Link } from '@tanstack/react-router'
import { CircleAlert, SearchX } from 'lucide-react'

import { errorMessage, isApiError } from '@/api/errors'
import { StateMessage } from '@/components/StateMessage'
import { Button } from '@/components/ui/button'

/** An analysis that could not be loaded: gone, or a request that failed. */
export function LoadFailure({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  if (isApiError(error, 'not_found')) {
    return (
      <StateMessage
        icon={SearchX}
        title="Analysis not found"
        actions={
          <Button asChild>
            <Link to="/history">Open History</Link>
          </Button>
        }
      >
        It may have been deleted, or the address is mistyped.
      </StateMessage>
    )
  }
  return (
    <StateMessage
      icon={CircleAlert}
      tone="error"
      title="The analysis could not load"
      actions={<Button onClick={onRetry}>Try again</Button>}
    >
      {errorMessage(error)}
    </StateMessage>
  )
}
