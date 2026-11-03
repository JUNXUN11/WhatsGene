<script setup lang="ts">
// First run (decision 017): the owner picks a username and password.
// Only shown while no account exists, and the backend accepts it only
// from the browser on the machine that runs WhatsGene.
const { status, needsSetup, setup, ensure } = useAuth()
const username = ref('')
const password = ref('')
const confirm = ref('')
const error = ref('')
const busy = ref(false)

onMounted(async () => {
  if (await ensure()) await navigateTo('/new')
  else if (!needsSetup.value) await navigateTo('/login')
})

async function submit() {
  error.value = ''
  if (password.value !== confirm.value) {
    error.value = 'The two passwords are not the same.'
    return
  }
  busy.value = true
  try {
    await setup(username.value.trim(), password.value)
    await navigateTo('/settings?tab=setup')
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; message?: string }
    error.value = err.data?.detail || 'Could not create the account. Is WhatsGene still running?'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="page page-narrow">
    <h1>Welcome to WhatsGene</h1>
    <p class="lede">Create your account. You are the owner of this copy: your workflows stay on this machine. Other people can create their own accounts on the login page, or you can add them in Settings → Accounts.</p>
    <form class="card auth-card" @submit.prevent="submit">
      <label for="welcome-user">Username</label>
      <input id="welcome-user" v-model="username" type="text" autocomplete="username" maxlength="32" required />
      <p class="hint">Letters, digits, dots, dashes, or underscores.</p>
      <label for="welcome-pass">Password</label>
      <input id="welcome-pass" v-model="password" type="password" autocomplete="new-password" required />
      <label for="welcome-confirm">Type the password again</label>
      <input id="welcome-confirm" v-model="confirm" type="password" autocomplete="new-password" required />
      <p class="hint">While you are the only account, this computer keeps you signed in. You need the password when you add other people.</p>
      <p v-if="error" class="error">{{ error }}</p>
      <button class="btn" type="submit" :disabled="busy || status === 'in'">
        {{ busy ? 'Creating…' : 'Create my account' }}
      </button>
    </form>
  </main>
</template>
