// Saving the results: the page as a PDF (through printing) or the data as JSON.
import { Download, FileJson, Printer } from 'lucide-react'

import type { Analysis, AnalysisResult, StoredReport } from '@/api/types'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { downloadJson, slugify } from '@/lib/download'

export interface ExportData {
  analysis: Analysis
  result: AnalysisResult
  report: StoredReport | null | undefined
}

export function ExportMenu({ data }: { data: ExportData }) {
  const { meta } = data.analysis
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm">
          <Download aria-hidden />
          Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={() => window.print()}>
          <Printer aria-hidden />
          Print or save as PDF
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={() =>
            downloadJson(`${slugify(meta.name)}-${meta.id}.json`, {
              analysis: data.analysis,
              result: data.result,
              report: data.report ?? null,
            })
          }
        >
          <FileJson aria-hidden />
          Download the data (JSON)
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
