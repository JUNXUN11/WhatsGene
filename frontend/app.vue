<script setup lang="ts">
import type { Job } from '~/types/job'

useJobWatcher()
const { status, username, ensure, logout } = useAuth()
const { listJobs } = useApi()
const route = useRoute()

const showLogoutConfirm = ref(false)
const loggingOut = ref(false)
const recent = ref<Job[]>([])
// Recent workflows stay hidden until the user opens them; the choice persists per browser.
const showRecent = ref(false)
const RECENT_KEY = 'wg-sidebar-recent-open'
let recentTimer: ReturnType<typeof setInterval> | undefined

// Authenticated app routes live under the left sidebar; guests keep the plain header.
const showSidebar = computed(() => {
  if (status.value !== 'in') return false
  return route.path === '/new' || route.path.startsWith('/jobs')
})

async function loadRecent() {
  if (!showSidebar.value) return
  try {
    const jobs = await listJobs()
    recent.value = [...jobs]
      .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
      .slice(0, 6)
  } catch {
    // Sidebar recents are a convenience; the workflows page shows load errors.
  }
}

onMounted(() => {
  try {
    showRecent.value = localStorage.getItem(RECENT_KEY) === '1'
  } catch {
    // Private mode etc. — collapsed is a fine default.
  }
  ensure().then(() => loadRecent())
  recentTimer = setInterval(loadRecent, 15000)
})

function toggleRecent() {
  showRecent.value = !showRecent.value
  try {
    localStorage.setItem(RECENT_KEY, showRecent.value ? '1' : '0')
  } catch {
    // Non-persistent is fine; the toggle still works for this visit.
  }
}
onUnmounted(() => {
  if (recentTimer) clearInterval(recentTimer)
})

watch(() => route.path, () => loadRecent())

async function signOut() {
  loggingOut.value = true
  try {
    await logout()
  } finally {
    loggingOut.value = false
    showLogoutConfirm.value = false
  }
  if (route.path !== '/') await navigateTo('/')
}

function shortQuestion(job: Job): string {
  if (job.question) return job.question
  const parts = [job.program, job.database].filter(Boolean)
  return parts.length ? parts.join(' · ') : 'Untitled workflow'
}
</script>

<template>
  <div>
    <header class="site-header" :class="{ 'site-header-app': showSidebar }">
      <div class="header-inner">
        <NuxtLink :to="status === 'in' ? '/new' : '/'" class="brand">
          <span class="brand-mark" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
              <path d="M7 3c0 6 10 6 10 12" />
              <path d="M17 3c0 6-10 6-10 12" />
              <path d="M7.5 7h9M7.5 12h9M7.5 17h9" stroke-width="2" />
            </svg>
          </span>
          <span class="brand-word">Whats<span>Gene</span></span>
        </NuxtLink>
        <nav v-if="!showSidebar" aria-label="Main">
          <NuxtLink to="/">Home</NuxtLink>
        </nav>
        <div class="header-auth">
          <template v-if="status === 'in'">
            <span class="header-user">{{ username }}</span>
            <button class="btn btn-small btn-secondary" @click="showLogoutConfirm = true">Log out</button>
          </template>
          <NuxtLink v-else-if="status === 'out'" to="/login" class="btn btn-small">Log in</NuxtLink>
        </div>
      </div>
    </header>
    <ToastStack />

    <ConfirmDialog
      :open="showLogoutConfirm"
      title="Log out?"
      confirm-label="Log out"
      :busy="loggingOut"
      busy-label="Logging out…"
      @confirm="signOut"
      @cancel="showLogoutConfirm = false"
    >
      <p>Running workflows keep running in the background — you can log back in to check them.</p>
    </ConfirmDialog>

    <div v-if="showSidebar" class="app-body">
      <aside class="sidebar" aria-label="Search and workflows">
        <nav class="side-nav">
          <NuxtLink to="/new" :class="{ 'side-active': route.path === '/new' }">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
            New search
          </NuxtLink>
          <NuxtLink to="/jobs" :class="{ 'side-active': route.path.startsWith('/jobs') }">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h10" /></svg>
            Workflows
          </NuxtLink>
        </nav>
        <template v-if="recent.length">
          <button
            type="button"
            class="side-toggle"
            :aria-expanded="showRecent"
            aria-controls="sidebar-recent"
            @click="toggleRecent"
          >
            <span class="side-toggle-label">Recent</span>
            <span class="side-toggle-count">{{ recent.length }}</span>
            <svg class="side-chevron" :class="{ 'side-chevron-open': showRecent }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
          </button>
          <ul v-if="showRecent" id="sidebar-recent" class="side-recent">
            <li v-for="job in recent" :key="job.id">
              <NuxtLink :to="`/jobs/${job.id}`" :class="{ 'side-current': route.params.id === job.id }" :title="`${job.id} · ${job.status}`">
                <span class="side-dot" :class="`side-${job.status}`" aria-hidden="true" />
                <span class="side-recent-text">
                  <span class="side-recent-q">{{ shortQuestion(job) }}</span>
                  <span class="side-recent-meta">
                    <span class="side-recent-id mono">{{ job.id }}</span>
                    <span class="side-recent-status">{{ job.status }}</span>
                  </span>
                </span>
              </NuxtLink>
            </li>
          </ul>
        </template>
      </aside>
      <div class="app-content">
        <NuxtPage />
      </div>
    </div>
    <NuxtPage v-else />

    <footer class="site-footer">
      <div class="footer-inner">
        <p>
          For research and education only. Every results page shows the backend, program, database and exact parameters; only remote (NCBI) jobs send sequences to NCBI.
        </p>
        <span class="footer-badge">Built with Muse Spark Open</span>
      </div>
    </footer>
  </div>
</template>
