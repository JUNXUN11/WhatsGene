// Guards /new and /jobs/**. Client-side only: the session cookie never
// reaches server-side rendering, and the backend 401s regardless. A
// fresh install with no account opens the first-run page instead.
export default defineNuxtRouteMiddleware(async (to) => {
  if (import.meta.server) return
  const { ensure, needsSetup } = useAuth()
  if (!(await ensure())) {
    if (needsSetup.value) return navigateTo('/welcome')
    return navigateTo({ path: '/login', query: { next: to.fullPath } })
  }
})
