// The 3D cortex: TRIBE v2's predicted response at the playhead, on fsaverage5.
// Loaded on demand (three.js is most of the results page's code).
import {
  Canvas,
  extend,
  useFrame,
  useThree,
  type ThreeElement,
  type ThreeEvent,
} from '@react-three/fiber'
import { useEffect, useMemo, useRef } from 'react'
import {
  Box3,
  BufferAttribute,
  BufferGeometry,
  Vector3,
  type DirectionalLight,
  type PerspectiveCamera,
} from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'

import type { Playback } from '@/features/results/playback'

import { HEMISPHERE_VERTICES, HEMISPHERES, type BrainAssets, type Surface } from './assets'
import { buildBase, buildLut, paintFrame, type FrameSet } from './paint'
import { readPalette } from './palette'
import { setBrainCanvas } from './snapshot'

extend({ OrbitControls })

declare module '@react-three/fiber' {
  interface ThreeElements {
    orbitControls: ThreeElement<typeof OrbitControls>
  }
}

export type BrainViewName = 'left' | 'right' | 'top' | 'back'

/** Direction from the brain's center to the camera, in RAS (z up). */
const VIEW_DIRECTIONS: Record<BrainViewName, [number, number, number]> = {
  left: [-1, 0, 0],
  right: [1, 0, 0],
  top: [0, -0.01, 1],
  back: [0, -1, 0.15],
}
/** Millimetres between the hemispheres, so inflated surfaces don't overlap. */
const GAP_MM = 8
const FOV = 28
/** Room around the brain when a view preset frames it. */
const FRAME_MARGIN = 1.1
/** Repaints per second at most while the media plays. */
const PAINT_RATE = 30

export interface BrainViewProps {
  assets: BrainAssets
  frames: FrameSet
  range: { vmin: number; vmax: number }
  surface: Surface
  view: BrainViewName
  playback: Playback
  /** Called with the vertex under the pointer (fsaverage5 index), or null. */
  onHover?: (vertex: number | null) => void
}

interface Scene {
  geometries: BufferGeometry[]
  colorAttributes: BufferAttribute[]
  colors: Float32Array
  center: Vector3
  radius: number
  /** Vertex positions of each hemisphere, as drawn. */
  points: Float32Array[]
}

function buildScene(assets: BrainAssets, surface: Surface): Scene {
  const colors = new Float32Array(HEMISPHERE_VERTICES * 2 * 3)
  const bounds = new Box3()
  const geometries: BufferGeometry[] = []
  const colorAttributes: BufferAttribute[] = []
  const points: Float32Array[] = []
  HEMISPHERES.forEach((hemisphere, h) => {
    const source = assets.mesh.positions[surface][hemisphere]
    const extent = new Box3().setFromArray(source)
    const shift = h === 0 ? -GAP_MM / 2 - extent.max.x : GAP_MM / 2 - extent.min.x
    const positions = new Float32Array(source)
    for (let i = 0; i < positions.length; i += 3) {
      positions[i] = (positions[i] ?? 0) + shift
    }
    const start = h * HEMISPHERE_VERTICES * 3
    const colorAttribute = new BufferAttribute(
      colors.subarray(start, start + HEMISPHERE_VERTICES * 3),
      3,
    )
    const geometry = new BufferGeometry()
    geometry.setAttribute('position', new BufferAttribute(positions, 3))
    geometry.setAttribute('color', colorAttribute)
    geometry.setIndex(new BufferAttribute(assets.mesh.faces[hemisphere], 1))
    geometry.computeVertexNormals()
    geometry.computeBoundingBox()
    if (geometry.boundingBox) {
      bounds.union(geometry.boundingBox)
    }
    geometries.push(geometry)
    colorAttributes.push(colorAttribute)
    points.push(positions)
  })
  const center = bounds.getCenter(new Vector3())
  const radius = bounds.getSize(new Vector3()).length() / 2
  return { geometries, colorAttributes, colors, center, radius, points }
}

/**
 * The closest the camera can be, looking at `center` from its current
 * direction, with every vertex (and a margin) still in the frame.
 */
function fitDistance(camera: PerspectiveCamera, center: Vector3, points: Float32Array[]): number {
  camera.lookAt(center)
  camera.updateMatrixWorld()
  const right = new Vector3().setFromMatrixColumn(camera.matrixWorld, 0)
  const up = new Vector3().setFromMatrixColumn(camera.matrixWorld, 1)
  const toward = new Vector3().setFromMatrixColumn(camera.matrixWorld, 2)
  const tanV = Math.tan((camera.fov * Math.PI) / 360)
  const tanH = tanV * camera.aspect
  const offset = new Vector3()
  let distance = 0
  for (const array of points) {
    for (let i = 0; i < array.length; i += 3) {
      offset.set(array[i]! - center.x, array[i + 1]! - center.y, array[i + 2]! - center.z)
      const across = Math.abs(offset.dot(right)) / tanH
      const along = Math.abs(offset.dot(up)) / tanV
      distance = Math.max(distance, offset.dot(toward) + FRAME_MARGIN * Math.max(across, along))
    }
  }
  return distance
}

/** Frames the brain from one of the preset directions. */
function aim(controls: OrbitControls, view: BrainViewName, scene: Scene): void {
  const camera = controls.object as PerspectiveCamera
  const [x, y, z] = VIEW_DIRECTIONS[view]
  const direction = new Vector3(x, y, z).normalize()
  camera.position.copy(scene.center).add(direction)
  const distance = fitDistance(camera, scene.center, scene.points)
  camera.position.copy(scene.center).addScaledVector(direction, distance)
  camera.near = scene.radius / 10
  camera.far = scene.radius * 20
  camera.updateProjectionMatrix()
  controls.target.copy(scene.center)
  controls.update()
}

/** Returns a function that colors the cortex at a time, in seconds. */
function createPainter(
  scene: Scene,
  assets: BrainAssets,
  frames: FrameSet,
  range: { vmin: number; vmax: number },
): (time: number) => void {
  const palette = readPalette()
  const base = buildBase(assets.mesh.sulc, assets.mesh.parcel, palette)
  const lut = buildLut(range, palette)
  return (time) => {
    paintFrame(scene.colors, base, assets.mesh.parcel, frames, lut, time)
    for (const attribute of scene.colorAttributes) {
      attribute.needsUpdate = true
    }
  }
}

function Controls({ view, scene }: { view: BrainViewName; scene: Scene }) {
  const camera = useThree((state) => state.camera)
  const element = useThree((state) => state.gl.domElement)
  const invalidate = useThree((state) => state.invalidate)
  // Reframes when the canvas changes shape, as on a phone turning sideways.
  const aspect = useThree((state) => state.size.width / state.size.height)
  const controls = useRef<OrbitControls>(null)

  useEffect(() => {
    const current = controls.current
    if (!current) {
      return
    }
    const onChange = () => invalidate()
    current.addEventListener('change', onChange)
    return () => current.removeEventListener('change', onChange)
  }, [invalidate])

  useEffect(() => {
    if (controls.current) {
      aim(controls.current, view, scene)
      invalidate()
    }
  }, [view, scene, aspect, invalidate])

  useFrame(() => {
    // Damping keeps the view moving after a drag; render until it settles.
    if (controls.current?.update()) {
      invalidate()
    }
  })

  return (
    <orbitControls
      ref={controls}
      args={[camera, element]}
      enableDamping
      enablePan={false}
      minDistance={scene.radius * 1.5}
      maxDistance={scene.radius * 8}
    />
  )
}

/** Lends the canvas to the report export while the view is on screen. */
function RegisterCanvas() {
  const canvas = useThree((state) => state.gl.domElement)
  useEffect(() => {
    setBrainCanvas(canvas)
    return () => setBrainCanvas(null)
  }, [canvas])
  return null
}

function HeadLight() {
  const light = useRef<DirectionalLight>(null)
  useFrame(({ camera }) => {
    light.current?.position.copy(camera.position)
  })
  return <directionalLight ref={light} intensity={2.2} />
}

function Cortex({ assets, frames, range, surface, view, playback, onHover }: BrainViewProps) {
  const invalidate = useThree((state) => state.invalidate)
  const scene = useMemo(() => buildScene(assets, surface), [assets, surface])
  const paint = useMemo(
    () => createPainter(scene, assets, frames, range),
    [scene, assets, frames, range],
  )

  useEffect(() => {
    let lastTick = Number.NaN
    const draw = () => {
      paint(playback.time)
      invalidate()
    }
    draw()
    return playback.subscribe(() => {
      const tick = Math.round(playback.time * PAINT_RATE)
      if (tick !== lastTick) {
        lastTick = tick
        draw()
      }
    })
  }, [paint, playback, invalidate])

  useEffect(
    () => () => {
      for (const geometry of scene.geometries) {
        geometry.dispose()
      }
    },
    [scene],
  )

  const hover = (offset: number) => (event: ThreeEvent<PointerEvent>) => {
    const face = event.face
    onHover?.(face ? offset + face.a : null)
  }

  return (
    <>
      {scene.geometries.map((geometry, h) => (
        <mesh
          key={HEMISPHERES[h]}
          geometry={geometry}
          onPointerMove={hover(h * HEMISPHERE_VERTICES)}
          onPointerOut={() => onHover?.(null)}
        >
          <meshLambertMaterial vertexColors />
        </mesh>
      ))}
      <Controls view={view} scene={scene} />
    </>
  )
}

export default function BrainView(props: BrainViewProps) {
  return (
    <Canvas
      frameloop="demand"
      dpr={[1, 2]}
      camera={{ fov: FOV, up: [0, 0, 1] }}
      // Keeps the last frame for printing and screenshots.
      gl={{ antialias: true, preserveDrawingBuffer: true }}
      aria-label="3D brain: predicted cortical response at the playhead"
    >
      <ambientLight intensity={0.9} />
      <HeadLight />
      <RegisterCanvas />
      <Cortex {...props} />
    </Canvas>
  )
}
