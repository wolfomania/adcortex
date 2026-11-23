// The analyzed clip: the video, or the audio with its loudness envelope.
import { useEffect, useMemo, useRef, useState } from 'react'

import { mediaUrls } from '@/api/endpoints'
import type { AnalysisResult, MediaKind, MediaSource } from '@/api/types'

import { usePlayback, type Playback } from './playback'

/** Keeps the playback store and a media element in step, both ways. */
function useMediaSync(element: HTMLMediaElement | null, playback: Playback): void {
  useEffect(() => {
    if (!element) {
      return
    }
    let frame = 0
    const tick = () => {
      playback.report(element.currentTime)
      frame = element.paused ? 0 : requestAnimationFrame(tick)
    }
    const start = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(tick)
    }
    const sync = () => playback.report(element.currentTime)
    element.addEventListener('play', start)
    element.addEventListener('seeked', sync)
    element.addEventListener('timeupdate', sync)
    const detach = playback.attach((seconds) => {
      if (Math.abs(element.currentTime - seconds) > 0.05) {
        element.currentTime = seconds
      }
    })
    return () => {
      cancelAnimationFrame(frame)
      element.removeEventListener('play', start)
      element.removeEventListener('seeked', sync)
      element.removeEventListener('timeupdate', sync)
      detach()
    }
  }, [element, playback])
}

function Envelope({ values, duration }: { values: number[]; duration: number }) {
  const playback = usePlayback()
  const head = useRef<SVGLineElement>(null)
  const path = useMemo(() => {
    const peak = Math.max(...values, 1e-6)
    const points = values.map((v, i) => `${i},${50 - (v / peak) * 46}`)
    const mirror = values.map((v, i) => `${i},${50 + (v / peak) * 46}`).reverse()
    return `M${points.join('L')}L${mirror.join('L')}Z`
  }, [values])

  useEffect(
    () =>
      playback.subscribe(() => {
        const x = String((playback.time / duration) * values.length)
        head.current?.setAttribute('x1', x)
        head.current?.setAttribute('x2', x)
      }),
    [playback, duration, values.length],
  )

  return (
    <svg
      viewBox={`0 0 ${values.length} 100`}
      preserveAspectRatio="none"
      className="h-28 w-full"
      aria-hidden
    >
      <path d={path} className="fill-viz-axis" />
      <line
        ref={head}
        x1={0}
        x2={0}
        y1={0}
        y2={100}
        className="stroke-viz-playhead"
        strokeWidth={2}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}

export function MediaPlayer({
  source,
  kind,
  result,
}: {
  source: MediaSource
  kind: MediaKind
  result: AnalysisResult
}) {
  const playback = usePlayback()
  const [element, setElement] = useState<HTMLMediaElement | null>(null)
  useMediaSync(element, playback)
  const url = mediaUrls.media(source)

  if (kind === 'video') {
    // Ads often open on black; the first scene's keyframe shows what's coming.
    const opening = result.scenes.find((scene) => scene.keyframe)
    return (
      <video
        ref={setElement}
        src={url}
        poster={opening ? mediaUrls.keyframe(source, opening.index) : undefined}
        controls
        playsInline
        preload="metadata"
        className="aspect-video w-full rounded-lg bg-black"
      />
    )
  }
  return (
    <div className="flex aspect-video w-full flex-col justify-center gap-4 rounded-lg bg-sunken p-4">
      {result.envelope?.length ? (
        <Envelope values={result.envelope} duration={result.duration_s} />
      ) : null}
      <audio ref={setElement} src={url} controls preload="metadata" className="w-full" />
    </div>
  )
}
