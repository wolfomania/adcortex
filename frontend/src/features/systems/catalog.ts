// The ten brain systems the analysis reports on, with what they mean and
// where the definition comes from (generated from the backend's systems.yaml).
import data from './catalog.json'

export type Confidence = 'high' | 'medium' | 'low'

export interface Citation {
  key: string
  text: string
}

export interface SystemInfo {
  id: string
  label: string
  /** How directly the literature ties the parcels to the function. */
  confidence: Confidence
  /** Needs a picture: not applicable to audio or scripts. */
  visual: boolean
  /** HCP-MMP1.0 parcel names (both hemispheres). */
  parcels: string[]
  description: string
  citations: Citation[]
}

export const SYSTEM_CATALOG: readonly SystemInfo[] = data.systems as SystemInfo[]

const BY_ID = new Map(SYSTEM_CATALOG.map((system) => [system.id, system]))

export function systemInfo(id: string): SystemInfo | undefined {
  return BY_ID.get(id)
}

export const CONFIDENCE_LABELS: Record<Confidence, string> = {
  high: 'High confidence',
  medium: 'Medium confidence',
  low: 'Low confidence',
}

export const CONFIDENCE_HINTS: Record<Confidence, string> = {
  high: 'Decades of converging evidence tie these areas to this function.',
  medium: 'Well supported, but the areas also take part in other functions.',
  low: 'The areas serve several functions; read this system as a hint, not a measurement.',
}
