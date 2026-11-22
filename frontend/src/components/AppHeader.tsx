import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import { LogOut } from 'lucide-react'

import { api } from '@/api/endpoints'
import { configQuery } from '@/api/queries'
import { Button } from '@/components/ui/button'

import { Logo } from './Logo'

const NAV = [
  { to: '/', label: 'Analyze', exact: true },
  { to: '/history', label: 'History', exact: false },
  { to: '/compare', label: 'Compare', exact: false },
] as const

interface AppHeaderProps {
  /** Share-link viewers see the brand only. */
  isReadOnly?: boolean
}

export function AppHeader({ isReadOnly = false }: AppHeaderProps) {
  const { data: config } = useQuery(configQuery())
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const logout = useMutation({
    mutationFn: api.logout,
    meta: { allowUnauthorized: true },
    onSettled: async () => {
      queryClient.clear()
      await navigate({ to: '/login', search: { next: undefined } })
    },
  })
  const canLogOut = !isReadOnly && config?.password_required === true && config.authenticated

  return (
    <header className="no-print sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur-md supports-backdrop-filter:bg-background/70">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4 sm:px-6">
        <Link to="/" className="rounded-md" aria-label="Neuro Validator, new analysis">
          <Logo />
        </Link>
        {isReadOnly ? null : (
          <nav aria-label="Main" className="flex items-center gap-1">
            {NAV.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                activeOptions={{ exact: item.exact, includeSearch: false }}
                className="rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground data-[status=active]:bg-secondary data-[status=active]:text-foreground"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        )}
        <div className="ml-auto flex items-center gap-2">
          {canLogOut ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => logout.mutate()}
              disabled={logout.isPending}
            >
              <LogOut aria-hidden />
              Log out
            </Button>
          ) : null}
        </div>
      </div>
    </header>
  )
}
