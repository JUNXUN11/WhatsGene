<script setup lang="ts">
const route = useRoute()
const { status, login, ensure } = useAuth()
const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

function nextPath(): string {
  const next = route.query.next
  return typeof next === 'string' && next.startsWith('/') ? next : '/jobs'
}

onMounted(async () => {
  if (await ensure()) await navigateTo(nextPath())
})

async function submit() {
  error.value = ''
  busy.value = true
  try {
    await login(username.value.trim(), password.value)
    await navigateTo(nextPath())
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; message?: string }
    error.value = err.data?.detail || 'Could not log in. Is the backend running on port 8000?'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="page page-narrow">
    <div class="crumbs">
      <NuxtLink to="/">Home</NuxtLink>
      <span class="sep">/</span>
      <span>Log in</span>
    </div>
    <h1>Log in</h1>
    <p class="lede">Search and workflows need an account. This demo has one shared reviewer account — no sign-up.</p>
    <form class="card auth-card" @submit.prevent="submit">
      <label for="login-user">Username</label>
      <input id="login-user" v-model="username" type="text" autocomplete="username" required />
      <label for="login-pass">Password</label>
      <input id="login-pass" v-model="password" type="password" autocomplete="current-password" required />
      <p v-if="error" class="error">{{ error }}</p>
      <button class="btn" type="submit" :disabled="busy || status === 'in'">
        {{ busy ? 'Logging in…' : 'Log in' }}
      </button>
    </form>
  </main>
</template>
