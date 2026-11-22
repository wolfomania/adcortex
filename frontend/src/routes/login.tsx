// The password gate, shown only when the deployment sets NM_PASSWORD.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, redirect, useNavigate } from '@tanstack/react-router'
import { useId, useState } from 'react'

import { api } from '@/api/endpoints'
import { errorMessage, isApiError } from '@/api/errors'
import { configQuery, queryKeys } from '@/api/queries'
import { safeNext } from '@/app/auth'
import { LogoMark } from '@/components/Logo'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useDocumentTitle } from '@/lib/useDocumentTitle'

interface LoginSearch {
  next?: string
}

export const Route = createFileRoute('/login')({
  validateSearch: (search: Record<string, unknown>): LoginSearch => ({
    next: typeof search.next === 'string' ? search.next : undefined,
  }),
  beforeLoad: async ({ context, search }) => {
    const config = await context.queryClient.ensureQueryData(configQuery())
    if (!config.password_required || config.authenticated) {
      throw redirect({ href: safeNext(search.next), replace: true })
    }
  },
  component: LoginPage,
})

function LoginPage() {
  const { next } = Route.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [password, setPassword] = useState('')
  const inputId = useId()
  const errorId = useId()
  useDocumentTitle('Log in')
  const login = useMutation({
    mutationFn: (value: string) => api.login(value),
    meta: { allowUnauthorized: true },
    onSuccess: async () => {
      // The root route reads the session from the config; load it again.
      queryClient.removeQueries({ queryKey: queryKeys.config })
      await navigate({ href: safeNext(next), replace: true })
    },
  })
  const failure = login.isError
    ? isApiError(login.error, 'unauthorized')
      ? 'That password is not right.'
      : errorMessage(login.error)
    : null

  return (
    <div className="flex flex-1 items-center justify-center px-4 py-16">
      <form
        noValidate
        className="flex w-full max-w-sm flex-col gap-6 rounded-2xl border bg-card p-8 shadow-2xl shadow-black/40"
        onSubmit={(event) => {
          event.preventDefault()
          if (password && !login.isPending) {
            login.mutate(password)
          }
        }}
      >
        <div className="flex flex-col items-center gap-3 text-center">
          <LogoMark className="size-10" />
          <h1 className="text-xl font-semibold tracking-tight">Neuro-Marketing Validator</h1>
          <p className="text-sm text-muted-foreground">Enter the password to continue.</p>
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={inputId}>Password</Label>
          <Input
            id={inputId}
            type="password"
            autoComplete="current-password"
            autoFocus
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            aria-invalid={failure ? true : undefined}
            aria-describedby={failure ? errorId : undefined}
          />
          {failure ? (
            <p id={errorId} role="alert" className="text-sm text-destructive">
              {failure}
            </p>
          ) : null}
        </div>
        <Button type="submit" disabled={!password || login.isPending}>
          {login.isPending ? 'Checking…' : 'Continue'}
        </Button>
      </form>
    </div>
  )
}
