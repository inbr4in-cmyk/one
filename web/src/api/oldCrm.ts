import { http, qs } from './http'

/** Import from the school's old CRM: several exports at once, preview (dry run) then commit. */
export type ImportStatus = 'new' | 'update' | 'skip' | 'error'
export type ImportTotals = Record<ImportStatus, number>

export interface ImportRow {
  row: number
  status: ImportStatus
  label: string
  reason: string | null
}

export interface ImportFileResult {
  index: number
  filename: string
  kind: string | null
  detected: string | null
  confidence: number
  title: string | null
  header_row: number | null
  error: string | null
  info: Record<string, string>
  totals: ImportTotals
  stats: Record<string, number>
  ms: number
  rows: ImportRow[]
}

export interface ImportResult {
  dry_run: boolean
  /** File indexes in the order they ran (dependency order) */
  order: number[]
  refs: { totals: ImportTotals; rows: ImportRow[] }
  files: ImportFileResult[]
  totals: ImportTotals
  stats: Record<string, number>
}

export interface ImportKind {
  code: string
  title: string
  order: number
}

export const oldCrmApi = {
  kinds: () => http.get<ImportKind[]>('/import/old-crm/kinds'),
  run: (files: File[], kinds: string[], defaultBranchId: number | null, commit: boolean) => {
    const fd = new FormData()
    for (const f of files) fd.append('files', f)
    fd.append('kinds', JSON.stringify(kinds))
    if (defaultBranchId) fd.append('default_branch_id', String(defaultBranchId))
    return http.post<ImportResult>(`/import/old-crm${qs({ commit: commit || undefined })}`, fd, { silent: true })
  },
}
