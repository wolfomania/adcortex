// The start page: what the tool does, and the upload form.
import { useSuspenseQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import { AudioWaveform, BrainCircuit, NotebookPen } from 'lucide-react'

import { configQuery } from '@/api/queries'
import { UploadForm } from '@/features/upload/UploadForm'

export const Route = createFileRoute('/')({
  loader: ({ context }) => context.queryClient.ensureQueryData(configQuery()),
  component: UploadPage,
})

const STEPS = [
  {
    icon: BrainCircuit,
    title: 'Predict',
    text: 'TRIBE v2, Meta’s brain-encoding model, turns the picture, sound, and words into the response of 20,484 points on the cortex, second by second.',
  },
  {
    icon: AudioWaveform,
    title: 'Measure',
    text: 'The points are grouped into ten brain systems, from faces and speech to attention and valuation, and scored against reference ads.',
  },
  {
    icon: NotebookPen,
    title: 'Explain',
    text: 'A language model reads the numbers, and the clip when it can, and writes the strengths, risks, and fixes.',
  },
]

function UploadPage() {
  const { data: config } = useSuspenseQuery(configQuery())
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-12 px-4 py-12 sm:px-6 sm:py-16">
      <div className="flex flex-col gap-4 text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
          How would a brain respond to your ad?
        </h1>
        <p className="mx-auto max-w-2xl text-pretty text-muted-foreground">
          Upload a video, an audio spot, or a script. See which brain systems it engages, moment by
          moment, and what to change.
        </p>
      </div>
      <UploadForm config={config} />
      <section aria-labelledby="how-title" className="flex flex-col gap-6">
        <h2 id="how-title" className="text-sm font-medium text-muted-foreground">
          How it works
        </h2>
        <ol className="grid gap-6 sm:grid-cols-3">
          {STEPS.map((step, index) => (
            <li key={step.title} className="flex flex-col gap-2">
              <step.icon className="size-5 text-primary" aria-hidden />
              <h3 className="text-sm font-medium">
                {index + 1}. {step.title}
              </h3>
              <p className="text-sm text-muted-foreground">{step.text}</p>
            </li>
          ))}
        </ol>
        <p className="text-xs text-muted-foreground">
          The predictions describe an average brain, not your audience. Treat them as hypotheses to
          test, not as a forecast of sales.
        </p>
      </section>
    </div>
  )
}
