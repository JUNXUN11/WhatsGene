// Guests-only (landing page). Logged-in visitors go straight to search —
// after login there is no home page, only search and workflows.
export default defineNuxtRouteMiddleware(async () => {
  if (import.meta.server) return
  const { ensure } = useAuth()
  if (await ensure()) {
    return navigateTo('/new')
  }
})
