// Where the password gate applies, and where to send people after login.

/** Pages that work without a session: the login page and share links. */
export function isPublicPath(pathname: string): boolean {
  return pathname === '/login' || pathname.startsWith('/s/')
}

/**
 * The page to open after logging in. Only same-app paths are allowed, so a
 * crafted `?next=` cannot send people to another site.
 */
export function safeNext(next: string | undefined | null): string {
  if (!next || !next.startsWith('/') || next.startsWith('//') || next.startsWith('/\\')) {
    return '/'
  }
  return next.startsWith('/login') ? '/' : next
}
