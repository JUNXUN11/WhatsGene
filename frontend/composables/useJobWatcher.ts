// Watches all workflows and toasts when one finishes or fails.
// Seeded silently on first load so only transitions notify.
export function useJobWatcher() {
  const { listJobs } = useApi()
  const { push } = useToasts()
  const seen: Record<string, string> = {}
  let seeded = false

  async function poll() {
    let jobs: Awaited<ReturnType<typeof listJobs>>
    try {
      jobs = await listJobs()
    } catch {
      return // backend unreachable: pages show their own errors
    }
    for (const job of jobs) {
      const prev = seen[job.id]
      const active = prev === 'queued' || prev === 'running'
      if (seeded && active && job.status !== prev) {
        if (job.status === 'done') {
          push({
            kind: 'done',
            title: `Workflow ${job.id} finished`,
            body: job.outcome ? `Outcome: ${job.outcome}.` : undefined,
            link: `/jobs/${job.id}`,
            linkLabel: 'View results',
          })
        } else if (job.status === 'failed') {
          push({
            kind: 'failed',
            title: `Workflow ${job.id} failed`,
            body: job.error || undefined,
            link: `/jobs/${job.id}`,
            linkLabel: 'View details',
          })
        }
      }
      seen[job.id] = job.status
    }
    seeded = true
  }

  onMounted(() => {
    poll()
    const timer = setInterval(poll, 10000)
    onUnmounted(() => clearInterval(timer))
  })
}
