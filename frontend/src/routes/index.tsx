import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/')({
  component: UploadPage,
})

function UploadPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-24">
      <h1 className="text-3xl font-semibold tracking-tight">Neuro-Marketing Validator</h1>
    </main>
  )
}
