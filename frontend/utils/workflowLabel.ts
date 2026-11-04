import type { Job } from '~/types/job'

// Human labels for a workflow, so lists show what was searched instead of
// the random WG-… ID. Built from the user's own input; never invented.

const ACCESSION_LIKE = /^[A-Za-z0-9_.]+(?::\d+-\d+)?$/
// Same rule as the backend (app/validate.py): a FASTA pasted without ">".
const HEADERLESS_FIRST = /[0-9=|:;,()[\]]/
const SEQUENCE_ONLY = /^[A-Za-z*-]+$/

/** "sp|P01308|INS_HUMAN Insulin OS=Homo sapiens OX=9606 GN=INS" -> "P01308 Insulin (Homo sapiens)". */
function cleanHeader(header: string): string {
  const [first = '', ...rest] = header.trim().split(/\s+/)
  const parts = first.split('|')
  const id = parts.length >= 2 && parts[1] ? parts[1] : first
  const desc = rest.join(' ')
  const organism = desc.match(/\bOS=(.+?)(?=\s+[A-Z]{2}=|$)/)?.[1]
  const name = desc.replace(/\s+[A-Z]{2}=.*$/, '').trim()
  const label = [id, name].filter(Boolean).join(' ') + (organism ? ` (${organism})` : '')
  return label.length > 70 ? `${label.slice(0, 70)}…` : label || 'FASTA sequence'
}

/** The submitted input, short: an accession, a FASTA header, or a sequence preview. */
export function workflowInput(job: Pick<Job, 'raw_input' | 'accession' | 'detected_type' | 'query_length'>): string {
  const raw = (job.raw_input || '').trim()
  if (!raw) return job.accession || 'sequence'
  const lines = raw.split(/\r?\n/).map(l => l.trim()).filter(Boolean)
  if (lines[0].startsWith('>')) return cleanHeader(lines[0].slice(1))
  if (lines.length >= 2 && HEADERLESS_FIRST.test(lines[0]) && SEQUENCE_ONLY.test(lines.slice(1).join(''))) {
    return cleanHeader(lines[0])
  }
  if (ACCESSION_LIKE.test(raw) && raw.length <= 30 && /\d/.test(raw)) return raw.toUpperCase()
  const seq = lines.join('').replace(/\s+/g, '').toUpperCase()
  const length = job.query_length || seq.length
  const unit = job.detected_type === 'protein' ? 'aa' : job.detected_type === 'dna' ? 'bp' : 'residues'
  const preview = seq.length > 14 ? `${seq.slice(0, 14)}…` : seq
  return `${preview} (${length} ${unit})`
}

/** The headline: the user's question, else what they searched. */
export function workflowTitle(job: Pick<Job, 'question' | 'raw_input' | 'accession' | 'detected_type' | 'query_length'>): string {
  const question = (job.question || '').trim()
  return question || `Search ${workflowInput(job)}`
}

/** "3 Nov, 16:53" in the viewer's locale, or '' when unknown. */
export function workflowWhen(job: Pick<Job, 'created_at'>): string {
  const when = job.created_at ? new Date(job.created_at) : null
  if (!when || Number.isNaN(when.getTime())) return ''
  return when.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
