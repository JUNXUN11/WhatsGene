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
  annotation?: string
  identity?: number
  query_coverage?: number
  alignment_length?: number
  subject_length?: number
  bit_score?: number
  evalue?: number
  classification?: Classification
  taxa_flag?: string | null
}

export interface SearchResult {
  id: number
  kind: string
  program?: string | null
  database?: string | null
  parameters?: Record<string, unknown>
  rid?: string | null
  status: string
  hits?: Hit[]
  error?: string | null
}

export interface Job {
  id: string
  status: JobStatus
  question: string
  raw_input?: string
  input_kind: string
  source?: string
  workflow_mode?: string
  backend_choice?: string
  requested_program?: string | null
  requested_database?: string | null
  accession?: string | null
  detected_type?: string
  query_length?: number
  program?: string | null
  database?: string | null
  organism_filter?: string | null
  parameters?: Record<string, unknown>
  summary?: string | null
  error?: string | null
  hits?: Hit[]
  searches?: SearchResult[]
  outcome?: string | null
  intent?: Record<string, unknown>
  searches_used?: number
  step_log?: StepLogEntry[]
  msa_alignment?: string | null
  tree_newick?: string | null
  homologs?: Array<Record<string, unknown>>
  whatsapp_status?: string
  notified_at?: string | null
  notify_configured?: boolean
  results_url?: string
  data_notice?: string
  created_at?: string
  updated_at?: string
}
