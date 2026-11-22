// Ten brain systems over time: a heatmap under the clip's filmstrip, with the
// peaks and dips, scene cuts, and the playhead. Click or use the arrow keys to seek.
import { useEffect, useRef, useState } from 'react'

import { mediaUrls } from '@/api/endpoints'
import type { AnalysisResult, MediaSource } from '@/api/types'
import { formatClock, formatZ } from '@/lib/format'
import { cn } from '@/lib/utils'

import { usePlayback, usePlaybackTime } from './playback'
import { heatFill, timeAtX, timeTicks } from './timeline'

/** Room for each time label on the axis. */
const TICK_SPACING_PX = 64

/** How many axis intervals fit the track's current width. */
function useTickBudget(track: React.RefObject<HTMLDivElement | null>): number {
  const [budget, setBudget] = useState(10)
  useEffect(() => {
    const element = track.current
    if (!element || typeof ResizeObserver === 'undefined') {
      return
    }
    const observer = new ResizeObserver(([entry]) => {
      if (entry) {
        setBudget(Math.max(2, Math.floor(entry.contentRect.width / TICK_SPACING_PX)))
      }
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [track])
  return budget
}

const ROW_PX = 22
const STRIP_PX = 44
const MAX_TILES = 60

function Filmstrip({ result, source }: { result: AnalysisResult; source: MediaSource }) {
  const columns = result.strip_columns ?? 10
  const tiles = Math.floor(result.duration_s) + 1
  const rows = Math.ceil(tiles / columns)
  const step = Math.ceil(tiles / MAX_TILES)
  const url = mediaUrls.strip(source)
  const shown = Array.from({ length: Math.ceil(tiles / step) }, (_, i) => i * step)
  return (
    <div className="flex overflow-hidden rounded-sm" style={{ height: STRIP_PX }} aria-hidden>
      {shown.map((k) => (
        <div
          key={k}
          className="flex-1 bg-no-repeat"
          style={{
            backgroundImage: `url("${url}")`,
            backgroundSize: `${columns * 100}% ${rows * 100}%`,
            backgroundPosition: `${((k % columns) / Math.max(columns - 1, 1)) * 100}% ${(Math.floor(k / columns) / Math.max(rows - 1, 1)) * 100}%`,
          }}
        />
      ))}
    </div>
  )
}

export function SystemTimeline({
  result,
  source,
  showStrip,
}: {
  result: AnalysisResult
  source: MediaSource
  showStrip: boolean
}) {
  const playback = usePlayback()
  const second = usePlaybackTime(1)
  const track = useRef<HTMLDivElement>(null)
  const tickBudget = useTickBudget(track)
  const playhead = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<{ t: number; row: number } | null>(null)
  const duration = result.duration_s
  const systems = result.systems
  const columns = result.times.length
  const top = showStrip ? STRIP_PX + 6 : 0
  const height = top + systems.length * ROW_PX

  useEffect(() => {
    const move = () => {
      if (playhead.current) {
        playhead.current.style.left = `${(playback.time / duration) * 100}%`
      }
    }
    move()
    return playback.subscribe(move)
  }, [playback, duration])

  const timeAt = (clientX: number) => {
    const rect = track.current?.getBoundingClientRect()
    return rect ? timeAtX(clientX, rect.left, rect.width, duration) : 0
  }
  const onKeyDown = (event: React.KeyboardEvent) => {
    const jumps: Record<string, number> = {
      ArrowLeft: playback.time - 1,
      ArrowRight: playback.time + 1,
      PageDown: playback.time - 5,
      PageUp: playback.time + 5,
      Home: 0,
      End: duration,
    }
    const target = jumps[event.key]
    if (target !== undefined) {
      event.preventDefault()
      playback.seek(target)
    }
  }
  const hovered = hover ? systems[hover.row] : undefined
  const hoveredZ =
    hover && hovered ? hovered.values[Math.min(Math.floor(hover.t), columns - 1)] : null

  return (
    <section aria-labelledby="timeline-title" className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="timeline-title" className="text-sm font-medium">
          Brain systems over time
        </h2>
        <p className="text-xs text-muted-foreground" aria-live="polite">
          {hover && hovered
            ? `${formatClock(hover.t)} · ${hovered.label}: ${hoveredZ === null || hoveredZ === undefined ? 'not applicable' : formatZ(hoveredZ)}`
            : 'z-scores against the reference library, one column per second'}
        </p>
      </div>
      <div className="grid grid-cols-[6.75rem_1fr] gap-x-3 sm:grid-cols-[9rem_1fr]">
        <div className="flex flex-col text-xs" style={{ paddingTop: top }}>
          {systems.map((system) => (
            <div
              key={system.id}
              className={cn(
                'flex items-center truncate',
                system.applicable === false &&
                  'text-muted-foreground line-through decoration-muted-foreground/40',
              )}
              style={{ height: ROW_PX }}
              title={
                system.applicable === false ? `${system.label}: needs a picture` : system.label
              }
            >
              {system.label}
            </div>
          ))}
        </div>
        <div>
          <div
            ref={track}
            role="slider"
            tabIndex={0}
            aria-label="Playhead"
            aria-valuemin={0}
            aria-valuemax={Math.round(duration)}
            aria-valuenow={second}
            aria-valuetext={formatClock(second)}
            className="relative cursor-crosshair touch-none rounded-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
            style={{ height }}
            onPointerDown={(event) => playback.seek(timeAt(event.clientX))}
            onPointerMove={(event) => {
              const rect = track.current?.getBoundingClientRect()
              const y = rect ? event.clientY - rect.top - top : -1
              const row = Math.floor(y / ROW_PX)
              setHover(row >= 0 && row < systems.length ? { t: timeAt(event.clientX), row } : null)
              if (event.buttons === 1) {
                playback.seek(timeAt(event.clientX))
              }
            }}
            onPointerLeave={() => setHover(null)}
            onKeyDown={onKeyDown}
          >
            {showStrip ? <Filmstrip result={result} source={source} /> : null}
            <svg
              viewBox={`0 0 ${columns} ${systems.length}`}
              preserveAspectRatio="none"
              className="absolute inset-x-0 w-full"
              style={{ top, height: systems.length * ROW_PX }}
              aria-hidden
            >
              {systems.map((system, row) =>
                system.values.map((z, k) => (
                  <rect
                    key={`${system.id}-${k}`}
                    x={k}
                    y={row + 0.06}
                    width={1.02}
                    height={0.88}
                    style={{ fill: heatFill(z) }}
                  />
                )),
              )}
            </svg>
            {result.scenes.slice(1).map((scene) => (
              <div
                key={scene.index}
                className="pointer-events-none absolute inset-y-0 w-px bg-viz-ink/30"
                style={{ left: `${(scene.start / duration) * 100}%` }}
                aria-hidden
              />
            ))}
            {result.moments.map((moment) => {
              const row = systems.findIndex((s) => s.id === moment.system_id)
              return row < 0 ? null : (
                <span
                  key={`${moment.system_id}-${moment.t}-${moment.kind}`}
                  title={`${moment.kind === 'peak' ? 'Peak' : 'Dip'} · ${moment.label} · ${formatClock(moment.t)}`}
                  className={cn(
                    'pointer-events-none absolute size-2 -translate-1/2 rounded-full border-2 border-viz-ink',
                    moment.kind === 'peak' ? 'bg-viz-ink' : 'bg-transparent',
                  )}
                  style={{
                    left: `${((moment.t + 0.5) / duration) * 100}%`,
                    top: top + row * ROW_PX + ROW_PX / 2,
                  }}
                />
              )
            })}
            <div
              ref={playhead}
              className="pointer-events-none absolute inset-y-0 w-0.5 -translate-x-1/2 bg-viz-playhead"
              aria-hidden
            />
          </div>
          <div className="relative mt-1 h-4 text-[0.68rem] text-muted-foreground" aria-hidden>
            {timeTicks(duration, tickBudget).map((t) => (
              <span
                key={t}
                className="absolute -translate-x-1/2 font-mono first:translate-x-0 last:-translate-x-full"
                style={{ left: `${(t / duration) * 100}%` }}
              >
                {formatClock(t)}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
