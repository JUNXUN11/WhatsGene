<script setup lang="ts">
// Log in, or create an account when this WhatsGene allows sign-up
// (decision 017). A new account is a member with its own workflows.
const route = useRoute()
const { status, needsSetup, signupOpen, login, register, ensure } = useAuth()
const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const confirm = ref('')
const error = ref('')
const busy = ref(false)

function nextPath(): string {
  const next = route.query.next
  return typeof next === 'string' && next.startsWith('/') ? next : '/new'
}

onMounted(async () => {
  if (await ensure()) await navigateTo(nextPath())
  else if (needsSetup.value) await navigateTo('/welcome')
})

function switchMode(to: 'login' | 'register') {
  mode.value = to
  error.value = ''
  password.value = ''
  confirm.value = ''
}

async function submit() {
  error.value = ''
  if (mode.value === 'register' && password.value !== confirm.value) {
    error.value = 'The two passwords are not the same.'
    return
  }
  busy.value = true
  try {
    if (mode.value === 'register') await register(username.value.trim(), password.value)
    else await login(username.value.trim(), password.value)
    await navigateTo(nextPath())
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; message?: string }
    error.value = err.data?.detail || (mode.value === 'register'
      ? 'Could not create the account. Is WhatsGene still running?'
      : 'Could not log in. Is the backend running on port 8000?')
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
      <span>{{ mode === 'register' ? 'Create an account' : 'Log in' }}</span>
    </div>
    <template v-if="mode === 'login'">
      <h1>Log in</h1>
      <p v-if="signupOpen" class="lede">Search and workflows need an account. New here? Create one below; your workflows stay private to your account.</p>
      <p v-else class="lede">Search and workflows need an account. The owner of this WhatsGene adds accounts in Settings → Accounts.</p>
    </template>
    <template v-else>
      <h1>Create an account</h1>
      <p class="lede">Pick a username and a password. You get your own workflows; nobody else on this WhatsGene sees them.</p>
    </template>
    <form class="card auth-card" @submit.prevent="submit">
      <label for="login-user">Username</label>
      <input id="login-user" v-model="username" type="text" autocomplete="username" :maxlength="mode === 'register' ? 32 : undefined" required />
      <p v-if="mode === 'register'" class="hint">Letters, digits, dots, dashes, or underscores.</p>
      <label for="login-pass">Password</label>
      <input id="login-pass" v-model="password" type="password" :autocomplete="mode === 'register' ? 'new-password' : 'current-password'" required />
      <template v-if="mode === 'register'">
        <label for="login-confirm">Type the password again</label>
        <input id="login-confirm" v-model="confirm" type="password" autocomplete="new-password" required />
      </template>
      <p v-if="error" class="error">{{ error }}</p>
      <button class="btn" type="submit" :disabled="busy || status === 'in'">
        <template v-if="mode === 'register'">{{ busy ? 'Creating…' : 'Create account' }}</template>
        <template v-else>{{ busy ? 'Logging in…' : 'Log in' }}</template>
      </button>
      <p v-if="signupOpen && mode === 'login'" class="auth-switch">
        No account yet? <button type="button" class="link-button" @click="switchMode('register')">Create an account</button>
      </p>
      <p v-if="mode === 'register'" class="auth-switch">
        Already have an account? <button type="button" class="link-button" @click="switchMode('login')">Log in</button>
      </p>
    </form>
  </main>
</template>

<style scoped>
.auth-switch { margin: 14px 0 0; font-size: 14px; color: var(--muted); text-align: center; }
.link-button {
  background: none; border: 0; padding: 0; font: inherit; font-weight: 600;
  color: var(--accent); cursor: pointer; text-decoration: underline; text-underline-offset: 3px;
}
</style>
