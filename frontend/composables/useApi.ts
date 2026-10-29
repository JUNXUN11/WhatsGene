import type { Job } from '~/types/job'

export function useApi() {
  const config = useRuntimeConfig()
  const base = (config.public.apiBase as string).replace(/\/$/, '')

  async function createJob(sequence: string, question: string): Promise<Job> {
    return await $fetch<Job>(`${base}/jobs`, {
      method: 'POST',
      body: { sequence, question },
    })
  }

  async function getJob(id: string): Promise<Job> {
    return await $fetch<Job>(`${base}/jobs/${encodeURIComponent(id)}`)
  }

  async function listJobs(): Promise<Job[]> {
    return await $fetch<Job[]>(`${base}/jobs`)
  }

  return { createJob, getJob, listJobs, base }
}
