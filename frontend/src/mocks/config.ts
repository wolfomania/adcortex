// Static parts of the mock backend's configuration.
import type { LanguageOption, Limits } from '@/api/types'

/** The backend's defaults (backend/src/neuromarketing/config.py). */
export const MOCK_LIMITS: Limits = {
  min_duration_s: 3,
  max_duration_s: 180,
  max_upload_mb: 500,
  min_script_chars: 20,
  max_script_chars: 3000,
}

const NAMES: Record<string, string> = {
  en: 'English',
  ar: 'Arabic',
  ca: 'Catalan',
  cs: 'Czech',
  da: 'Danish',
  de: 'German',
  el: 'Greek',
  es: 'Spanish',
  fa: 'Persian',
  fi: 'Finnish',
  fr: 'French',
  he: 'Hebrew',
  hi: 'Hindi',
  hr: 'Croatian',
  hu: 'Hungarian',
  it: 'Italian',
  ja: 'Japanese',
  ko: 'Korean',
  nl: 'Dutch',
  no: 'Norwegian',
  pl: 'Polish',
  pt: 'Portuguese',
  ro: 'Romanian',
  ru: 'Russian',
  sk: 'Slovak',
  sl: 'Slovenian',
  tr: 'Turkish',
  uk: 'Ukrainian',
  vi: 'Vietnamese',
  zh: 'Chinese',
}

/** The backend's language list: TRIBE v2 was trained on English only. */
export const MOCK_LANGUAGES: LanguageOption[] = Object.entries(NAMES).map(([code, name]) => ({
  code,
  name,
  full_support: code === 'en',
}))
