import type { QueryClient } from '@tanstack/react-query'
import {
  createRootRouteWithContext,
  Link,
  Outlet,
  redirect,
  useLocation,
  useRouter,
  type ErrorComponentProps,
} from '@tanstack/react-router'
import { CircleAlert, Compass } from 'lucide-react'

import { errorMessage } from '@/api/errors'
import { configQuery } from '@/api/queries'
import { isPublicPath } from '@/app/auth'
import { AppHeader } from '@/components/AppHeader'
import { DemoBanner } from '@/components/DemoBanner'
import { StateMessage } from '@/components/StateMessage'
import { Toaster } from '@/components/Toaster'
import { Button } from '@/components/ui/button'

export interface RouterContext {
  queryClient: QueryClient
}

export const Route = createRootRouteWithContext<RouterContext>()({
  beforeLoad: async ({ context, location }) => {
    if (isPublicPath(location.pathname)) {
      return
    }
    const config = await context.queryClient.ensureQueryData(configQuery())
    if (config.password_required && !config.authenticated) {
      throw redirect({ to: '/login', search: { next: location.href } })
    }
  },
  component: RootLayout,
  errorComponent: RootError,
  notFoundComponent: NotFound,
})

function RootLayout() {
  const { pathname } = useLocation()
  const isLogin = pathname === '/login'
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-primary px-3 py-2 text-primary-foreground focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to content
      </a>
      {isLogin ? null : <AppHeader isReadOnly={pathname.startsWith('/s/')} />}
      <DemoBanner />
      <main id="main" className="flex flex-1 flex-col">
        <Outlet />
      </main>
      <Toaster />
    </div>
  )
}

function RootError({ error, reset }: ErrorComponentProps) {
  const router = useRouter()
  return (
    <StateMessage
      icon={CircleAlert}
      tone="error"
      title="This page could not load"
      actions={
        <>
          <Button
            onClick={() => {
              reset()
              void router.invalidate()
            }}
          >
            Try again
          </Button>
          <Button variant="outline" asChild>
            <Link to="/">New analysis</Link>
          </Button>
        </>
      }
    >
      {errorMessage(error)}
    </StateMessage>
  )
}

function NotFound() {
  return (
    <StateMessage
      icon={Compass}
      title="Page not found"
      actions={
        <Button asChild>
          <Link to="/">Start a new analysis</Link>
        </Button>
      }
    >
      The address may be mistyped, or the page has moved.
    </StateMessage>
  )
}
