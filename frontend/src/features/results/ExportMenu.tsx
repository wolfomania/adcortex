// Saving the results: a standalone HTML report, the page as a PDF (through
// printing), or the data as JSON.
import { Download, FileJson, FileText, Printer } from 'lucide-react'

import { toast } from '@/components/toast-store'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { exportReportHtml, type ReportSource } from '@/features/export/exportReport'
import { downloadJson, slugify } from '@/lib/download'

import { usePlayback } from './playback'

export function ExportMenu({ data }: { data: ReportSource }) {
  const { meta } = data.analysis
  const playback = usePlayback()
  const saveReport = async () => {
    try {
      await exportReportHtml(data, playback)
    } catch (error) {
      toast({
        title: 'The report could not be saved',
        description: error instanceof Error ? error.message : undefined,
        tone: 'error',
      })
    }
  }
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm">
          <Download aria-hidden />
          Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={() => void saveReport()}>
          <FileText aria-hidden />
          Download the report (HTML)
        </DropdownMenuItem>
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
