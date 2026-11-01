import type { Job } from '~/types/job'

export interface JobCreateOptions {
  workflow_mode?: 'auto' | 'single' | 'all'
  program?: string | null
  whatsapp_number?: string | null
  search_backend?: 'server' | 'local' | 'ncbi'
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
        whatsapp_number: options.whatsapp_number || null,
        source: 'web',
      },
    })
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

  return { createJob, getJob, listJobs, cancelJob, deleteJob, askJob, alignJob, login, logout, me, base }
}
