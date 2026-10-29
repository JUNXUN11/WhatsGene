export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled'

export interface StepLogEntry {
  seq: number
  step: string
  observation?: string
  decision?: string
  reason?: string
  is_deviation?: boolean
  deviation_reason?: string | null
  created_at?: string
}
export type Classification = 'strong' | 'borderline' | 'not_significant'

export interface Hit {
  accession: string
  organism?: string
  identity?: number
  query_coverage?: number
  alignment_length?: number
  bit_score?: number
  evalue?: number
  classification?: Classification
}

export interface Job {
  id: string
  status: JobStatus
  question: string
  input_kind: string
  accession?: string | null
  detected_type?: string
  program?: string | null
  database?: string | null
  organism_filter?: string | null
  parameters?: Record<string, unknown>
  summary?: string | null
  error?: string | null
  hits?: Hit[]
  outcome?: string | null
  intent?: Record<string, unknown>
  searches_used?: number
  step_log?: StepLogEntry[]
  whatsapp_status?: string
  results_url?: string
  data_notice?: string
  created_at?: string
  updated_at?: string
}
