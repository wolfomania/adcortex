// The playhead shared by the player, the brain view, the timeline, and the transcript.
//
// The media element reports its time many times a second; components subscribe
// and redraw themselves without re-rendering the whole results page.
import { createContext, useContext, useSyncExternalStore } from 'react'

type Listener = () => void
type Seeker = (seconds: number) => void

export class Playback {
  readonly duration: number
  private current = 0
  private seeker: Seeker | null = null
  private readonly listeners = new Set<Listener>()

  constructor(duration: number) {
    this.duration = duration
  }

  get time(): number {
    return this.current
  }

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }

  /** The media element reports where it is. */
  report(seconds: number): void {
    const next = Math.min(Math.max(seconds, 0), this.duration)
    if (next === this.current) {
      return
    }
    this.current = next
    for (const listener of this.listeners) {
      listener()
    }
  }

  /** Jump to `seconds`: the media element follows when there is one. */
  seek(seconds: number): void {
    this.report(seconds)
    this.seeker?.(this.current)
  }

  /** The media element registers how to move itself; returns the detach function. */
  attach(seeker: Seeker): () => void {
    this.seeker = seeker
    return () => {
      if (this.seeker === seeker) {
        this.seeker = null
      }
    }
  }
}

export const PlaybackContext = createContext<Playback | null>(null)

export function usePlayback(): Playback {
  const playback = useContext(PlaybackContext)
  if (!playback) {
    throw new Error('usePlayback needs a PlaybackContext provider')
  }
  return playback
}

/** The playhead, rounded down to `step` seconds, so callers re-render only that often. */
export function usePlaybackTime(step = 0.25): number {
  const playback = usePlayback()
  return useSyncExternalStore(playback.subscribe, () => Math.floor(playback.time / step) * step)
}
