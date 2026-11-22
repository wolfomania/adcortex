// The transcript, word by word; the spoken word follows the playhead.
import type { LanguageInfo, Word } from '@/api/types'
import { cn } from '@/lib/utils'

import { usePlayback, usePlaybackTime } from './playback'

function languageNote(language: LanguageInfo): string | null {
  const code = language.detected ?? language.requested
  if (!code || code === 'auto') {
    return null
  }
  const name = new Intl.DisplayNames(['en'], { type: 'language' }).of(code) ?? code
  const how = language.detected ? 'detected' : 'as requested'
  return language.full_support === false
    ? `${name} (${how}). TRIBE v2 was trained on English speech, so text responses are less reliable.`
    : `${name} (${how}).`
}

export function Transcript({
  words,
  language,
}: {
  words: readonly Word[]
  language: LanguageInfo
}) {
  const playback = usePlayback()
  const time = usePlaybackTime(0.2)
  const note = languageNote(language)
  return (
    <section aria-labelledby="transcript-title" className="flex flex-col gap-2">
      <h2 id="transcript-title" className="text-sm font-medium">
        Transcript
      </h2>
      {note ? <p className="text-xs text-muted-foreground">{note}</p> : null}
      {words.length ? (
        <p className="text-sm leading-7">
          {words.map((word, i) => (
            <button
              key={`${word.start}-${i}`}
              type="button"
              onClick={() => playback.seek(word.start)}
              className={cn(
                'rounded px-0.5 hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none',
                time >= word.start && time < word.end && 'bg-viz-playhead/25',
              )}
            >
              {word.text}
            </button>
          ))}
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">No speech was found.</p>
      )}
    </section>
  )
}
