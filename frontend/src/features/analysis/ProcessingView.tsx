// An analysis on its way: the pipeline stages and live progress.
import { Link } from '@tanstack/react-router'
import { Circle, CircleCheck, LoaderCircle } from 'lucide-react'

import type { Analysis } from '@/api/types'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'

import {
  progressFraction,
  progressMessage,
  STATUS_STEPS,
  stepState,
  type StepState,
} from './status'

function StepIcon({ state }: { state: StepState }) {
  if (state === 'done') {
    return <CircleCheck className="size-5 text-status-good" aria-hidden />
  }
  if (state === 'current') {
    return <LoaderCircle className="size-5 animate-spin text-primary" aria-hidden />
  }
  return <Circle className="size-5 text-muted-foreground/50" aria-hidden />
}

const STATE_LABELS: Record<StepState, string> = {
  done: 'done',
  current: 'in progress',
  upcoming: 'not started',
}

export function ProcessingView({ analysis }: { analysis: Analysis }) {
  const percent = Math.round(progressFraction(analysis) * 100)
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-8 px-4 py-12 sm:px-6">
      <div className="flex flex-col gap-1">
        <p className="text-xs text-muted-foreground">Analyzing</p>
        <h1 className="truncate text-2xl font-semibold tracking-tight">{analysis.meta.name}</h1>
      </div>
      <div className="flex flex-col gap-2">
        <Progress value={percent} aria-label={`Progress: ${percent}%`} />
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {progressMessage(analysis)}
        </p>
      </div>
      <ol className="flex flex-col gap-4" aria-label="Stages">
        {STATUS_STEPS.map((step) => {
          const state = stepState(step.status, analysis.state.status)
          return (
            <li
              key={step.status}
              className="flex gap-3"
              aria-current={state === 'current' ? 'step' : undefined}
            >
              <StepIcon state={state} />
              <div className="flex flex-col gap-0.5">
                <p
                  className={cn(
                    'text-sm font-medium',
                    state === 'upcoming' && 'text-muted-foreground',
                  )}
                >
                  {step.label}
                  <span className="sr-only">: {STATE_LABELS[state]}</span>
                </p>
                {state === 'current' ? (
                  <p className="text-sm text-muted-foreground">{step.detail}</p>
                ) : null}
              </div>
            </li>
          )
        })}
      </ol>
      <p className="text-sm text-muted-foreground">
        You can close this page. The analysis keeps running and stays in{' '}
        <Link to="/history" className="underline underline-offset-4 hover:text-foreground">
          History
        </Link>
        .
      </p>
    </div>
  )
}
