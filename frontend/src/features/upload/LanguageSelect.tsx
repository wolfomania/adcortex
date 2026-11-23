import { ChevronDown } from 'lucide-react'
import { useMemo } from 'react'

import type { LanguageOption } from '@/api/types'
import { cn } from '@/lib/utils'

import { sortLanguages } from './languages'

interface LanguageSelectProps {
  id: string
  value: string
  languages: readonly LanguageOption[]
  isDisabled?: boolean
  describedBy?: string
  onChange: (code: string) => void
}

/** A native select: fast, accessible, and familiar on every platform. */
export function LanguageSelect({
  id,
  value,
  languages,
  isDisabled,
  describedBy,
  onChange,
}: LanguageSelectProps) {
  const sorted = useMemo(() => sortLanguages(languages), [languages])
  return (
    <div className="relative">
      <select
        id={id}
        value={value}
        disabled={isDisabled}
        aria-describedby={describedBy}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          'h-9 w-full appearance-none rounded-lg border border-input bg-input/20 pr-9 pl-3 text-sm text-foreground transition-colors outline-none',
          'hover:bg-input/30 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/40 disabled:opacity-50',
        )}
      >
        <option value="auto">Detect automatically</option>
        {sorted.map((language) => (
          <option key={language.code} value={language.code}>
            {language.full_support ? language.name : `${language.name} (limited support)`}
          </option>
        ))}
      </select>
      <ChevronDown
        aria-hidden
        className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-muted-foreground"
      />
    </div>
  )
}
