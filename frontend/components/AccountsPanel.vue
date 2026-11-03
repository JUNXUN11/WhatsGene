<script setup lang="ts">
// Settings → Accounts (decision 017). Everyone can change their own
// password; only the owner sees People and adds, resets, or removes
// accounts. No <form> here: this panel sits inside the Settings form,
// so every button is type="button" and Enter is handled per input.
import type { Account } from '~/composables/useApi'

const { username, auto, owner, refresh } = useAuth()
const { changePassword, listUsers, createUser, resetUserPassword, removeUser } = useApi()
const { push: pushToast } = useToasts()

function detail(e: unknown, fallback: string): string {
  const err = e as { data?: { detail?: string } }
  return err.data?.detail || fallback
}

// --- My password ---
const currentPw = ref('')
const newPw = ref('')
const confirmPw = ref('')
const pwBusy = ref(false)
const pwError = ref('')

async function savePassword() {
  pwError.value = ''
  if (newPw.value !== confirmPw.value) {
    pwError.value = 'The two new passwords are not the same.'
    return
  }
  pwBusy.value = true
  try {
    await changePassword(currentPw.value, newPw.value)
    currentPw.value = newPw.value = confirmPw.value = ''
    pushToast({ kind: 'info', title: 'Password changed', body: 'Other browsers signed in as you are logged out.' })
  } catch (e) {
    pwError.value = detail(e, 'Could not change the password.')
  } finally {
    pwBusy.value = false
  }
}

// --- People (owner only) ---
const people = ref<Account[]>([])
const peopleError = ref('')
const newName = ref('')
const newPass = ref('')
const addBusy = ref(false)
const addError = ref('')
const resetFor = ref<Account | null>(null)
const resetPass = ref('')
const resetBusy = ref(false)
const resetError = ref('')
const removing = ref<Account | null>(null)
const removeBusy = ref(false)

async function loadPeople() {
  if (!owner.value) return
  try {
    people.value = await listUsers()
  } catch (e) {
    peopleError.value = detail(e, 'Could not load the accounts.')
  }
}

onMounted(loadPeople)

async function addPerson() {
  addError.value = ''
  addBusy.value = true
  try {
    const created = await createUser(newName.value.trim(), newPass.value)
    newName.value = newPass.value = ''
    await loadPeople()
    // The second account turns login on for every browser.
    await refresh()
    pushToast({ kind: 'info', title: `Account ${created.username} added`, body: 'Give them the username and password. They can change the password in Settings.' })
  } catch (e) {
    addError.value = detail(e, 'Could not add the account.')
  } finally {
    addBusy.value = false
  }
}

function startReset(person: Account) {
  resetFor.value = person
  resetPass.value = ''
  resetError.value = ''
}

async function saveReset() {
  if (!resetFor.value) return
  resetError.value = ''
  resetBusy.value = true
  try {
    await resetUserPassword(resetFor.value.id, resetPass.value)
    pushToast({ kind: 'info', title: `Password reset for ${resetFor.value.username}`, body: 'They are logged out and use the new password next time.' })
    resetFor.value = null
  } catch (e) {
    resetError.value = detail(e, 'Could not reset the password.')
  } finally {
    resetBusy.value = false
  }
}

async function confirmRemove() {
  if (!removing.value) return
  removeBusy.value = true
  try {
    const res = await removeUser(removing.value.id)
    pushToast({ kind: 'info', title: `Account ${removing.value.username} removed`, body: `${res.moved_workflows} workflow(s) moved to your account.` })
    removing.value = null
    await loadPeople()
    await refresh()
  } catch (e) {
    peopleError.value = detail(e, 'Could not remove the account.')
    removing.value = null
  } finally {
    removeBusy.value = false
  }
}

function joined(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString()
}
</script>

<template>
  <div>
    <fieldset>
      <legend>My account</legend>
      <p class="hint" style="margin-top: 10px;">
        Signed in as <strong>{{ username }}</strong><span v-if="owner"> — the owner of this WhatsGene</span>.
        <span v-if="auto"> This computer keeps you signed in while you are the only account.</span>
      </p>
      <template v-if="!auto">
        <label for="pw-current">Current password</label>
        <input id="pw-current" v-model="currentPw" type="password" autocomplete="current-password" @keydown.enter.prevent="savePassword">
      </template>
      <label for="pw-new">New password</label>
      <input id="pw-new" v-model="newPw" type="password" autocomplete="new-password" @keydown.enter.prevent="savePassword">
      <label for="pw-confirm">Type the new password again</label>
      <input id="pw-confirm" v-model="confirmPw" type="password" autocomplete="new-password" @keydown.enter.prevent="savePassword">
      <div class="submit-row">
        <button class="btn btn-secondary" type="button" :disabled="pwBusy || !newPw" @click="savePassword">{{ pwBusy ? 'Saving…' : 'Change my password' }}</button>
      </div>
      <p v-if="pwError" class="error">{{ pwError }}</p>
    </fieldset>

    <fieldset v-if="owner">
      <legend>People</legend>
      <p class="hint" style="margin-top: 10px;">Each person gets their own workflows. You can add accounts here, and people can also create their own on the login page.</p>
      <ul class="people-list">
        <li v-for="p in people" :key="p.id">
          <span class="person">
            <strong>{{ p.username }}</strong>
            <span v-if="p.owner" class="status-pill status-done">Owner</span>
            <span class="hint person-date">added {{ joined(p.created_at) }}</span>
          </span>
          <span v-if="!p.owner" class="person-actions">
            <button class="btn btn-small btn-secondary" type="button" @click="startReset(p)">Reset password</button>
            <button class="btn btn-small btn-secondary" type="button" @click="removing = p">Remove</button>
          </span>
        </li>
      </ul>
      <div v-if="resetFor" class="reset-box">
        <label for="reset-pass">New password for {{ resetFor.username }}</label>
        <input id="reset-pass" v-model="resetPass" type="password" autocomplete="new-password" @keydown.enter.prevent="saveReset">
        <div class="submit-row">
          <button class="btn btn-small" type="button" :disabled="resetBusy || !resetPass" @click="saveReset">{{ resetBusy ? 'Saving…' : 'Set password' }}</button>
          <button class="btn btn-small btn-secondary" type="button" @click="resetFor = null">Cancel</button>
        </div>
        <p v-if="resetError" class="error">{{ resetError }}</p>
      </div>
      <p v-if="peopleError" class="error">{{ peopleError }}</p>

      <h3 class="add-title">Add a person</h3>
      <p v-if="people.length === 1" class="hint">After you add the first person, every browser asks for a login, this one too. Your username is <strong>{{ username }}</strong>; make sure you know your password first.</p>
      <label for="add-name">Username</label>
      <input id="add-name" v-model="newName" type="text" autocomplete="off" maxlength="32" @keydown.enter.prevent="addPerson">
      <label for="add-pass">Starting password</label>
      <input id="add-pass" v-model="newPass" type="password" autocomplete="new-password" @keydown.enter.prevent="addPerson">
      <p class="hint">Tell the person their username and password; they can change the password in Settings → Accounts.</p>
      <div class="submit-row">
        <button class="btn" type="button" :disabled="addBusy || !newName || !newPass" @click="addPerson">{{ addBusy ? 'Adding…' : 'Add account' }}</button>
      </div>
      <p v-if="addError" class="error">{{ addError }}</p>
    </fieldset>

    <ConfirmDialog
      :open="!!removing"
      :title="`Remove ${removing?.username}?`"
      confirm-label="Remove account"
      danger
      :busy="removeBusy"
      busy-label="Removing…"
      @confirm="confirmRemove"
      @cancel="removing = null"
    >
      <p>They can no longer log in. Their workflows move to your account, so no result is lost.</p>
    </ConfirmDialog>
  </div>
</template>

<style scoped>
.people-list { list-style: none; margin: 12px 0 0; padding: 0; display: grid; gap: 8px; }
.people-list li {
  display: flex; gap: 12px; align-items: center; justify-content: space-between; flex-wrap: wrap;
  padding: 10px 14px; background: var(--surface); border: 1px solid var(--line-strong); border-radius: 8px;
}
.person { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.person-date { margin-top: 0; }
.person-actions { display: flex; gap: 8px; }
.reset-box { margin-top: 12px; }
.add-title { font-size: 15px; margin: 22px 0 4px; }
.submit-row { display: flex; gap: 12px; margin-top: 14px; align-items: center; flex-wrap: wrap; }
</style>
