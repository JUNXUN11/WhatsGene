// Guards /new and /jobs/**. Client-side only: the session cookie never
// reaches server-side rendering, and the backend 401s regardless.
export default defineNuxtRouteMiddleware(async (to) => {
  if (import.meta.server) return
  const { ensure } = useAuth()
  if (!(await ensure())) {
    return navigateTo({ path: '/login', query: { next: to.fullPath } })
  }
})
