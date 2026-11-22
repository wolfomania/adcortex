import { useEffect } from 'react'

export const APP_TITLE = 'Neuro-Marketing Validator'

/** Names the browser tab after the page, and restores the previous name on leaving. */
export function useDocumentTitle(title: string | null | undefined): void {
  useEffect(() => {
    if (!title) {
      return
    }
    const previous = document.title
    document.title = `${title} · ${APP_TITLE}`
    return () => {
      document.title = previous
    }
  }, [title])
}
