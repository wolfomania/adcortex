// The brain view with its controls, color legend, and the region under the pointer.
import { useQuery } from '@tanstack/react-query'
import { lazy, Suspense, useMemo, useState } from 'react'

import { framesQuery } from '@/api/queries'
import type { AnalysisResult, MediaSource } from '@/api/types'
import { Skeleton } from '@/components/ui/skeleton'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { usePlayback, usePlaybackTime } from '@/features/results/playback'
import { SYSTEM_CATALOG } from '@/features/systems/catalog'
import { formatZ } from '@/lib/format'

import { loadBrainAssets, type BrainAssets, type Surface } from './assets'
import type { BrainViewName } from './BrainView'
import { byteToZ, framePosition, type FrameSet } from './paint'
import { supportsWebGL } from './webgl'

const BrainView = lazy(() => import('./BrainView'))

const SURFACES: { value: Surface; label: string }[] = [
  { value: 'inflated', label: 'Inflated' },
  { value: 'pial', label: 'Folded' },
]
const VIEWS: { value: BrainViewName; label: string }[] = [
  { value: 'left', label: 'Left' },
  { value: 'right', label: 'Right' },
  { value: 'top', label: 'Top' },
  { value: 'back', label: 'Back' },
]

const SYSTEM_OF_PARCEL = new Map(
  SYSTEM_CATALOG.flatMap((system) =>
    system.parcels.map((parcel) => [parcel, system.label] as const),
  ),
)

/** The canvas shape: 4:3 in one column, 16:9 beside the video. */
const FRAME_SHAPE = 'aspect-[4/3] w-full lg:aspect-video'

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div
      className={`flex ${FRAME_SHAPE} items-center justify-center rounded-lg bg-sunken p-6 text-center text-sm text-muted-foreground`}
    >
      {children}
    </div>
  )
}

function HoverReadout({
  vertex,
  assets,
  frames,
  range,
}: {
  vertex: number | null
  assets: BrainAssets
  frames: FrameSet
  range: { vmin: number; vmax: number }
}) {
  const time = usePlaybackTime(0.5)
  if (vertex === null) {
    return <span>Point at the cortex to name a region.</span>
  }
  const parcel = assets.atlas.parcels[assets.mesh.parcel[vertex] ?? 0]
  if (!parcel || parcel.id === 0) {
    return <span>Medial wall: no cortex here.</span>
  }
  const { k } = framePosition(time, frames.nFrames)
  const z = byteToZ(frames.bytes[k * frames.nVertices + vertex] ?? 128, range)
  const system = SYSTEM_OF_PARCEL.get(parcel.name)
  const side = vertex < frames.nVertices / 2 ? 'left' : 'right'
  return (
    <span>
      <span className="font-medium text-foreground">{parcel.name}</span> · {parcel.longName} ({side}
      ){system ? ` · ${system}` : ''} · <span className="font-mono">{formatZ(z)}</span>
    </span>
  )
}

export function BrainPanel({ result, source }: { result: AnalysisResult; source: MediaSource }) {
  const playback = usePlayback()
  const [surface, setSurface] = useState<Surface>('inflated')
  const [view, setView] = useState<BrainViewName>('left')
  const [vertex, setVertex] = useState<number | null>(null)
  const webgl = useMemo(() => supportsWebGL(), [])
  const assets = useQuery({
    queryKey: ['brain-assets'],
    queryFn: loadBrainAssets,
    staleTime: Number.POSITIVE_INFINITY,
    enabled: webgl,
  })
  const framesInfo = result.frames
  const frames = useQuery({ ...framesQuery(source), enabled: webgl && Boolean(framesInfo) })
  const frameSet = useMemo<FrameSet | null>(() => {
    if (!frames.data || !framesInfo) {
      return null
    }
    const bytes = new Uint8Array(frames.data)
    return bytes.length === framesInfo.n_frames * framesInfo.n_vertices
      ? { bytes, nFrames: framesInfo.n_frames, nVertices: framesInfo.n_vertices }
      : null
  }, [frames.data, framesInfo])
  const range = useMemo(
    () => ({ vmin: framesInfo?.vmin ?? -3, vmax: framesInfo?.vmax ?? 3 }),
    [framesInfo],
  )

  let body: React.ReactNode
  if (!webgl) {
    body = <Frame>The 3D brain needs WebGL, which this browser has turned off.</Frame>
  } else if (!framesInfo) {
    body = <Frame>This analysis has no brain maps.</Frame>
  } else if (assets.isError || frames.isError || (frames.data && !frameSet)) {
    body = <Frame>The brain maps could not load. Reload the page to try again.</Frame>
  } else if (!assets.data || !frameSet) {
    body = <Skeleton className={`${FRAME_SHAPE} rounded-lg`} />
  } else {
    body = (
      <div className={`${FRAME_SHAPE} overflow-hidden rounded-lg bg-sunken`}>
        <Suspense fallback={<Skeleton className="size-full" />}>
          <BrainView
            assets={assets.data}
            frames={frameSet}
            range={range}
            surface={surface}
            view={view}
            playback={playback}
            onHover={setVertex}
          />
        </Suspense>
      </div>
    )
  }

  return (
    <section aria-labelledby="brain-title" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="brain-title" className="text-sm font-medium">
          Predicted cortical response
        </h2>
        <div className="flex flex-wrap gap-2 print:hidden">
          <ToggleGroup
            type="single"
            size="sm"
            variant="outline"
            value={surface}
            onValueChange={(value: string) => value && setSurface(value as Surface)}
            aria-label="Surface"
          >
            {SURFACES.map((item) => (
              <ToggleGroupItem key={item.value} value={item.value}>
                {item.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <ToggleGroup
            type="single"
            size="sm"
            variant="outline"
            value={view}
            onValueChange={(value: string) => value && setView(value as BrainViewName)}
            aria-label="View"
          >
            {VIEWS.map((item) => (
              <ToggleGroupItem key={item.value} value={item.value}>
                {item.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
      </div>
      {body}
      <div className="flex flex-col gap-2 text-xs text-muted-foreground">
        <div className="flex items-center gap-2" aria-hidden>
          <span>Below</span>
          <span className="h-2 flex-1 rounded-full bg-gradient-to-r from-viz-neg via-viz-mid to-viz-pos" />
          {/* Without a reference library, the backend compares each vertex with the clip itself. */}
          <span>
            {result.baseline ? 'Above the reference average' : "Above this clip's average"}
          </span>
        </div>
        {assets.data && frameSet ? (
          <p className="min-h-4" aria-live="polite">
            <HoverReadout vertex={vertex} assets={assets.data} frames={frameSet} range={range} />
          </p>
        ) : null}
      </div>
    </section>
  )
}
