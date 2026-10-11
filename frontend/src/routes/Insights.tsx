import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { StateBadge } from '../components/StateBadge'
import { api } from '../lib/api'
import { CATEGORY_LABEL, ago, duration, money, outcomeLabel, remedyLabel } from '../lib/format'
import type { Category, GoldenReport, GoldenResult, Stats } from '../types/api'

function expectedText(e: GoldenResult['expected']): string {
  if (e.outcome === 'escalated_to_l2') return 'Straight to a person (safety)'
  const r = e.remedy
  if (!r || r.type === 'no_action') return outcomeLabel(e.outcome)
  if (r.merit_fraction != null) return `${outcomeLabel(e.outcome)} · refund, merit ${r.merit_fraction}`
  return `${outcomeLabel(e.outcome)} · ${remedyLabel(r.type)} ${money(r.amount)}`
}

function actualText(a: GoldenResult['actual']): string {
  if (a.error) return 'Pipeline error'
  if (a.state === 'safety_bypassed') return 'Straight to a person (safety)'
  if (!a.outcome) return a.state === 'declined_insufficient_evidence' ? 'Declined, insufficient evidence' : (a.state ?? '—')
  const r = a.remedy
  return `${outcomeLabel(a.outcome)}${r && r.type !== 'no_action' ? ` · ${remedyLabel(r.type)} ${money(r.amount)}` : ''}`
}

/** One labelled bar per category: passed out of run, drawn to a shared 0–100% scale. */
function CategoryBars({ report }: { report: GoldenReport }) {
  const rows = (Object.entries(report.by_category) as [Category, { total: number; run: number; passed: number }][])
  return (
    <div className="stack" style={{ gap: 12 }}>
      {rows.map(([cat, b]) => {
        const pct = b.run ? (b.passed / b.run) * 100 : 0
        return (
          <div key={cat} className="stack" style={{ gap: 4 }}>
            <div className="row between small">
              <span style={{ fontWeight: 600 }}>{CATEGORY_LABEL[cat]}</span>
              <span className="mono muted">
                {b.passed}/{b.run}
                {b.run < b.total && <span className="faint"> ({b.total - b.run} not run)</span>}
              </span>
            </div>
            <div className="meter-track" role="img" aria-label={`${CATEGORY_LABEL[cat]}: ${b.passed} of ${b.run} passed`}>
              <div className="meter-fill" style={{ width: `${pct}%` }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function Insights() {
  const [report, setReport] = useState<GoldenReport | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | 'failed'>('all')

  const load = useCallback(() => {
    api.golden().then(setReport, (e: Error) => setError(e.message))
    api.stats().then(setStats, () => setStats(null))
  }, [])
  useEffect(load, [load])

  const running = report?.status.running ?? false
  useEffect(() => {
    if (!running) return
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [running, load])

  const start = async () => {
    setError(null)
    try {
      await api.startGolden()
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const pass = report && report.run ? Math.round((report.passed / report.run) * 100) : null
  const cases = (report?.cases ?? []).filter((c) => filter === 'all' || (c.result && !c.result.passed))
  const lastRun = report?.cases.map((c) => c.result?.ran_at).filter(Boolean).sort().pop()

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="page-head" style={{ marginBottom: 0 }}>
        <div className="stack" style={{ gap: 6 }}>
          <h1>Does it get it right?</h1>
          <p className="lead">
            {report?.total ?? 22} labelled cases, each with an answer written from the synthetic data’s ground truth
            (the real detour, the real GPS, the real mess). The golden run files every one through the full pipeline
            with real model calls and checks the verdict against the label.
          </p>
        </div>
        <div className="stack" style={{ gap: 6, alignItems: 'flex-end' }}>
          <button className="btn-primary" onClick={start} disabled={running}>
            {running ? (
              <>
                <span className="spinner" /> Running {report?.status.done}/{report?.status.total}
              </>
            ) : (
              'Run the golden cases'
            )}
          </button>
          <span className="tiny faint">{lastRun ? `last run ${ago(lastRun)}` : 'not run yet'} · takes a few minutes</span>
        </div>
      </div>
      {error && <p className="error-text">{error}</p>}

      {running && report && (
        <div className="meter-track" aria-label="Run progress">
          <div className="meter-fill" style={{ width: `${(report.status.done / Math.max(report.status.total, 1)) * 100}%` }} />
        </div>
      )}

      <section className="panel metrics">
        <div className="metric">
          <span className="metric-value">{pass == null ? '—' : `${pass}%`}</span>
          <span className="small muted">
            verdicts match the label{report?.run ? ` (${report.passed} of ${report.run})` : ''}
          </span>
        </div>
        <div className="metric">
          <span className="metric-value">{report?.run ? `${report.decided_automatically}` : '—'}</span>
          <span className="small muted">decided automatically, every gate passed</span>
        </div>
        <div className="metric">
          <span className="metric-value">{report?.run ? `${report.sent_to_a_person}` : '—'}</span>
          <span className="small muted">sent to a person (safety, escalation, declined)</span>
        </div>
        <div className="metric">
          <span className="metric-value">{duration(report?.median_seconds)}</span>
          <span className="small muted">median per case, claim to verdict</span>
        </div>
      </section>

      <div className="split">
        <section className="panel">
          <div className="panel-head">
            <h2>Every golden case</h2>
            <div className="segmented">
              <button className={filter === 'all' ? 'on' : ''} onClick={() => setFilter('all')}>
                All
              </button>
              <button className={filter === 'failed' ? 'on' : ''} onClick={() => setFilter('failed')}>
                Mismatches
              </button>
            </div>
          </div>
          <div className="table-wrap">
            <table className="queue">
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Label</th>
                  <th>System said</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((c) => {
                  const r = c.result
                  return (
                    <tr key={c.golden_id} style={{ cursor: 'default' }}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{CATEGORY_LABEL[c.category]}</div>
                        {r?.case_id ? (
                          <Link to={`/trace/${r.case_id}`} className="tiny mono">
                            {r.case_id} →
                          </Link>
                        ) : (
                          <span className="tiny faint">not run</span>
                        )}
                      </td>
                      <td className="small">{expectedText(c.expected)}</td>
                      <td className="small">
                        {r ? actualText(r.actual) : '—'}
                        {r?.actual.state && (
                          <div style={{ marginTop: 4 }}>
                            <StateBadge state={r.actual.state} />
                          </div>
                        )}
                      </td>
                      <td>
                        {r ? (
                          <div className="stack" style={{ gap: 4 }}>
                            <span className={`badge ${r.passed ? 'tone-good' : 'tone-bad'}`}>{r.passed ? '✓ Match' : '✗ Mismatch'}</span>
                            {r.why && !r.passed && <span className="tiny muted">{r.why}</span>}
                            <span className="tiny faint mono">{r.seconds}s</span>
                          </div>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>

        <aside className="stack">
          <section className="panel panel-pad stack">
            <span className="eyebrow">By category</span>
            {report ? <CategoryBars report={report} /> : <div className="skeleton" style={{ height: 120 }} />}
          </section>
          <section className="panel panel-pad stack" style={{ gap: 10 }}>
            <span className="eyebrow">How it’s scored</span>
            <ul className="principles">
              <li>The verdict must match: outcome, remedy type, and the exact amount (the policy formula’s refund, the tier fee, the $4.50 fee).</li>
              <li>Safety reports pass only if no agent ever decided them.</li>
              <li>Routing isn’t scored: a right verdict that also went to a person still counts. It depends on live state, such as how many disputes someone has open.</li>
            </ul>
          </section>
          {stats && (
            <section className="panel panel-pad stack" style={{ gap: 10 }}>
              <span className="eyebrow">Why cases went to a person (all cases)</span>
              {Object.keys(stats.escalation_reasons).length === 0 ? (
                <p className="small muted">None yet.</p>
              ) : (
                <dl className="kv">
                  {Object.entries(stats.escalation_reasons)
                    .sort((a, b) => b[1] - a[1])
                    .map(([k, v]) => (
                      <span key={k} style={{ display: 'contents' }}>
                        <dt>{k.replaceAll('_', ' ')}</dt>
                        <dd className="mono">{v}</dd>
                      </span>
                    ))}
                </dl>
              )}
            </section>
          )}
        </aside>
      </div>
    </div>
  )
}
