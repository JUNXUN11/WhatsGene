import type { Job } from '~/types/job'

export interface JobCreateOptions {
  workflow_mode?: 'auto' | 'single' | 'all'
  program?: string | null
  whatsapp_number?: string | null
}

export function useApi() {
  const config = useRuntimeConfig()
  const base = (config.public.apiBase as string).replace(/\/$/, '')

  async function createJob(sequence: string, question: string, options: JobCreateOptions = {}): Promise<Job> {
    return await $fetch<Job>(`${base}/jobs`, {
      method: 'POST',
      body: {
        sequence, question,
        workflow_mode: options.workflow_mode || 'auto',
        program: options.program || null,
        whatsapp_number: options.whatsapp_number || null,
        source: 'web',
      },
    })
  }

  async function getJob(id: string): Promise<Job> {
    return await $fetch<Job>(`${base}/jobs/${encodeURIComponent(id)}`)
  }

  async function listJobs(): Promise<Job[]> {
    return await $fetch<Job[]>(`${base}/jobs`)
  }

  async function cancelJob(id: string): Promise<Job> {
    return await $fetch<Job>(`${base}/jobs/${encodeURIComponent(id)}/cancel`, { method: 'POST' })
  }

  async function askJob(id: string, question: string): Promise<string> {
    const res = await $fetch<{ answer: string }>(`${base}/jobs/${encodeURIComponent(id)}/ask`, {
      method: 'POST', body: { question },
    })
    return res.answer
  }

  return { createJob, getJob, listJobs, cancelJob, askJob, base }
}
