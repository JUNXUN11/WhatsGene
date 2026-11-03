<script setup lang="ts">
import type { LibraryFile, LibraryResponse } from '~/composables/useApi'

definePageMeta({ middleware: 'auth' })

const { getLibrary, sortLibrary, buildDatabase, buildFromTaxon, libraryQueryText } = useApi()
const { push: pushToast } = useToasts()
const router = useRouter()

const data = ref<LibraryResponse | null>(null)
const loading = ref(true)
const error = ref('')
const busy = ref(false)
const choices = ref<Record<string, string>>({})
const included = ref<Record<string, boolean>>({})
const buildNames = ref<Record<string, string>>({})
const builtDb = ref('')
const taxonOrganism = ref('')
const taxonName = ref('')

const categories = [
  { value: 'query', label: 'Search query' },
  { value: 'database_source', label: 'Database source' },
  { value: 'document', label: 'Document' },
  { value: 'result', label: 'Old result' },
  { value: 'unknown', label: 'Unknown — check later' },
]
const categoryLabel = (value: string) => categories.find(c => c.value === value)?.label || value

const includedCount = computed(() =>
  (data.value?.inbox || []).filter(f => included.value[f.path]).length)

const libraryGroups = computed(() => {
  const groups: { value: string; label: string; files: LibraryFile[] }[] = []
  for (const c of categories) {
    const files = (data.value?.library || []).filter(f => f.category === c.value)
    if (files.length) groups.push({ ...c, files })
  }
  return groups
})

function slug(name: string): string {
  let s = name.replace(/\.(gz|fa|fasta|faa|fna|fas|fsa|txt)$/gi, '')
    .toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
  if (/^[0-9]/.test(s)) s = `db_${s}`
  return (s || 'custom_db').slice(0, 40)
}

function formatSize(bytes: number): string {
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`
  if (bytes >= 1_000) return `${(bytes / 1_000).toFixed(1)} KB`
  return `${bytes} B`
}

function isOverridden(f: LibraryFile): boolean {
  return (choices.value[f.path] || f.category_proposed) !== f.category_proposed
}

async function load() {
  loading.value = true
  try {
    data.value = await getLibrary()
    const inboxPaths = new Set(data.value.inbox.map(f => f.path))
    const libraryPaths = new Set(data.value.library.map(f => f.path))
    for (const key of Object.keys(choices.value)) if (!inboxPaths.has(key)) delete choices.value[key]
    for (const key of Object.keys(included.value)) if (!inboxPaths.has(key)) delete included.value[key]
    for (const key of Object.keys(buildNames.value)) if (!libraryPaths.has(key)) delete buildNames.value[key]
    for (const f of data.value.inbox) {
      if (!(f.path in choices.value)) choices.value[f.path] = f.category_proposed
      if (!(f.path in included.value)) included.value[f.path] = true
    }
    for (const f of data.value.library) {
      if (!(f.path in buildNames.value)) buildNames.value[f.path] = slug(f.name)
    }
    error.value = ''
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; message?: string }
    error.value = err.data?.detail || err.message || 'Could not read the inbox. Is the backend running on port 8000?'
  } finally {
    loading.value = false
  }
}

onMounted(load)

function setAll(value: boolean) {
  for (const f of data.value?.inbox || []) included.value[f.path] = value
}

async function sortConfirmed() {
  if (!data.value) return
  const items = data.value.inbox
    .filter(f => included.value[f.path])
    .map(f => ({ path: f.path, category: choices.value[f.path] || f.category_proposed }))
  if (!items.length) { error.value = 'Tick at least one file to sort.'; return }
  busy.value = true
  try {
    const res = await sortLibrary(items)
    builtDb.value = ''
    pushToast({ kind: 'info', title: `Sorted ${res.sorted.length} file(s)`, body: 'Originals stay in the inbox. Copies are in your library.' })
    await load()
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; message?: string }
    error.value = err.data?.detail || err.message || 'Sorting failed.'
  } finally {
    busy.value = false
  }
}

async function useAsSearch(file: LibraryFile) {
  busy.value = true
  try {
    const text = await libraryQueryText(file.root, file.path)
    await router.push({ path: '/new', query: { sequence: text } })
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; message?: string }
    error.value = err.data?.detail || err.message || 'Could not read that sequence.'
    busy.value = false
  }
}

async function buildDb(file: LibraryFile) {
  const name = (buildNames.value[file.path] || slug(file.name)).trim()
  busy.value = true
  try {
    const entry = await buildDatabase(file.root, file.path, name)
    builtDb.value = entry.name
    pushToast({ kind: 'info', title: `Database ${entry.name} built`, body: `${entry.sequence_count ?? ''} sequences. Pick it under Local database on New search.` })
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; message?: string }
    error.value = err.data?.detail || err.message || 'Database build failed.'
  } finally {
    busy.value = false
  }
}

async function buildTaxon() {
  if (!taxonOrganism.value.trim() || !taxonName.value.trim()) {
    error.value = 'Give an organism and a database name first.'
    return
  }
  busy.value = true
  try {
    const entry = await buildFromTaxon(taxonOrganism.value.trim(), taxonName.value.trim())
    builtDb.value = entry.name
    pushToast({ kind: 'info', title: `Database ${entry.name} built`, body: `${entry.sequence_count ?? ''} sequences from your SwissProt copy.` })
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; message?: string }
    error.value = err.data?.detail || err.message || 'Taxon database build failed.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="page">
    <div class="page-head">
      <h1>Library</h1>
      <button class="btn btn-secondary" :disabled="loading" @click="load">Rescan inbox</button>
    </div>
    <p class="lede">Drop any files into the inbox folder. WhatsGene reads each one and proposes what it is. You confirm, then sorted copies go to your library — originals are never moved or deleted.</p>

    <p v-if="loading" class="hint">Reading your inbox…</p>
    <p v-if="error" class="error">{{ error }}</p>

    <template v-if="data && !loading">
      <section class="card">
        <div class="lib-head">
          <h2>Inbox ({{ data.inbox.length }})</h2>
          <div v-if="data.inbox.length" class="lib-bulk">
            <button type="button" class="quiet-link" @click="setAll(true)">Select all</button>
            <span aria-hidden="true">·</span>
            <button type="button" class="quiet-link" @click="setAll(false)">Select none</button>
          </div>
        </div>
        <p class="hint">Drop files here: <span class="mono">{{ data.inbox_dir }}</span></p>
        <p v-if="!data.inbox.length" class="hint">Inbox is empty. Copy sequence files, notes, anything — order does not matter.</p>
        <div v-for="f in data.inbox" :key="f.path" class="lib-row">
          <label class="lib-include">
            <input v-model="included[f.path]" type="checkbox">
            <span class="sr-only">Include {{ f.name }}</span>
          </label>
          <div class="lib-main">
            <p class="lib-name">
              {{ f.name }}
              <span class="status-pill" :class="f.confidence === 'high' ? 'status-done' : (f.confidence === 'medium' ? 'status-queued' : '')">{{ f.confidence }}</span>
              <span v-if="isOverridden(f)" class="status-pill status-queued">changed</span>
            </p>
            <p class="lib-meta">{{ f.kind }} · {{ formatSize(f.size_bytes) }}<span v-if="f.sequence_count"> · {{ f.sequence_count }} sequence(s) · {{ f.sequence_type || 'type unknown' }}</span></p>
            <p class="lib-reason">{{ f.reason }}</p>
          </div>
          <div class="lib-choice">
            <label class="lib-choice-label" :for="`choice-${f.path}`">Sort as</label>
            <select :id="`choice-${f.path}`" v-model="choices[f.path]" class="select lib-select">
              <option v-for="c in categories" :key="c.value" :value="c.value">{{ c.label }}</option>
            </select>
          </div>
        </div>
        <div v-if="data.inbox.length" class="submit-row">
          <button class="btn" :disabled="busy || !includedCount" @click="sortConfirmed">
            {{ busy ? 'Working…' : `Sort ${includedCount} confirmed file${includedCount === 1 ? '' : 's'}` }}
          </button>
        </div>
      </section>

      <section class="card">
        <h2>Your library ({{ data.library.length }})</h2>
        <p class="hint">Stored at <span class="mono">{{ data.library_dir }}</span>. Search a query file, or build a small database from a source file — type a short lowercase name first.</p>
        <p v-if="!data.library.length" class="hint">Nothing sorted yet.</p>
        <div v-for="group in libraryGroups" :key="group.value" class="lib-group">
          <h3>{{ group.label }} ({{ group.files.length }})</h3>
          <div v-for="f in group.files" :key="f.path" class="lib-row">
            <div class="lib-main">
              <p class="lib-name">{{ f.name }}</p>
              <p class="lib-meta">{{ f.kind }} · {{ formatSize(f.size_bytes) }}<span v-if="f.sequence_count"> · {{ f.sequence_count }} sequence(s) · {{ f.sequence_type || 'type unknown' }}</span></p>
              <div v-if="f.can_search || f.can_build_database" class="lib-actions">
                <button v-if="f.can_search" class="btn btn-secondary btn-small" :disabled="busy" @click="useAsSearch(f)">Use as search</button>
                <template v-if="f.can_build_database">
                  <label class="lib-dbname-label" :for="`dbname-${f.path}`">Database name</label>
                  <input :id="`dbname-${f.path}`" v-model="buildNames[f.path]" class="lib-dbname mono" maxlength="40">
                  <button class="btn btn-secondary btn-small" :disabled="busy" @click="buildDb(f)">Build database</button>
                </template>
              </div>
            </div>
          </div>
        </div>
        <p v-if="builtDb" class="hint lib-built">
          Database <span class="mono">{{ builtDb }}</span> is ready.
          <NuxtLink :to="{ path: '/new', query: { database: builtDb } }">Open New search with it →</NuxtLink>
        </p>
      </section>

      <section class="card">
        <h2>Small database from one species</h2>
        <p class="hint">Build a tiny database from just one organism in your SwissProt copy, instead of searching all of it. Takes a minute or two on a first build.</p>
        <label for="taxon-org">Organism or group</label>
        <input id="taxon-org" v-model="taxonOrganism" type="text" placeholder="e.g. C. elegans — or nematodes, human">
        <label for="taxon-name">New database name (lowercase, 3–40 characters)</label>
        <input id="taxon-name" v-model="taxonName" type="text" class="mono" placeholder="e.g. celegans_proteins">
        <div class="submit-row">
          <button class="btn" :disabled="busy" @click="buildTaxon">{{ busy ? 'Building…' : 'Build species database' }}</button>
        </div>
      </section>
    </template>
  </main>
</template>

<style scoped>
.lib-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.lib-head h2 { margin: 0; }
.lib-bulk { display: flex; align-items: center; gap: 6px; font-size: 13.5px; color: var(--muted); }
.lib-bulk .quiet-link { background: none; border: 0; padding: 0; cursor: pointer; font: inherit; color: var(--accent); }
.lib-row { display: flex; gap: 12px; align-items: flex-start; padding: 12px 0; border-top: 1px solid var(--line); }
.lib-row:first-of-type { border-top: none; }
.lib-main { flex: 1; min-width: 0; }
.lib-name { font-weight: 650; margin: 0; display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.lib-meta, .lib-reason { margin: 2px 0 0; font-size: 13.5px; color: var(--muted); }
.lib-choice { flex: none; display: grid; gap: 4px; }
.lib-choice-label { font-size: 12px; font-weight: 650; color: var(--muted); margin: 0; }
.lib-select { min-width: 180px; }
.lib-group h3 { margin: 14px 0 2px; font-size: 14px; }
.lib-group:first-of-type h3 { margin-top: 4px; }
.lib-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 8px; }
.lib-dbname { width: 160px; }
.lib-dbname-label { font-size: 12px; font-weight: 650; color: var(--muted); margin: 0; }
.lib-built { margin-top: 12px; }
.lib-include { padding-top: 4px; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.submit-row { display: flex; gap: 10px; margin-top: 14px; }
@media (max-width: 640px) {
  .lib-row { flex-direction: column; }
  .lib-include { display: none; }
  .lib-choice { width: 100%; }
  .lib-select { width: 100%; }
  .lib-dbname { flex: 1; min-width: 140px; }
}
</style>
