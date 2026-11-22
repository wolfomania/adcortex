import { useId } from 'react'

import type { Limits } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

import { checkScript } from './validation'

export const SAMPLE_SCRIPT =
  'Introducing Lumen, the adaptive lamp. It learns when you work and when you rest. ' +
  'In the evening it glows warm and soft. In the morning it wakes you gently. Lumen. Light that listens.'

interface ScriptFieldProps {
  value: string
  limits: Limits
  isDisabled?: boolean
  onChange: (value: string) => void
}

export function ScriptField({ value, limits, isDisabled, onChange }: ScriptFieldProps) {
  const id = useId()
  const counterId = useId()
  const errorId = useId()
  const length = value.trim().length
  const error = checkScript(value, limits)
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <Label htmlFor={id}>Script</Label>
        {value ? null : (
          <Button
            type="button"
            variant="link"
            size="xs"
            className="h-auto px-0"
            disabled={isDisabled}
            onClick={() => onChange(SAMPLE_SCRIPT)}
          >
            Use a sample script
          </Button>
        )}
      </div>
      <Textarea
        id={id}
        value={value}
        rows={7}
        disabled={isDisabled}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${counterId} ${errorId}` : counterId}
        placeholder="Paste the voice-over or dialogue. It is read aloud by text-to-speech, and the brain model predicts the response to the speech."
        className="min-h-40 resize-y bg-sunken leading-relaxed"
        onChange={(event) => onChange(event.target.value)}
      />
      <div className="flex justify-between gap-3 text-xs">
        <p id={errorId} className="text-destructive" role={error ? 'alert' : undefined}>
          {error}
        </p>
        <p
          id={counterId}
          className={cn(
            'tabular shrink-0 font-mono',
            length > limits.max_script_chars ? 'text-destructive' : 'text-muted-foreground',
          )}
        >
          {length.toLocaleString('en')} / {limits.max_script_chars.toLocaleString('en')}
        </p>
      </div>
    </div>
  )
}
