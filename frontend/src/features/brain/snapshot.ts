// Pictures of the 3D brain for the exported report. The brain view registers
// its canvas here; the export seeks the playback and copies what it draws.
import type { Playback } from '@/features/results/playback'

/** Width of the exported pictures, in pixels. */
const PICTURE_WIDTH = 720

let current: HTMLCanvasElement | null = null

/** Called by the brain view with its canvas, and with null when it unmounts. */
export function setBrainCanvas(canvas: HTMLCanvasElement | null): void {
  current = canvas
}

/** Resolves once the browser has painted twice: the canvas renders on demand. */
function nextPaint(): Promise<void> {
  return new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
  })
}

/** A PNG of the canvas, scaled down to `PICTURE_WIDTH`; transparent where the canvas is. */
function takePicture(canvas: HTMLCanvasElement): string {
  const scale = Math.min(1, PICTURE_WIDTH / canvas.width)
  const copy = document.createElement('canvas')
  copy.width = Math.round(canvas.width * scale)
  copy.height = Math.round(canvas.height * scale)
  copy.getContext('2d')?.drawImage(canvas, 0, 0, copy.width, copy.height)
  return copy.toDataURL('image/png')
}

/**
 * Pictures of the cortex at each time, in seconds, as data URLs. Empty when
 * the brain is not on screen (no WebGL, or still loading). The playhead
 * returns to where it was.
 */
export async function captureBrain(
  playback: Playback,
  times: readonly number[],
  take: (canvas: HTMLCanvasElement) => string = takePicture,
): Promise<string[]> {
  const canvas = current
  if (!canvas?.isConnected || times.length === 0) {
    return []
  }
  const start = playback.time
  const pictures: string[] = []
  try {
    for (const time of times) {
      playback.seek(time)
      await nextPaint()
      pictures.push(take(canvas))
    }
  } finally {
    playback.seek(start)
  }
  return pictures
}
