// Picking two analyses to compare.

export const COMPARE_SIZE = 2

/** Toggles `id`; a third pick replaces the oldest, so two stay selected. */
export function toggleSelection(selected: readonly string[], id: string): string[] {
  if (selected.includes(id)) {
    return selected.filter((item) => item !== id)
  }
  return [...selected, id].slice(-COMPARE_SIZE)
}
