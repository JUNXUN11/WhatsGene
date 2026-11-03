// The / route. In app builds (the local tool) it always goes straight to
// search — /new's auth guard sends guests to login. In landing builds
// (the hosted download page) it renders with no session check, since
// there is no backend behind that site.
export default defineNuxtRouteMiddleware(async () => {
  if (import.meta.server) return
  if (useRuntimeConfig().public.siteMode !== 'landing') {
    return navigateTo('/new')
  }
})
