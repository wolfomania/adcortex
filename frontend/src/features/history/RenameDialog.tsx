import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useId, useState } from 'react'

import { api } from '@/api/endpoints'
import { errorMessage } from '@/api/errors'
import type { Analysis } from '@/api/types'
import { toast } from '@/components/toast-store'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const MAX_NAME = 120

export function RenameDialog({
  analysis,
  open,
  onOpenChange,
}: {
  analysis: Analysis
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const inputId = useId()
  const [name, setName] = useState(analysis.meta.name)
  const trimmed = name.trim()
  const rename = useMutation({
    mutationFn: () => api.rename(analysis.meta.id, trimmed),
    onSuccess: async () => {
      onOpenChange(false)
      toast({ title: 'Renamed', tone: 'success' })
      await queryClient.invalidateQueries({ queryKey: ['analyses'] })
    },
  })

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (next) {
          setName(analysis.meta.name)
          rename.reset()
        }
        onOpenChange(next)
      }}
    >
      <DialogContent>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (trimmed && !rename.isPending) {
              rename.mutate()
            }
          }}
        >
          <DialogHeader>
            <DialogTitle>Rename the analysis</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor={inputId}>Name</Label>
            <Input
              id={inputId}
              value={name}
              maxLength={MAX_NAME}
              onChange={(event) => setName(event.target.value)}
              autoFocus
            />
            {rename.isError ? (
              <p role="alert" className="text-sm text-destructive">
                {errorMessage(rename.error)}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={!trimmed || rename.isPending}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
