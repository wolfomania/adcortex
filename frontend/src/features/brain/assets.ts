// The cortical surface and atlas served from /brain (see public/brain).
//
// mesh.bin holds the fsaverage5 surface quantized to 16-bit integers;
// mesh.json says where each buffer starts and how to dequantize it.
// atlas.json names the 180 HCP-MMP1.0 parcels per hemisphere.

export const HEMISPHERE_VERTICES = 10242
export const N_VERTICES = HEMISPHERE_VERTICES * 2

export type Hemisphere = 'left' | 'right'
export type Surface = 'pial' | 'inflated'

export const HEMISPHERES: readonly Hemisphere[] = ['left', 'right']
export const SURFACES: readonly Surface[] = ['pial', 'inflated']

type Vec3 = [number, number, number]

interface BufferSpec {
  offset: number
  length: number
  dtype: 'u1' | 'u2'
  min?: Vec3
  max?: Vec3
}

export interface MeshDescription {
  format: number
  hemisphere_vertices: number
  buffers: Record<string, BufferSpec>
  bytes: number
}

export interface BrainMesh {
  /** Vertex positions in millimetres (RAS), xyz interleaved, per hemisphere. */
  positions: Record<Surface, Record<Hemisphere, Float32Array>>
  /** Triangle vertex indices, local to each hemisphere. */
  faces: Record<Hemisphere, Uint16Array>
  /** Sulcal depth per vertex, 0 (gyrus crown) to 255 (sulcus fundus). */
  sulc: Uint8Array
  /** Atlas parcel id per vertex (0 = medial wall). */
  parcel: Uint8Array
}

export interface AtlasParcel {
  id: number
  name: string
  longName: string
  section: string
}

export interface BrainAtlas {
  source: string
  license: string
  acknowledgment: string
  /** Parcels indexed by id. */
  parcels: AtlasParcel[]
}

export interface BrainAssets {
  mesh: BrainMesh
  atlas: BrainAtlas
}

function spec(description: MeshDescription, name: string): BufferSpec {
  const found = description.buffers[name]
  if (!found) {
    throw new Error(`mesh.json has no buffer "${name}"`)
  }
  return found
}

function checkBounds(buffer: ArrayBuffer, item: BufferSpec, name: string): void {
  if (item.offset < 0 || item.offset + item.length > buffer.byteLength) {
    throw new Error(`mesh.bin is too short for buffer "${name}"`)
  }
}

function readPositions(view: DataView, item: BufferSpec, name: string): Float32Array {
  const { min, max } = item
  if (!min || !max || item.dtype !== 'u2') {
    throw new Error(`Buffer "${name}" is not a quantized position buffer`)
  }
  const count = item.length / 2
  const out = new Float32Array(count)
  for (let i = 0; i < count; i += 1) {
    const axis = i % 3
    const q = view.getUint16(item.offset + i * 2, true)
    out[i] = min[axis]! + (q / 65535) * (max[axis]! - min[axis]!)
  }
  return out
}

function readU16(view: DataView, item: BufferSpec): Uint16Array {
  const count = item.length / 2
  const out = new Uint16Array(count)
  for (let i = 0; i < count; i += 1) {
    out[i] = view.getUint16(item.offset + i * 2, true)
  }
  return out
}

/** Decode mesh.bin with the layout from mesh.json. */
export function parseMesh(description: MeshDescription, buffer: ArrayBuffer): BrainMesh {
  if (description.format !== 1) {
    throw new Error(`Unsupported mesh format ${description.format}`)
  }
  if (description.hemisphere_vertices !== HEMISPHERE_VERTICES) {
    throw new Error('The mesh is not fsaverage5')
  }
  for (const [name, item] of Object.entries(description.buffers)) {
    checkBounds(buffer, item, name)
  }
  const view = new DataView(buffer)
  const position = (surface: Surface, hemisphere: Hemisphere) => {
    const name = `${surface}.${hemisphere}.position`
    return readPositions(view, spec(description, name), name)
  }
  const bytes = (name: string) => {
    const item = spec(description, name)
    return new Uint8Array(buffer.slice(item.offset, item.offset + item.length))
  }
  return {
    positions: {
      pial: { left: position('pial', 'left'), right: position('pial', 'right') },
      inflated: { left: position('inflated', 'left'), right: position('inflated', 'right') },
    },
    faces: {
      left: readU16(view, spec(description, 'faces.left')),
      right: readU16(view, spec(description, 'faces.right')),
    },
    sulc: bytes('sulc'),
    parcel: bytes('parcel'),
  }
}

interface RawParcel {
  id: number
  name: string
  long_name: string
  section: string
}

function isRawParcel(value: unknown): value is RawParcel {
  if (typeof value !== 'object' || value === null) {
    return false
  }
  const item = value as Record<string, unknown>
  return typeof item.id === 'number' && typeof item.name === 'string'
}

/** Read atlas.json: parcel names and the data source to credit. */
export function parseAtlas(json: unknown): BrainAtlas {
  if (
    typeof json !== 'object' ||
    json === null ||
    !Array.isArray((json as { parcels?: unknown }).parcels)
  ) {
    throw new Error('atlas.json has no parcel list')
  }
  const raw = json as Record<string, unknown> & { parcels: unknown[] }
  const parcels: AtlasParcel[] = []
  for (const item of raw.parcels) {
    if (!isRawParcel(item)) {
      throw new Error('atlas.json has a malformed parcel')
    }
    parcels[item.id] = {
      id: item.id,
      name: item.name,
      longName: typeof item.long_name === 'string' ? item.long_name : item.name,
      section: typeof item.section === 'string' ? item.section : '',
    }
  }
  return {
    source: String(raw.source ?? ''),
    license: String(raw.license ?? ''),
    acknowledgment: String(raw.acknowledgment ?? ''),
    parcels,
  }
}

/** URL of a file under public/brain, valid outside the page too. */
export function brainAssetUrl(file: string): string {
  return new URL(`${import.meta.env.BASE_URL}brain/${file}`, window.location.origin).toString()
}

async function fetchOk(file: string): Promise<Response> {
  const response = await fetch(brainAssetUrl(file))
  if (!response.ok) {
    throw new Error(`Could not load the brain model (${file}: HTTP ${response.status})`)
  }
  return response
}

let pending: Promise<BrainAssets> | null = null

/** Load the mesh and atlas once per page; later calls share the result. */
export function loadBrainAssets(): Promise<BrainAssets> {
  if (!pending) {
    pending = Promise.all([fetchOk('mesh.json'), fetchOk('mesh.bin'), fetchOk('atlas.json')])
      .then(async ([description, binary, atlas]) => ({
        mesh: parseMesh((await description.json()) as MeshDescription, await binary.arrayBuffer()),
        atlas: parseAtlas(await atlas.json()),
      }))
      .catch((error: unknown) => {
        pending = null
        throw error
      })
  }
  return pending
}
