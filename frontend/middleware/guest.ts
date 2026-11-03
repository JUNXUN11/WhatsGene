// The / route. In app builds (the local tool) it is the front door:
// logged-in users go straight to search, guests get the login page
// (which returns them to search after). In landing builds (the hosted
// download page) it renders with no session check, since there is no
// backend behind that site.
export default defineNuxtRouteMiddleware(async () => {
  if (import.meta.server) return
  if (useRuntimeConfig().public.siteMode !== 'landing') {
    const { ensure } = useAuth()
    if (await ensure()) return navigateTo('/new')
    return navigateTo({ path: '/login', query: { next: '/new' } })
  }
})
