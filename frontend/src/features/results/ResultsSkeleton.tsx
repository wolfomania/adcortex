import { Skeleton } from '@/components/ui/skeleton'

/** The results page's outline while its data loads. */
export function ResultsSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-4 py-8 sm:px-6" aria-busy>
      <span className="sr-only" role="status">
        Loading the analysis
      </span>
      <Skeleton className="h-12 w-80 max-w-full" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
      <div className="grid gap-8 lg:grid-cols-2">
        <Skeleton className="aspect-video" />
        <Skeleton className="aspect-[4/3]" />
      </div>
    </div>
  )
}
