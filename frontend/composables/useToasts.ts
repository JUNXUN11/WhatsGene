// Shared in-app notifications (in-page stand-in for the WhatsApp
// done-notification until outbound delivery is verified).
export interface Toast {
  id: number
  kind: 'done' | 'failed' | 'info'
  title: string
  body?: string
  link?: string
  linkLabel?: string
}

let nextId = 1
const toasts = ref<Toast[]>([])

export function useToasts() {
  function push(t: Omit<Toast, 'id'>, ttlMs = 10000) {
    const id = nextId++
    toasts.value.push({ id, ...t })
    if (ttlMs > 0) {
      setTimeout(() => dismiss(id), ttlMs)
    }
    return id
  }

  function dismiss(id: number) {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  return { toasts, push, dismiss }
}
