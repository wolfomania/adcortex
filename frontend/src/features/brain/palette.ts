// Brain colors from the theme, converted to the linear RGB three.js renders in.
import { Color, SRGBColorSpace } from 'three'

import type { BrainPalette, Rgb } from './paint'

const FALLBACK = {
  positive: '#e2643f',
  negative: '#5a8ee0',
  gyrus: '#a7abb2',
  sulcus: '#5e636b',
  medialWall: '#3c3f45',
}

/** Any CSS color (oklch included) as sRGB, by drawing one pixel; null without a 2D canvas. */
function cssToSrgb(css: string): Rgb | null {
  const canvas = document.createElement('canvas')
  canvas.width = 1
  canvas.height = 1
  const context = canvas.getContext('2d', { willReadFrequently: true })
  if (!context) {
    return null
  }
  context.fillStyle = css
  context.fillRect(0, 0, 1, 1)
  const [r = 0, g = 0, b = 0] = context.getImageData(0, 0, 1, 1).data
  return [r / 255, g / 255, b / 255]
}

function linear(color: Color): Rgb {
  return [color.r, color.g, color.b]
}

function themed(style: CSSStyleDeclaration, variable: string, fallback: string): Rgb {
  const css = style.getPropertyValue(variable).trim()
  const srgb = css ? cssToSrgb(css) : null
  return linear(srgb ? new Color().setRGB(...srgb, SRGBColorSpace) : new Color(fallback))
}

/** Response colors follow the theme's diverging pair; anatomy stays neutral gray. */
export function readPalette(element: Element = document.documentElement): BrainPalette {
  const style = getComputedStyle(element)
  return {
    positive: themed(style, '--viz-pos', FALLBACK.positive),
    negative: themed(style, '--viz-neg', FALLBACK.negative),
    gyrus: linear(new Color(FALLBACK.gyrus)),
    sulcus: linear(new Color(FALLBACK.sulcus)),
    medialWall: linear(new Color(FALLBACK.medialWall)),
  }
}
