import type { LanguageOption } from '@/api/types'

/** Full-support languages first, then the rest alphabetically. */
export function sortLanguages(languages: readonly LanguageOption[]): LanguageOption[] {
  return [...languages].sort((a, b) => {
    if (a.full_support !== b.full_support) {
      return a.full_support ? -1 : 1
    }
    return a.name.localeCompare(b.name)
  })
}
