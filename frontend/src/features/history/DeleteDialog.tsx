import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/endpoints'
import { errorMessage } from '@/api/errors'
import { queryKeys } from '@/api/queries'
import type { Analysis } from '@/api/types'
import { toast } from '@/components/toast-store'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

export function DeleteDialog({
  analysis,
  open,
  onOpenChange,
  onDeleted,
}: {
  analysis: Analysis
  open: boolean
  onOpenChange: (open: boolean) => void
  onDeleted: (id: string) => void
}) {
  const queryClient = useQueryClient()
  const { id, name } = analysis.meta
  const remove = useMutation({
    mutationFn: () => api.remove(id),
    onSuccess: async () => {
      onDeleted(id)
      toast({ title: `Deleted “${name}”`, tone: 'success' })
      queryClient.removeQueries({ queryKey: queryKeys.analysis(id) })
      queryClient.removeQueries({ queryKey: queryKeys.status(id) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.history })
    },
    onError: (error) =>
      toast({ title: 'Could not delete', description: errorMessage(error), tone: 'error' }),
  })

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete “{name}”?</AlertDialogTitle>
          <AlertDialogDescription>
            The upload, the brain maps, the report, and any share links are deleted for good.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={remove.isPending}
            onClick={() => remove.mutate()}
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
