// Creating a read-only link to a completed analysis.
import { useMutation } from '@tanstack/react-query'
import { Copy, Link2 } from 'lucide-react'
import { useId, useState } from 'react'

import { api } from '@/api/endpoints'
import { errorMessage } from '@/api/errors'
import { toast } from '@/components/toast-store'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDateTime } from '@/lib/format'

export function ShareDialog({ id }: { id: string }) {
  const [open, setOpen] = useState(false)
  const inputId = useId()
  const share = useMutation({ mutationFn: () => api.share(id) })
  const url = share.data ? new URL(share.data.path, window.location.origin).toString() : null

  const copy = async () => {
    if (!url) {
      return
    }
    try {
      await navigator.clipboard.writeText(url)
      toast({ title: 'Link copied', tone: 'success' })
    } catch {
      toast({ title: 'Copying failed', description: 'Select the link and copy it.', tone: 'error' })
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (next && !share.data && !share.isPending) {
          share.mutate()
        }
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Link2 aria-hidden />
          Share
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Share a read-only link</DialogTitle>
          <DialogDescription>
            {share.data
              ? `Anyone with the link can view this analysis until ${formatDateTime(share.data.expires_at)}. They cannot change or delete it.`
              : 'Anyone with the link can view this analysis. They cannot change or delete it.'}
          </DialogDescription>
        </DialogHeader>
        {share.isError ? (
          <div className="flex flex-col items-start gap-3">
            <p role="alert" className="text-sm text-destructive">
              {errorMessage(share.error)}
            </p>
            <Button variant="outline" size="sm" onClick={() => share.mutate()}>
              Try again
            </Button>
          </div>
        ) : url ? (
          <div className="flex gap-2">
            <label htmlFor={inputId} className="sr-only">
              Share link
            </label>
            <Input
              id={inputId}
              readOnly
              value={url}
              onFocus={(event) => event.currentTarget.select()}
            />
            <Button onClick={() => void copy()}>
              <Copy aria-hidden />
              Copy
            </Button>
          </div>
        ) : (
          <Skeleton className="h-9 w-full" />
        )}
      </DialogContent>
    </Dialog>
  )
}
