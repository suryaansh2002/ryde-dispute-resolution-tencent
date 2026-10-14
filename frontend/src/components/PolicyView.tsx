import type { PolicyTag } from '../types/api'
import { api } from '../lib/api'
import { useApi } from '../lib/useApi'
import { Icon } from './Icon'

/* A cited policy: the plain summary first, then the clause itself, formatted. */

export const POLICY_INFO: Record<string, [string, string]> = {
  'POL-01': ['General principles', 'Every decision rests on evidence, not on who argues harder. Both sides are held to the same standard, and whoever makes a claim has to support it.'],
  'POL-02': ['Route deviation', 'If a trip was much longer than the fastest route and nothing on record explains it, the fare for the extra distance is refunded: nothing under 10% longer, half between 10% and 25%, all of it above 25%. Roadworks or a closure near the route, or a detour the rider asked for, explain a detour.'],
  'POL-03': ['No-show charge', 'The $4.50 no-show fee stands only if the driver reached the pickup point (within 100 m), waited the grace period and tried to reach the rider. Otherwise it is waived.'],
  'POL-04': ['Cleaning and damage fees', 'A driver needs at least one photo. The fee follows what the photo shows: $40 for a spill or crumbs, $120 for mud, dirt or stains, $200 for vomit. Without a photo, the claim is declined and can be sent again.'],
  'POL-05': ['Safety incidents', 'Safety reports aren’t decided under this policy. They go straight to a person.'],
  'POL-06': ['Evidence standard', 'When the evidence a claim needs is missing, the claim is declined, not denied, and can be refiled with that evidence.'],
  'POL-07': ['Remedies and caps', 'Refunds can’t exceed the fare, cleaning fees can’t exceed $200, and a waiver returns exactly the fee charged.'],
  'POL-08': ['When a person decides', 'A person decides when confidence is low, the fee is $120 or more, either party has filed three or more disputes in 30 days, or a rule check fails.'],
}

const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
const inline = (s: string) =>
  esc(s)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*(?!\s)(.+?)\*(?!\*)/g, '$1<em>$2</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')

/** The policy corpus is our own markdown: paragraphs, bullet lists and pipe tables.
 * Everything is escaped before the few inline marks are applied. */
function mdToHtml(src: string) {
  return src
    .trim()
    .split(/\n\s*\n/)
    .map((b) => {
      const lines = b.split('\n').filter((l) => l.trim())
      if (lines.every((l) => l.trim().startsWith('|'))) {
        const rows = lines
          .filter((l) => !/^\|\s*-/.test(l.trim()))
          .map((l) => l.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim()))
        const [head, ...body] = rows
        return `<div class="md-table"><table><thead><tr>${head.map((h) => `<th>${inline(h)}</th>`).join('')}</tr></thead><tbody>${body
          .map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join('')}</tr>`)
          .join('')}</tbody></table></div>`
      }
      if (lines.every((l) => /^\s*[-*] /.test(l) || /^\s{2,}/.test(l))) {
        return `<ul>${lines
          .filter((l) => /^\s*[-*] /.test(l))
          .map((l) => `<li>${inline(l.replace(/^\s*[-*] /, ''))}</li>`)
          .join('')}</ul>`
      }
      return `<p>${inline(lines.join(' '))}</p>`
    })
    .join('')
}

const clauseBody = (excerpt: string) => excerpt.replace(/^§\d+\.[^—]*—\s*/, '')

function sourceOf(text: string): [string, string] | null {
  if (/not Ryde-sourced|our own/i.test(text)) return ['neutral', 'Includes our own rules']
  if (/real, sourced|help\.rydesharing|Terms of Use/i.test(text)) return ['good', 'Ryde’s published figures']
  return null
}

function Clause({ c, cited }: { c: PolicyTag; cited?: boolean }) {
  const src = sourceOf(c.excerpt)
  return (
    <div className={`clause${cited ? ' cited' : ''}`}>
      <div className="clause-head">
        <span className="mono">{c.chunk_id}</span>
        {cited && <span>The clause cited</span>}
        {src && <span className={`pill ${src[0]}`}>{src[1]}</span>}
      </div>
      <div className="md" dangerouslySetInnerHTML={{ __html: mdToHtml(clauseBody(c.excerpt)) }} />
    </div>
  )
}

export function PolicyView({ refId }: { refId: string }) {
  const pid = refId.slice(0, 6)
  const { data: clauses = [], loading } = useApi(`policy:${pid}`, () => api.policy(pid))
  const cited = clauses.find((c) => c.chunk_id === refId)
  const [title, summary] = POLICY_INFO[pid] ?? [pid, '']
  const others = clauses.filter((c) => c !== cited)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <h3 style={{ fontSize: 22, letterSpacing: '-0.02em' }}>{title}</h3>
        <p style={{ marginTop: 8, fontSize: 16, color: 'var(--ink-2)' }}>{summary}</p>
      </div>
      {loading && <p className="small muted">Loading the policy text…</p>}
      {cited && <Clause c={cited} cited />}
      {!cited && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {clauses.map((c) => <Clause key={c.chunk_id} c={c} />)}
        </div>
      )}
      {cited && others.length > 0 && (
        <details className="more">
          <summary>
            <Icon name="right" size={14} />
            The rest of this section ({others.length} clause{others.length === 1 ? '' : 's'})
          </summary>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 12 }}>
            {others.map((c) => <Clause key={c.chunk_id} c={c} />)}
          </div>
        </details>
      )}
    </div>
  )
}
