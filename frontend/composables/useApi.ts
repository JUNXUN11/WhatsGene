import type { Job } from '~/types/job'

export interface Cutoffs {
  strong_max_evalue: number
  strong_min_coverage: number
  borderline_max_evalue: number
  borderline_min_coverage: number
}

export interface UserSettings {
  lab_name: string
  default_organism: string
  default_backend: 'server' | 'local' | 'ncbi'
  strictness: 'strict' | 'balanced' | 'loose'
  cutoff_mode: 'standard' | 'custom'
  cutoffs: Cutoffs
  muse_base_url: string
  muse_model: string
}

export interface SetupStep { id: string; title: string; status: string; detail: string }

export interface SettingsResponse {
  settings: UserSettings
  muse_key_set: boolean
  muse_key_last4: string
  presets: Record<string, { label: string; help: string; evalue_threshold: number | null }>
  standard_cutoffs: Cutoffs
  database_options: Record<string, { label: string; size: string; source: string }>
  setup: {
    search_backend: string
    blast_plus_installed: boolean
    blastdb_path: string
    local_db_ready: boolean
  }
  server_model: { model: string; configured: boolean }
}

export interface AiSetupResponse {
  reply: string
  mode: 'demo' | 'live'
  plan: { database: string; steps: SetupStep[] }
}

export interface JobCreateOptions {
  workflow_mode?: 'auto' | 'single' | 'all'
  program?: string | null
  whatsapp_number?: string | null
  search_backend?: 'server' | 'local' | 'ncbi'
  database?: string | null
}

export interface LibraryFile {
  root: string
  path: string
  name: string
  size_bytes: number
  kind: string
  category_proposed: string
  category: string | null
  reason: string
  confidence: string
  sequence_type: string | null
  sequence_count: number
  first_header: string
  total_length: number
  can_search: boolean
  can_build_database: boolean
  needs_review: boolean
}

export interface LibraryResponse {
  inbox_dir: string
  library_dir: string
  inbox: LibraryFile[]
  library: LibraryFile[]
}

export interface SetupRunState {
  running: boolean
  status: 'idle' | 'running' | 'done' | 'failed'
  database: string
  steps: SetupStep[]
  log: string[]
  setup: SettingsResponse['setup']
}

export interface LocalDatabase {
  name: string
  stem: string
  dbtype: 'protein' | 'nucleotide'
  label: string
  description: string
  ready: boolean
}

export function useApi() {
  const config = useRuntimeConfig()
  const base = (config.public.apiBase as string).replace(/\/$/, '')
  // Session cookie must travel with every API call (backend gates on it).
  const withCreds = { credentials: 'include' as const }

  async function login(username: string, password: string): Promise<{ username: string }> {
    return await $fetch<{ username: string }>(`${base}/auth/login`, {
      ...withCreds, method: 'POST', body: { username, password },
    })
  }

  async function logout(): Promise<void> {
    await $fetch(`${base}/auth/logout`, { ...withCreds, method: 'POST' })
  }

  async function me(): Promise<{ authenticated: boolean; username?: string }> {
    return await $fetch<{ authenticated: boolean; username?: string }>(`${base}/auth/me`, withCreds)
  }

  async function createJob(sequence: string, question: string, options: JobCreateOptions = {}): Promise<Job> {
    return await $fetch<Job>(`${base}/jobs`, {
      ...withCreds,
      method: 'POST',
      body: {
        sequence, question,
        workflow_mode: options.workflow_mode || 'auto',
        search_backend: options.search_backend || 'server',
        program: options.program || null,
        database: options.database || null,
        whatsapp_number: options.whatsapp_number || null,
        source: 'web',
      },
    })
  }

  async function getLibrary(): Promise<LibraryResponse> {
    return await $fetch<LibraryResponse>(`${base}/library`, withCreds)
  }

  async function sortLibrary(items: { path: string; category: string }[]): Promise<{ sorted: unknown[] }> {
    return await $fetch(`${base}/library/sort`, { ...withCreds, method: 'POST', body: { items } })
  }

  async function buildDatabase(root: string, path: string, name: string): Promise<LocalDatabase & { sequence_count?: number }> {
    return await $fetch(`${base}/library/build-database`, { ...withCreds, method: 'POST', body: { root, path, name } })
  }

  async function buildFromTaxon(organism: string, name: string): Promise<LocalDatabase & { sequence_count?: number }> {
    return await $fetch(`${base}/library/build-from-taxon`, { ...withCreds, method: 'POST', body: { organism, name } })
  }

  async function libraryQueryText(root: string, path: string): Promise<string> {
    const res = await $fetch<{ text: string }>(`${base}/library/query-text`, {
      ...withCreds, query: { root, path },
    })
    return res.text
  }

  async function runSetup(database = 'swissprot'): Promise<SetupRunState> {
    return await $fetch<SetupRunState>(`${base}/setup/run`, {
      ...withCreds, method: 'POST', body: { database },
    })
  }

  async function setupStatus(): Promise<SetupRunState> {
    return await $fetch<SetupRunState>(`${base}/setup/status`, withCreds)
  }

  async function listDatabases(): Promise<LocalDatabase[]> {
    const res = await $fetch<{ databases: LocalDatabase[] }>(`${base}/databases`, withCreds)
    return res.databases
  }

  async function getJob(id: string): Promise<Job> {
    return await $fetch<Job>(`${base}/jobs/${encodeURIComponent(id)}`, withCreds)
  }

  async function listJobs(): Promise<Job[]> {
    return await $fetch<Job[]>(`${base}/jobs`, withCreds)
  }

  async function cancelJob(id: string): Promise<Job> {
    return await $fetch<Job>(`${base}/jobs/${encodeURIComponent(id)}/cancel`, { ...withCreds, method: 'POST' })
  }

  async function deleteJob(id: string): Promise<{ status: string; id: string }> {
    return await $fetch<{ status: string; id: string }>(`${base}/jobs/${encodeURIComponent(id)}`, { ...withCreds, method: 'DELETE' })
  }

  async function alignJob(id: string): Promise<Job> {
    return await $fetch<Job>(`${base}/jobs/${encodeURIComponent(id)}/align`, { ...withCreds, method: 'POST' })
  }

  async function askJob(id: string, question: string): Promise<string> {
    const res = await $fetch<{ answer: string }>(`${base}/jobs/${encodeURIComponent(id)}/ask`, {
      ...withCreds, method: 'POST', body: { question },
    })
    return res.answer
  }

  async function getSettings(): Promise<SettingsResponse> {
    return await $fetch<SettingsResponse>(`${base}/settings`, withCreds)
  }

  async function saveSettings(settings: UserSettings & { muse_api_key?: string; clear_muse_key?: boolean }): Promise<UserSettings> {
    const res = await $fetch<{ settings: UserSettings }>(`${base}/settings`, {
      ...withCreds, method: 'PUT', body: settings,
    })
    return res.settings
  }

  async function aiSetup(database: string, message: string): Promise<AiSetupResponse> {
    return await $fetch<AiSetupResponse>(`${base}/settings/ai-setup`, {
      ...withCreds, method: 'POST', body: { database, message },
    })
  }

  return { createJob, getJob, listJobs, listDatabases, getLibrary, sortLibrary, buildDatabase, buildFromTaxon, libraryQueryText, runSetup, setupStatus, cancelJob, deleteJob, askJob, alignJob, login, logout, me, getSettings, saveSettings, aiSetup, base }
}
