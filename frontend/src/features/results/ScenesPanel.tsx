// The scenes of a video: a keyframe each, and the systems that respond most.
import { mediaUrls } from '@/api/endpoints'
import type { AnalysisResult, MediaSource } from '@/api/types'
import { formatClock, formatZ } from '@/lib/format'

import { usePlayback } from './playback'

const TOP_SYSTEMS = 2

export function ScenesPanel({ result, source }: { result: AnalysisResult; source: MediaSource }) {
  const playback = usePlayback()
  const labels = new Map(result.systems.map((system) => [system.id, system.label]))
  return (
    <section aria-labelledby="scenes-title" className="flex flex-col gap-2">
      <h2 id="scenes-title" className="text-sm font-medium">
        Scenes
      </h2>
      <ol className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {result.scenes.map((scene) => {
          const stats = result.scene_stats.find((stat) => stat.scene_index === scene.index)
          const top = Object.entries(stats?.mean_z ?? {})
            .filter((entry): entry is [string, number] => typeof entry[1] === 'number')
            .sort((a, b) => b[1] - a[1])
            .slice(0, TOP_SYSTEMS)
          return (
            <li key={scene.index}>
              <button
                type="button"
                onClick={() => playback.seek(scene.start)}
                className="flex w-full flex-col gap-1.5 rounded-lg text-left focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
              >
                {scene.keyframe ? (
                  <img
                    src={mediaUrls.keyframe(source, scene.index)}
                    alt={`Scene ${scene.index + 1}`}
                    loading="lazy"
                    className="aspect-video w-full rounded-md bg-sunken object-cover"
                  />
                ) : null}
                <span className="font-mono text-xs text-muted-foreground tabular-nums">
                  {formatClock(scene.start)}–{formatClock(scene.end)}
                </span>
                <span className="text-xs">
                  {top.map(([id, z]) => `${labels.get(id) ?? id} ${formatZ(z)}`).join(' · ') || '–'}
                </span>
              </button>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
