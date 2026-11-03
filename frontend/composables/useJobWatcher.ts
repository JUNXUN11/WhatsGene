// Watches all workflows and toasts when one finishes or fails.
// Seeded silently on first load so only transitions notify.
// While this tab sits in the background, a browser notification also
// fires (if the user allowed it), so nobody has to keep checking the tab.

function canNotify(): boolean {
  return typeof window !== 'undefined' && 'Notification' in window
}

// Ask once, from a click (Safari only prompts on a user gesture).
// A denied or already-granted permission is never asked again.
export function requestSystemNotifications() {
  if (!canNotify() || Notification.permission !== 'default') return
  try {
    Notification.requestPermission().catch(() => {})
  } catch {
    // Old browsers without the promise form: the toast still works.
  }
}

export function useJobWatcher() {
  const { listJobs } = useApi()
  const { push } = useToasts()
  const router = useRouter()
  const seen: Record<string, string> = {}
  let seeded = false

  function systemNotify(title: string, body: string | undefined, link: string) {
    if (!canNotify() || Notification.permission !== 'granted' || !document.hidden) return
    try {
      const n = new Notification(title, { body, tag: link })
      n.onclick = () => {
        window.focus()
        router.push(link)
        n.close()
      }
    } catch {
      // Some browsers allow notifications only from a service worker.
    }
  }

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
        const link = `/jobs/${job.id}`
        if (job.status === 'done') {
          const title = `Workflow ${job.id} finished`
          const body = job.outcome ? `Outcome: ${job.outcome}.` : undefined
          push({ kind: 'done', title, body, link, linkLabel: 'View results' })
          systemNotify(title, body, link)
        } else if (job.status === 'failed') {
          const title = `Workflow ${job.id} failed`
          const body = job.error || undefined
          push({ kind: 'failed', title, body, link, linkLabel: 'View details' })
          systemNotify(title, body, link)
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
