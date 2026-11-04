<script setup lang="ts">
import type { AiSetupResponse, SettingsResponse, SetupRunState, UserSettings } from '~/composables/useApi'

definePageMeta({ middleware: 'auth' })

const { getSettings, saveSettings, revealMuseKey, aiSetup, runSetup, setupStatus } = useApi()
const { push: pushToast } = useToasts()

const form = ref<UserSettings>({
  lab_name: '',
  default_organism: '',
  default_backend: 'server',
  strictness: 'balanced',
  cutoff_mode: 'standard',
  cutoffs: { strong_max_evalue: 0.00001, strong_min_coverage: 70, borderline_max_evalue: 0.01, borderline_min_coverage: 30 },
  muse_base_url: '',
  muse_model: '',
})
const presets = ref<SettingsResponse['presets']>({})
const standardCutoffs = ref<UserSettings['cutoffs'] | null>(null)
const databaseOptions = ref<SettingsResponse['database_options']>({})
const setup = ref<SettingsResponse['setup'] | null>(null)
const keySet = ref(false)
const apiKeyInput = ref('')
// Eye button: shows typed text, or fetches the saved key on demand.
const showKey = ref(false)
const revealedKey = ref('')
const confirmRemoveKey = ref(false)
const busy = ref(false)
const loading = ref(true)
const error = ref('')

const dbChoice = ref('swissprot')
const setupMessage = ref('')
const setupBusy = ref(false)
const setupResult = ref<AiSetupResponse | null>(null)
const setupError = ref('')
const runState = ref<SetupRunState | null>(null)
const runError = ref('')
let pollTimer: ReturnType<typeof setInterval> | null = null

const backendOptions = [
  { value: 'server', label: 'Server default — whatever this install is configured for' },
  { value: 'local', label: 'Local BLAST — on this machine, private, seconds' },
  { value: 'ncbi', label: 'Real NCBI BLAST — all databases, slower, sequence sent to NCBI' },
] as const

const strictnessOrder = ['strict', 'balanced', 'loose'] as const

const tabs = [
  { id: 'ai', label: 'Muse AI' },
  { id: 'setup', label: 'Local BLAST setup' },
  { id: 'lab', label: 'My lab' },
  { id: 'judging', label: 'Search & judging' },
  { id: 'accounts', label: 'Accounts' },
] as const
type TabId = (typeof tabs)[number]['id']
// ?tab=setup opens a tab directly (the first-run page sends new owners
// to Local BLAST setup).
const route = useRoute()
const requestedTab = tabs.find(t => t.id === route.query.tab)?.id
const activeTab = ref<TabId>(requestedTab || 'ai')

const stepMarks: Record<string, string> = {
  done: 'Done', needed: 'Needed', pending: 'Waiting', demo_only: 'Plan only',
  running: 'Running', skipped: 'Skipped', failed: 'Failed',
}

async function load() {
  try {
    const res = await getSettings()
    form.value = { ...res.settings, cutoffs: { ...res.settings.cutoffs } }
    presets.value = res.presets
    standardCutoffs.value = res.standard_cutoffs
    databaseOptions.value = res.database_options
    setup.value = res.setup
    keySet.value = res.muse_key_set
  } catch {
    error.value = 'Could not load your settings. Is the backend running on port 8000?'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await load()
  await refreshRunState()
  if (runState.value?.running) startPolling()
})

async function save() {
  error.value = ''
  busy.value = true
  try {
    const payload = { ...form.value, cutoffs: { ...form.value.cutoffs } } as UserSettings & { muse_api_key?: string }
    if (apiKeyInput.value.trim()) payload.muse_api_key = apiKeyInput.value.trim()
    form.value = await saveSettings(payload)
    apiKeyInput.value = ''
    hideKey()
    await load()
    pushToast({ kind: 'info', title: 'Settings saved', body: 'New searches will use them.' })
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; message?: string }
    error.value = err.data?.detail || err.message || 'Could not save settings.'
  } finally {
    busy.value = false
  }
}

function hideKey() {
  showKey.value = false
  // A revealed saved key goes back to ****; typed text stays (masked).
  if (revealedKey.value && apiKeyInput.value === revealedKey.value) apiKeyInput.value = ''
  revealedKey.value = ''
}

async function toggleKey() {
  if (showKey.value) return hideKey()
  if (keySet.value && !apiKeyInput.value) {
    try {
      revealedKey.value = await revealMuseKey()
      apiKeyInput.value = revealedKey.value
    } catch {
      error.value = 'Could not show the saved key.'
      return
    }
  }
  showKey.value = true
}

function deleteKey() {
  if (keySet.value) confirmRemoveKey.value = true
  else apiKeyInput.value = ''
}

async function removeKey() {
  busy.value = true
  try {
    await saveSettings({ ...form.value, cutoffs: { ...form.value.cutoffs }, clear_muse_key: true })
    apiKeyInput.value = ''
    hideKey()
    confirmRemoveKey.value = false
    await load()
    pushToast({ kind: 'info', title: 'Muse key removed', body: 'AI features now use demo replies.' })
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; message?: string }
    error.value = err.data?.detail || err.message || 'Could not remove the key.'
  } finally {
    busy.value = false
  }
}

async function askAssistant() {
  setupError.value = ''
  setupBusy.value = true
  try {
    setupResult.value = await aiSetup(dbChoice.value, setupMessage.value.trim())
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; message?: string }
    setupError.value = err.data?.detail || err.message || 'The setup assistant could not answer right now.'
  } finally {
    setupBusy.value = false
  }
}

async function refreshRunState() {
  try {
    runState.value = await setupStatus()
    if (runState.value.setup) setup.value = runState.value.setup
    if (!runState.value.running) stopPolling()
  } catch {
    // Keep the last known state; the next poll retries.
  }
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(refreshRunState, 1500)
}

async function startSetup() {
  runError.value = ''
  try {
    runState.value = await runSetup(dbChoice.value)
    if (runState.value.running) startPolling()
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; message?: string }
    runError.value = err.data?.detail || err.message || 'Setup could not start.'
  }
}

onBeforeUnmount(stopPolling)

function useStandard() {
  if (standardCutoffs.value) form.value.cutoffs = { ...standardCutoffs.value }
}
</script>

<template>
  <main class="page page-narrow settings-page">
    <h1>Settings</h1>
    <p class="lede">Your control panel for this copy of WhatsGene. Add your Muse AI key once, then let Muse guide the hard parts — setting up the local BLAST database and explaining workflow results. No files to edit, nothing to restart.</p>

    <p v-if="loading" class="hint">Loading your settings…</p>

    <form v-else @submit.prevent="save">
      <div class="prog-tabs-block">
        <p class="prog-tabs-label">Settings theme</p>
        <div class="prog-tabs" role="tablist" aria-label="Settings theme">
          <button
            v-for="t in tabs"
            :key="t.id"
            type="button"
            role="tab"
            :aria-selected="activeTab === t.id"
            :class="['prog-tab', { 'prog-tab-active': activeTab === t.id }]"
            @click="activeTab = t.id"
          >{{ t.label }}</button>
        </div>
      </div>

      <div v-show="activeTab === 'ai'">
      <fieldset>
        <legend>Muse AI (Meta model)</legend>
        <p class="hint muse-status">
          <span v-if="keySet">A key is saved. It stays hidden unless you press the eye button. Muse now reads your questions, writes each verdict, and answers Ask on every workflow.</span>
          <span v-else>No key saved yet. Without one, AI features answer with a scripted demo so you can see how they will work.</span>
        </p>
        <label for="muse-key">Muse API key</label>
        <!-- Masked, and kept out of browser password managers: an API key is not a site password. -->
        <div class="key-field">
          <input id="muse-key" v-model="apiKeyInput" :type="showKey ? 'text' : 'password'" name="muse-api-key"
                 autocomplete="off" autocapitalize="off" spellcheck="false"
                 data-lpignore="true" data-1p-ignore="true" data-bwignore="true" data-form-type="other"
                 :placeholder="keySet ? '****************' : 'Paste your Muse API key'">
          <div class="key-actions">
            <button type="button" class="key-btn" :aria-label="showKey ? 'Hide key' : 'Show key'" :title="showKey ? 'Hide key' : 'Show key'"
                    :disabled="!keySet && !apiKeyInput" @click="toggleKey">
              <svg v-if="!showKey" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></svg>
              <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3l18 18" /><path d="M10.6 5.1A10.7 10.7 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 4.1M6.6 6.6A17 17 0 0 0 2 12s3.5 7 10 7a10 10 0 0 0 5.4-1.6" /><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" /></svg>
            </button>
            <button type="button" class="key-btn key-btn-danger" :aria-label="keySet ? 'Delete saved key' : 'Clear'" :title="keySet ? 'Delete saved key' : 'Clear'"
                    :disabled="busy || (!keySet && !apiKeyInput)" @click="deleteKey">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M19 6l-1 14H6L5 6" /><path d="M10 11v6M14 11v6" /></svg>
            </button>
          </div>
        </div>
        <label for="muse-url">Endpoint (optional)</label>
        <input id="muse-url" v-model="form.muse_base_url" type="text" placeholder="Leave blank to use this install's endpoint">
        <p class="hint">The key is stored only in this machine's local database, and only your own account can show it. Muse explains and guides; WhatsGene code still runs every search, build, and check. Works with Muse Spark (Meta Model API) or Muse Spark Open.</p>
      </fieldset>
      </div>

      <div v-show="activeTab === 'setup'">
      <fieldset>
        <legend>Set up local BLAST</legend>
        <p class="hint" style="margin-top: 4px;">Press Run setup and WhatsGene does the work: checks BLAST+, downloads the database files (about 170 MB), builds the database, and proves it with a known accession before trusting it. Muse can explain the plan; code runs every step.</p>
        <label for="db-choice">Database to set up</label>
        <select id="db-choice" v-model="dbChoice" class="select">
          <option v-for="(o, key) in databaseOptions" :key="key" :value="key">{{ o.label }}</option>
        </select>
        <div class="submit-row">
          <button class="btn" type="button" :disabled="runState?.running" @click="startSetup">{{ runState?.running ? 'Setting up…' : 'Run setup now' }}</button>
          <span v-if="runState && runState.status === 'done'" class="status-pill status-done">Setup done</span>
          <span v-else-if="runState && runState.status === 'failed'" class="status-pill status-failed">Setup stopped</span>
        </div>
        <p v-if="runError" class="error">{{ runError }}</p>
        <div v-if="runState && runState.status !== 'idle'" class="assistant-result">
          <ol class="step-list">
            <li v-for="s in runState.steps" :key="s.id">
              <span class="step-mark" :class="`mark-${s.status}`">{{ stepMarks[s.status] || s.status }}</span>
              <span><strong>{{ s.title }}</strong><span v-if="s.detail"> — {{ s.detail }}</span></span>
            </li>
          </ol>
          <ol v-if="runState.log.length" class="setup-log mono">
            <li v-for="(line, i) in runState.log" :key="i">{{ line }}</li>
          </ol>
          <p v-if="runState.status === 'done'" class="hint">Local search is ready. <NuxtLink to="/new">Run your first search →</NuxtLink></p>
          <p v-if="runState.status === 'failed'" class="hint">Read the last step above for the real error, fix it, then press Run setup again. Nothing is faked: a step only says Done after the code proves it.</p>
        </div>
        <label for="setup-msg">Tell Muse about your work (optional)</label>
        <input id="setup-msg" v-model="setupMessage" type="text" placeholder="e.g. I search worm proteins and want fast private runs">
        <div class="submit-row">
          <button class="btn btn-secondary" type="button" :disabled="setupBusy" @click="askAssistant">{{ setupBusy ? 'Asking…' : 'Ask Muse to explain the plan' }}</button>
        </div>
        <p v-if="setupError" class="error">{{ setupError }}</p>
        <div v-if="setupResult" class="assistant-result">
          <p class="assistant-mode">{{ setupResult.mode === 'live' ? 'Live Muse answer — using your key' : 'Demo answer — add your Muse key for live guidance' }}</p>
          <ol class="step-list">
            <li v-for="s in setupResult.plan.steps" :key="s.id">
              <span class="step-mark" :class="`mark-${s.status}`">{{ stepMarks[s.status] || s.status }}</span>
              <span><strong>{{ s.title }}</strong> — {{ s.detail }}</span>
            </li>
          </ol>
          <p class="assistant-reply">{{ setupResult.reply }}</p>
        </div>
      </fieldset>

      <fieldset v-if="setup">
        <legend>This machine</legend>
        <dl class="cutoff-list">
          <div><dt>BLAST+ programs</dt><dd>{{ setup.blast_plus_installed ? 'Installed and ready' : 'Not found — local searches cannot run yet' }}</dd></div>
          <div><dt>Local database</dt><dd>{{ setup.local_db_ready ? `Ready at ${setup.blastdb_path}` : 'Not ready — ask Muse above to plan the setup' }}</dd></div>
          <div><dt>Server default</dt><dd>{{ setup.search_backend }}</dd></div>
        </dl>
      </fieldset>
      </div>

      <div v-show="activeTab === 'lab'">
      <fieldset>
        <legend>Your lab</legend>
        <label for="lab-name">Lab or team name (optional)</label>
        <input id="lab-name" v-model="form.lab_name" type="text" placeholder="e.g. Parasitology Lab, UTM">
        <p class="hint">Shown at the top of the page, so a shared screen is easy to recognise.</p>
        <label for="default-organism">Organism you search most (optional)</label>
        <input id="default-organism" v-model="form.default_organism" type="text" placeholder="e.g. nematodes — or C. elegans, human, E. coli">
        <p class="hint">Pre-filled as the target on the New search page. You can still change it for any single search.</p>
      </fieldset>
      </div>

      <div v-show="activeTab === 'judging'">
      <fieldset>
        <legend>Where searches run</legend>
        <label for="default-backend">Usual search location</label>
        <select id="default-backend" v-model="form.default_backend" class="select">
          <option v-for="o in backendOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
        <p class="hint">Local BLAST keeps your sequences on this machine. NCBI sends them to NCBI's public service and waits in its queue.</p>
      </fieldset>

      <fieldset>
        <legend>How wide to cast the net</legend>
        <div class="preset-list" role="radiogroup" aria-label="Strictness">
          <label
            v-for="key in strictnessOrder"
            :key="key"
            class="preset-option"
            :class="{ 'preset-selected': form.strictness === key }"
          >
            <input v-model="form.strictness" type="radio" name="strictness" :value="key">
            <span class="preset-text">
              <span class="preset-label">{{ presets[key]?.label || key }}</span>
              <span class="preset-help">{{ presets[key]?.help }}</span>
            </span>
          </label>
        </div>
        <p class="hint">This changes only how many hits are collected. How hits are judged is set below.</p>
      </fieldset>

      <fieldset>
        <legend>How hits are judged</legend>
        <div class="preset-list" role="radiogroup" aria-label="Cut-off mode">
          <label class="preset-option" :class="{ 'preset-selected': form.cutoff_mode === 'standard' }">
            <input v-model="form.cutoff_mode" type="radio" name="cutoff-mode" value="standard">
            <span class="preset-text">
              <span class="preset-label">Course cut-offs (recommended)</span>
              <span class="preset-help">Strong: E ≤ 1×10^-5 and coverage ≥ 70%. Borderline up to E ≤ 0.01, coverage ≥ 30%. The same ruler as the course and every other install.</span>
            </span>
          </label>
          <label class="preset-option" :class="{ 'preset-selected': form.cutoff_mode === 'custom' }">
            <input v-model="form.cutoff_mode" type="radio" name="cutoff-mode" value="custom">
            <span class="preset-text">
              <span class="preset-label">My own cut-offs (advanced)</span>
              <span class="preset-help">Your numbers judge your hits. Every workflow records the exact cut-offs it used, so results stay honest and reproducible.</span>
            </span>
          </label>
        </div>
        <div v-if="form.cutoff_mode === 'custom'" class="cutoff-grid">
          <label>Strong: max E-value<input v-model.number="form.cutoffs.strong_max_evalue" type="text" inputmode="decimal"></label>
          <label>Strong: min coverage %<input v-model.number="form.cutoffs.strong_min_coverage" type="text" inputmode="decimal"></label>
          <label>Borderline: max E-value<input v-model.number="form.cutoffs.borderline_max_evalue" type="text" inputmode="decimal"></label>
          <label>Borderline: min coverage %<input v-model.number="form.cutoffs.borderline_min_coverage" type="text" inputmode="decimal"></label>
          <button class="btn btn-secondary btn-small" type="button" @click="useStandard">Reset to course cut-offs</button>
        </div>
        <p class="hint">Warning: custom cut-offs change what “strong” means in your results. Verification (reciprocal best hit) still uses the standard gates, and finished workflows never change when you edit these.</p>
      </fieldset>
      </div>

      <div v-show="activeTab === 'accounts'">
        <AccountsPanel />
      </div>

      <div v-show="activeTab !== 'accounts'" class="submit-row">
        <button class="btn" type="submit" :disabled="busy">{{ busy ? 'Saving…' : 'Save settings' }}</button>
        <NuxtLink to="/new" class="btn btn-secondary">New search</NuxtLink>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
    </form>
    <ConfirmDialog
      :open="confirmRemoveKey"
      title="Delete the saved Muse key?"
      confirm-label="Delete key"
      danger
      :busy="busy"
      busy-label="Deleting…"
      @confirm="removeKey"
      @cancel="confirmRemoveKey = false"
    >
      <p>Searches keep working with code-written summaries and answers. You can paste a key again at any time.</p>
    </ConfirmDialog>
  </main>
</template>

<style scoped>
.preset-list { display: grid; gap: 8px; margin-top: 10px; }
.preset-option {
  display: flex; gap: 10px; align-items: flex-start;
  margin: 0; padding: 12px 14px; cursor: pointer;
  background: var(--surface); border: 1px solid var(--line-strong); border-radius: 8px;
}
.preset-option input { margin-top: 3px; }
.preset-selected { border-color: var(--accent); background: var(--panel); }
.preset-text { display: grid; gap: 2px; }
.preset-label { font-weight: 650; color: var(--ink); }
.preset-help { font-weight: 400; font-size: 13px; line-height: 1.5; color: var(--muted); }
.cutoff-list { margin: 10px 0 0; display: grid; gap: 8px; }
.cutoff-list div { display: flex; gap: 12px; justify-content: space-between; }
.cutoff-list dt { font-weight: 600; font-size: 13.5px; color: var(--ink-2); }
.cutoff-list dd { margin: 0; font-size: 13.5px; color: var(--ink); text-align: right; }
.cutoff-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 16px; margin-top: 10px; }
.setup-log { margin: 10px 0 0; padding-left: 18px; font-size: 12px; color: var(--muted); }
.submit-row { display: flex; gap: 12px; margin-top: 20px; align-items: center; flex-wrap: wrap; }
.muse-status { margin-top: 10px; }
.key-field { position: relative; }
.key-field input { padding-right: 84px; }
.key-actions { position: absolute; top: 0; right: 6px; bottom: 0; display: flex; align-items: center; gap: 2px; }
.key-btn {
  display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px;
  border: 0; border-radius: 6px; background: transparent; color: var(--muted); cursor: pointer;
}
.key-btn:hover:not(:disabled) { background: var(--panel); color: var(--ink); }
.key-btn-danger:hover:not(:disabled) { color: var(--error); }
.key-btn:disabled { opacity: 0.35; cursor: default; }
.assistant-result { margin-top: 14px; }
.assistant-mode { font-size: 13px; font-weight: 650; color: var(--ink-2); margin: 0 0 8px; }
.step-list { margin: 0 0 10px; padding-left: 18px; display: grid; gap: 8px; font-size: 13.5px; line-height: 1.5; }
.step-mark { font-weight: 650; margin-right: 6px; }
.mark-done { color: var(--accent-strong); }
.mark-needed, .mark-demo_only { color: var(--error); }
.assistant-reply { white-space: pre-wrap; font-size: 14px; line-height: 1.6; color: var(--ink); background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; }
</style>
