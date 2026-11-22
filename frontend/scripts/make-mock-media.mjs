// Render the media that the development mocks serve (`pnpm gen:mock-media`).
//
// Everything is synthesized with ffmpeg: lavfi test sources for the
// pictures, a generated music bed, and flite text-to-speech for the voice.
// The script writes MP4/M4A files, keyframes, thumbnail strips, and
// timeline.json (scene cuts and spoken sentences with measured timings),
// which the mock fixtures read to line the data up with the media.
//
// Needs ffmpeg built with libx264, libfreetype, and libflite, plus fontconfig.
import { execFileSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const OUT = fileURLToPath(new URL('../src/mocks/media/', import.meta.url))
const WIDTH = 640
const HEIGHT = 360
const FPS = 24
const STRIP_COLUMNS = 10
const VOICE = 'slt'
const ENVELOPE_HZ = 10

const FONT_BOLD = font('sans:bold')
const FONT = font('sans')
const FONT_SYMBOL = font(':charset=263a')

function font(pattern) {
  return execFileSync('fc-match', ['-f', '%{file}', pattern], { encoding: 'utf8' }).trim()
}

function ffmpeg(args) {
  execFileSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', ...args], {
    stdio: 'inherit',
  })
}

/**
 * Loudness per 1/hz s window, as the backend computes it: RMS of 8 kHz mono
 * samples, mapped from [-60 dBFS, 0 dBFS] to [0, 1].
 */
function envelope(file, hz = ENVELOPE_HZ) {
  const raw = execFileSync(
    'ffmpeg',
    [
      '-hide_banner',
      '-loglevel',
      'error',
      '-i',
      file,
      '-vn',
      '-ac',
      '1',
      '-ar',
      '8000',
      '-f',
      's16le',
      '-',
    ],
    { maxBuffer: 64 * 1024 * 1024 },
  )
  const samples = new Int16Array(raw.buffer, raw.byteOffset, Math.floor(raw.byteLength / 2))
  const window = Math.floor(8000 / hz)
  const levels = []
  for (let start = 0; start + window <= samples.length; start += window) {
    let sum = 0
    for (let i = start; i < start + window; i += 1) {
      const value = samples[i] / 32768
      sum += value * value
    }
    const db = 20 * Math.log10(Math.max(Math.sqrt(sum / window), 1e-6))
    levels.push(Math.round(Math.min(1, Math.max(0, (db + 60) / 60)) * 1000) / 1000)
  }
  return levels
}

function duration(file) {
  const out = execFileSync(
    'ffprobe',
    ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file],
    { encoding: 'utf8' },
  )
  return Number.parseFloat(out)
}

/** Escape text for an ffmpeg filter option value inside single quotes. */
function quote(text) {
  return text.replaceAll('\\', '\\\\').replaceAll("'", "\\'").replaceAll(':', '\\:')
}

function caption(text, { size = 26, y = 'h-64', color = 'white', file = FONT } = {}) {
  return (
    `drawtext=fontfile='${file}':text='${quote(text)}':fontcolor=${color}:fontsize=${size}` +
    `:x=(w-text_w)/2:y=${y}:shadowcolor=black@0.6:shadowx=0:shadowy=2`
  )
}

/** Picture sources, one per kind of scene. Each returns a filtergraph. */
const SCENES = {
  title: (d) =>
    `color=c=0x0b0e12:s=${WIDTH}x${HEIGHT}:r=${FPS}:d=${d},` +
    `${caption('LUMEN', { size: 104, y: '(h-text_h)/2-24', file: FONT_BOLD })}:alpha='min(1,t/1.1)',` +
    `${caption('light that listens', { size: 28, y: '(h)/2+48', color: '0x9fd8e0' })}:alpha='min(1,max(0,(t-0.8)/1))'`,
  city: (d) =>
    `mandelbrot=s=${WIDTH}x${HEIGHT}:rate=${FPS}:start_scale=2.6:end_scale=0.02:end_pts=${d * FPS}` +
    `:inner=black:outer=normalized_iteration_count,trim=duration=${d},hue=s=0,format=rgb24,` +
    `lutrgb=r='val':g='val*0.62':b='val*0.3',eq=contrast=1.2:brightness=-0.04,vignette=PI/4,` +
    `${caption('Every night, the city glows.')}`,
  presenter: (d) =>
    `gradients=s=${WIDTH}x${HEIGHT}:r=${FPS}:d=${d}:c0=0x4a2a14:c1=0x120a06:x0=0:y0=0:x1=${WIDTH}:y1=${HEIGHT}:speed=0.004,` +
    `drawtext=fontfile='${FONT_SYMBOL}':text='☺':fontcolor=0xffe2b8:fontsize=210:x=(w-text_w)/2:y=(h-text_h)/2-28` +
    `:alpha='0.85+0.15*sin(2*PI*t*1.3)',${caption('Meet Lumen.')}`,
  product: (d) =>
    `color=c=black:s=${WIDTH}x${HEIGHT}:r=${FPS}:d=${d},format=rgb24,` +
    `geq=r='min(255,30+235*exp(-((X-W/2)*(X-W/2)+(Y-H/2)*(Y-H/2))/(2*pow(70+18*sin(2*PI*T/2.2),2))))'` +
    `:g='min(255,18+170*exp(-((X-W/2)*(X-W/2)+(Y-H/2)*(Y-H/2))/(2*pow(70+18*sin(2*PI*T/2.2),2))))'` +
    `:b='min(255,10+60*exp(-((X-W/2)*(X-W/2)+(Y-H/2)*(Y-H/2))/(2*pow(70+18*sin(2*PI*T/2.2),2))))',` +
    `format=yuv420p,${caption('Warm when you unwind. Bright when you focus.')}`,
  lifestyle: (d) =>
    `life=s=${WIDTH / 4}x${HEIGHT / 4}:rate=${FPS}:ratio=0.08:mold=10:life_color=0xffc070:death_color=0x0b0e12:mold_color=0x34244a,` +
    `scale=${WIDTH}:${HEIGHT}:flags=bilinear,gblur=sigma=5,eq=saturation=1.2,vignette=PI/4,trim=duration=${d},` +
    `${caption('Your evenings, your rhythm.')}`,
  endcard: (d) =>
    `color=c=0x0b0e12:s=${WIDTH}x${HEIGHT}:r=${FPS}:d=${d},` +
    `${caption('LUMEN', { size: 84, y: '(h-text_h)/2-30', file: FONT_BOLD })},` +
    `${caption('Available now  ·  lumen.example', { size: 26, y: '(h)/2+40', color: '0x9fd8e0' })}`,
}

/** Render one scene to an H.264 file without audio. */
function renderScene(kind, seconds, file) {
  ffmpeg([
    '-f',
    'lavfi',
    '-i',
    SCENES[kind](seconds),
    '-t',
    String(seconds),
    '-c:v',
    'libx264',
    '-preset',
    'veryfast',
    '-crf',
    '18',
    '-pix_fmt',
    'yuv420p',
    '-r',
    String(FPS),
    file,
  ])
}

/** Speak sentences at planned times; returns their measured spans. */
function voiceTrack(sentences, total, dir, name) {
  const spans = []
  let cursor = 0
  sentences.forEach(([at, text], index) => {
    const file = join(dir, `${name}-vo-${index}.wav`)
    ffmpeg([
      '-f',
      'lavfi',
      '-i',
      `flite=text='${quote(text)}':voice=${VOICE}`,
      '-ar',
      '44100',
      file,
    ])
    const start = Math.max(at, cursor + 0.15)
    const end = start + duration(file)
    spans.push({ text, start: round(start), end: round(end), file })
    cursor = end
  })
  if (cursor > total) {
    throw new Error(`${name}: voice-over runs to ${cursor.toFixed(2)} s, past ${total} s`)
  }
  const inputs = spans.flatMap((span) => ['-i', span.file])
  const delays = spans
    .map((span, index) => {
      const ms = Math.round(span.start * 1000)
      return `[${index}:a]adelay=${ms}|${ms},apad=whole_dur=${total}[v${index}]`
    })
    .join(';')
  const labels = spans.map((_, index) => `[v${index}]`).join('')
  const out = join(dir, `${name}-vo.wav`)
  ffmpeg([
    ...inputs,
    '-filter_complex',
    `${delays};${labels}amix=inputs=${spans.length}:normalize=0,atrim=duration=${total}[out]`,
    '-map',
    '[out]',
    '-ac',
    '1',
    out,
  ])
  return { file: out, spans: spans.map(({ text, start, end }) => ({ text, start, end })) }
}

/** A chord-pad music bed with an optional kick drum inside [from, to) windows. */
function musicBed(total, dir, name, { chords, kicks = [] }) {
  const bar = 4
  const pick = (voice) =>
    chords
      .map((chord, i) => `if(eq(mod(floor(t/${bar}),${chords.length}),${i}),${chord[voice]},`)
      .join('') +
    chords[0][voice] +
    ')'.repeat(chords.length)
  const env = `(1-exp(-mod(t,${bar})*2.5))*(0.75+0.25*sin(2*PI*t/${bar}))`
  const pad = [0, 1, 2].map((voice) => `0.045*sin(2*PI*${pick(voice)}*t)`).join('+')
  const gate = kicks.length ? kicks.map(([from, to]) => `between(t,${from},${to})`).join('+') : '0'
  const kick = `0.55*(${gate})*sin(2*PI*55*mod(t,0.5))*exp(-mod(t,0.5)*16)`
  const out = join(dir, `${name}-music.wav`)
  ffmpeg([
    '-f',
    'lavfi',
    '-i',
    `aevalsrc='(${pad})*${env}+${kick}':s=44100:d=${total}`,
    '-af',
    `afade=t=in:d=0.6,afade=t=out:st=${total - 1.2}:d=1.2`,
    out,
  ])
  return out
}

function mixAudio(music, voice, out, musicGain = 0.55) {
  ffmpeg([
    '-i',
    music,
    '-i',
    voice,
    '-filter_complex',
    `[0:a]volume=${musicGain}[m];[1:a]volume=1.6[v];[m][v]amix=inputs=2:normalize=0[out]`,
    '-map',
    '[out]',
    '-ac',
    '2',
    out,
  ])
}

/** Concatenate scenes, add audio, and write a fast-start MP4. */
function buildVideo(name, scenes, audio, dir) {
  const parts = scenes.map(([kind, seconds], index) => {
    const file = join(dir, `${name}-scene-${index}.mp4`)
    renderScene(kind, seconds, file)
    return file
  })
  const list = join(dir, `${name}-scenes.txt`)
  writeFileSync(list, parts.map((part) => `file '${part}'`).join('\n'))
  const out = join(OUT, `${name}.mp4`)
  ffmpeg([
    '-f',
    'concat',
    '-safe',
    '0',
    '-i',
    list,
    '-i',
    audio,
    '-c:v',
    'libx264',
    '-preset',
    'slow',
    '-crf',
    '31',
    '-profile:v',
    'main',
    '-pix_fmt',
    'yuv420p',
    '-c:a',
    'aac',
    '-b:a',
    '64k',
    '-shortest',
    '-movflags',
    '+faststart',
    out,
  ])
  return out
}

function buildAudio(name, audio) {
  const out = join(OUT, `${name}.m4a`)
  ffmpeg(['-i', audio, '-c:a', 'aac', '-b:a', '64k', '-movflags', '+faststart', out])
  return out
}

/** Scene spans from scene lengths. */
function spansOf(scenes) {
  let start = 0
  return scenes.map(([, seconds]) => {
    const span = [round(start), round(start + seconds)]
    start += seconds
    return span
  })
}

function keyframes(name, video, spans) {
  mkdirSync(join(OUT, 'keyframes'), { recursive: true })
  spans.forEach(([start, end], index) => {
    ffmpeg([
      '-ss',
      String((start + end) / 2),
      '-i',
      video,
      '-frames:v',
      '1',
      '-vf',
      'scale=480:-2',
      '-q:v',
      '5',
      join(OUT, 'keyframes', `${name}-${index}.jpg`),
    ])
  })
}

function strip(name, video, seconds) {
  const tiles = Math.floor(seconds) + 1
  const rows = Math.ceil(tiles / STRIP_COLUMNS)
  ffmpeg([
    '-i',
    video,
    '-vf',
    `fps=1:round=down,scale=160:-2,tile=${STRIP_COLUMNS}x${rows}`,
    '-frames:v',
    '1',
    '-q:v',
    '6',
    join(OUT, `${name}-strip.jpg`),
  ])
  return { columns: STRIP_COLUMNS, tiles }
}

function round(value) {
  return Math.round(value * 100) / 100
}

const CHORDS_LUMEN = [
  [220, 261.63, 329.63],
  [174.61, 220, 261.63],
  [261.63, 329.63, 392],
  [196, 246.94, 293.66],
]
const CHORDS_RADIO = [
  [261.63, 329.63, 392],
  [220, 277.18, 329.63],
  [196, 246.94, 293.66],
  [174.61, 220, 261.63],
]

function main() {
  mkdirSync(OUT, { recursive: true })
  const work = mkdtempSync(join(tmpdir(), 'nm-mock-media-'))
  const timeline = {}
  try {
    // 30 s launch spot.
    const lumenScenes = [
      ['title', 3.5],
      ['city', 4.5],
      ['presenter', 5.5],
      ['product', 5.5],
      ['lifestyle', 6],
      ['endcard', 5],
    ]
    const lumenVoice = voiceTrack(
      [
        [3.8, 'Every night, the city glows.'],
        [8.3, 'But the light you bring home matters most.'],
        [10.9, 'Meet Lumen, the lamp that learns your rhythm.'],
        [14.2, 'Warm when you unwind. Bright when you focus.'],
        [19.6, 'Your evenings, your rhythm, your light.'],
        [25.8, 'Lumen. Available now.'],
      ],
      30,
      work,
      'lumen-30s',
    )
    const lumenMusic = musicBed(30, work, 'lumen-30s', {
      chords: CHORDS_LUMEN,
      kicks: [
        [3.5, 8],
        [25, 29],
      ],
    })
    const lumenMix = join(work, 'lumen-30s-mix.wav')
    mixAudio(lumenMusic, lumenVoice.file, lumenMix)
    const lumen = buildVideo('lumen-30s', lumenScenes, lumenMix, work)
    const lumenSpans = spansOf(lumenScenes)
    keyframes('lumen-30s', lumen, lumenSpans)
    timeline['lumen-30s'] = {
      duration: round(duration(lumen)),
      width: WIDTH,
      height: HEIGHT,
      scenes: lumenSpans,
      sentences: lumenVoice.spans,
      strip: strip('lumen-30s', lumen, duration(lumen)),
      envelope: envelope(lumen),
    }

    // 15 s cut-down of the same spot.
    const cutScenes = [
      ['title', 2.5],
      ['product', 5.5],
      ['lifestyle', 3],
      ['endcard', 4],
    ]
    const cutVoice = voiceTrack(
      [
        [0.4, 'Meet Lumen.'],
        [2.9, 'Warm when you unwind. Bright when you focus.'],
        [11.4, 'Lumen. Available now.'],
      ],
      15,
      work,
      'lumen-15s',
    )
    const cutMusic = musicBed(15, work, 'lumen-15s', { chords: CHORDS_LUMEN, kicks: [[11, 14.5]] })
    const cutMix = join(work, 'lumen-15s-mix.wav')
    mixAudio(cutMusic, cutVoice.file, cutMix)
    const cut = buildVideo('lumen-15s', cutScenes, cutMix, work)
    const cutSpans = spansOf(cutScenes)
    keyframes('lumen-15s', cut, cutSpans)
    timeline['lumen-15s'] = {
      duration: round(duration(cut)),
      width: WIDTH,
      height: HEIGHT,
      scenes: cutSpans,
      sentences: cutVoice.spans,
      strip: strip('lumen-15s', cut, duration(cut)),
      envelope: envelope(cut),
    }

    // 20 s radio spot (audio only).
    const radioVoice = voiceTrack(
      [
        [0.6, 'Tired of cold, harsh light at home?'],
        [3.6, 'Lumen adapts to your day.'],
        [6.4, 'Warm in the evening, bright in the morning.'],
        [10.6, 'Find Lumen at your local store today.'],
        [14.8, 'Lumen. Light that listens.'],
      ],
      20,
      work,
      'radio-20s',
    )
    const radioMusic = musicBed(20, work, 'radio-20s', { chords: CHORDS_RADIO, kicks: [[0, 20]] })
    const radioMix = join(work, 'radio-20s-mix.wav')
    mixAudio(radioMusic, radioVoice.file, radioMix, 0.45)
    const radio = buildAudio('radio-20s', radioMix)
    timeline['radio-20s'] = {
      duration: round(duration(radio)),
      sentences: radioVoice.spans,
      envelope: envelope(radio),
    }

    // A pasted script, read aloud by text-to-speech (no music), as the
    // backend does for the "text" upload tab.
    const scriptVoice = voiceTrack(
      [
        [0.3, 'Introducing Lumen, the adaptive lamp.'],
        [3.1, 'It learns when you work and when you rest.'],
        [6.2, 'In the evening it glows warm and soft.'],
        [9.2, 'In the morning it wakes you gently.'],
        [12.2, 'Lumen. Light that listens.'],
      ],
      15,
      work,
      'script-15s',
    )
    const script = buildAudio('script-15s', scriptVoice.file)
    timeline['script-15s'] = {
      duration: round(duration(script)),
      sentences: scriptVoice.spans,
      envelope: envelope(script),
    }

    writeFileSync(join(OUT, 'timeline.json'), `${JSON.stringify(timeline, null, 2)}\n`)
    console.log(`Wrote mock media to ${OUT}`)
  } finally {
    rmSync(work, { recursive: true, force: true })
  }
}

main()
