// The hosted landing build is a single page: every other path
// (/login, /new, anything) bounces back to /. The app build is
// untouched — all routes work there.
export default defineNuxtRouteMiddleware((to) => {
  if (import.meta.server) return
  if (useRuntimeConfig().public.siteMode === 'landing' && to.path !== '/') {
    return navigateTo('/')
  }
})
