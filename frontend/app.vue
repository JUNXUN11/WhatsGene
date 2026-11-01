<script setup lang="ts">
useJobWatcher()
const { status, username, ensure, logout } = useAuth()
const route = useRoute()

onMounted(() => { ensure() })

async function signOut() {
  await logout()
  if (route.path !== '/') await navigateTo('/')
}
</script>

<template>
  <div>
    <header class="site-header">
      <div class="header-inner">
        <NuxtLink to="/" class="brand">
          <span class="brand-mark" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
              <path d="M7 3c0 6 10 6 10 12" />
              <path d="M17 3c0 6-10 6-10 12" />
              <path d="M7.5 7h9M7.5 12h9M7.5 17h9" stroke-width="2" />
            </svg>
          </span>
          <span class="brand-word">Whats<span>Gene</span></span>
        </NuxtLink>
        <nav aria-label="Main">
          <NuxtLink to="/">Home</NuxtLink>
          <template v-if="status === 'in'">
            <NuxtLink to="/new">New search</NuxtLink>
            <NuxtLink to="/jobs">Workflows</NuxtLink>
          </template>
        </nav>
        <div class="header-auth">
          <template v-if="status === 'in'">
            <span class="header-user">{{ username }}</span>
            <button class="btn btn-small btn-secondary" @click="signOut">Log out</button>
          </template>
          <NuxtLink v-else-if="status === 'out'" to="/login" class="btn btn-small">Log in</NuxtLink>
        </div>
      </div>
    </header>
    <ToastStack />
    <NuxtPage />
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
