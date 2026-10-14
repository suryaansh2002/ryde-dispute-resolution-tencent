import { useState, type ReactNode } from 'react'
import type { DecisionObject, FactIcon } from '../types/api'
import { band, money, outcomeLabel, REMEDY } from '../lib/format'
import { Cite } from './evidence'
import { Icon } from './Icon'

export function Phone({ children, small }: { children: ReactNode; small?: boolean }) {
  return (
    <div className="phone" role="group" aria-label="Phone preview">
      <div className="phone-screen">
        <div className="island" />
        <div className="statusbar">
          <span>9:41</span>
          <span className="sys">
            <Icon name="wifi" size={small ? 14 : 16} stroke={2.2} />
            <svg width={small ? 22 : 25} height="12" viewBox="0 0 25 12" aria-hidden="true">
              <rect x=".5" y=".5" width="21" height="11" rx="3.5" fill="none" stroke="currentColor" opacity=".4" />
              <rect x="2" y="2" width="16" height="8" rx="2" fill="currentColor" />
              <rect x="23" y="4" width="1.5" height="4" rx=".75" fill="currentColor" opacity=".4" />
            </svg>
          </span>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Back({ onClick, label = 'Back' }: { onClick: () => void; label?: string }) {
  return (
    <button className="back" onClick={onClick}>
      <Icon name="left" size={20} stroke={2.2} />
      {label}
    </button>
  )
}

export function FactSheet({ title, facts }: { title?: string; facts: { icon: FactIcon; text: string }[] }) {
  if (!facts.length) return null
  return (
    <div className="sheet">
      {title && <h4>{title}</h4>}
      <ul className="facts">
        {facts.map((f, i) => (
          <li key={i}><Icon name={f.icon} size={18} /><span>{f.text}</span></li>
        ))}
      </ul>
    </div>
  )
}

export type HeroTone = 'good' | 'warn' | 'bad' | 'neutral'
const TONE_IC: Record<HeroTone, ['check' | 'clock' | 'shield' | 'info', string, string]> = {
  good: ['check', 'var(--good-soft)', 'var(--good)'],
  warn: ['clock', 'var(--warn-soft)', 'var(--warn)'],
  bad: ['shield', 'var(--bad-soft)', 'var(--bad)'],
  neutral: ['info', 'var(--fill)', 'var(--ink-2)'],
}

export function ResultHero({ head, sub, tone }: { head: string; sub: string; tone: HeroTone }) {
  const [ic, bg, fg] = TONE_IC[tone]
  return (
    <div className="hero-result">
      <span className="badge-ic" style={{ background: bg, color: fg }}><Icon name={ic} size={26} stroke={2.2} /></span>
      <h3>{head}</h3>
      <p>{sub}</p>
    </div>
  )
}

export function Notice({ icon, tone = 'neutral', children }: { icon: FactIcon | 'send'; tone?: HeroTone; children: ReactNode }) {
  const [, bg, fg] = TONE_IC[tone]
  return (
    <div className="notice">
      <span className="ic" style={{ background: bg, color: fg }}><Icon name={icon} size={16} /></span>
      <div className="small" style={{ paddingTop: 6 }}>{children}</div>
    </div>
  )
}

export function ArgText({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  const long = text.length > 420
  return (
    <>
      <p className={long && !open ? 'clamp' : ''}>{text}</p>
      {long && <button className="more-btn" onClick={() => setOpen(!open)}>{open ? 'Show less' : 'Read more'}</button>}
    </>
  )
}

export function Verdict({ caseId, dec, court }: { caseId: string; dec: DecisionObject; court?: boolean }) {
  const amount = dec.remedy?.amount
  return (
    <div className={`verdict${court ? ' bench' : ''}`}>
      <div className="verdict-head">
        <div>
          {court && <p className="small muted">Ruling</p>}
          <h4>{outcomeLabel(dec.outcome)}</h4>
          <p className="muted">
            {REMEDY[dec.remedy.type] ?? dec.remedy.type}
            {amount ? ` · ${money(amount)}` : ''}
            {dec.policy_applied && <> · <Cite caseId={caseId} refId={dec.policy_applied} /></>}
          </p>
        </div>
        <Confidence value={dec.confidence} />
      </div>
      {court && <p className="findings-title">Findings of fact</p>}
      <ol className="findings">
        {dec.reasoning.map((f, i) => (
          <li key={i}>
            <div>
              {f.finding} {f.cites.map((x) => <Cite key={x} caseId={caseId} refId={x} />)}
            </div>
          </li>
        ))}
      </ol>
      {dec.human_ratified && (
        <p className="small muted" style={{ padding: '0 20px 18px' }}>
          Reviewed by {dec.ratified_by ?? 'a person'}.
        </p>
      )}
    </div>
  )
}

export function Confidence({ value }: { value: number }) {
  return (
    <div className="conf">
      <div className="conf-labels"><span>Confidence: {band(value)}</span><span className="num">{value.toFixed(2)}</span></div>
      <div className="conf-track">
        <div className="conf-fill" style={{ width: `${value * 100}%` }} />
        <div className="conf-tick" style={{ left: '60%' }} title="Below 0.60 a person decides" />
      </div>
      <span className="tiny muted">Below the 0.60 mark, a person decides.</span>
    </div>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="prep-run" aria-live="polite" style={{ border: 0 }}>
      <span className="spin" />
      {label}
    </div>
  )
}

export function ErrorNote({ error, retry }: { error: Error; retry?: () => void }) {
  return (
    <div className="notice" role="alert" style={{ background: 'var(--bad-soft)' }}>
      <span className="ic" style={{ background: 'var(--surface)', color: 'var(--bad)' }}><Icon name="alert" size={16} /></span>
      <div style={{ flex: 1 }}>
        <strong>Couldn’t reach the server</strong>
        <p className="small" style={{ color: 'var(--ink-2)' }}>{error.message}</p>
      </div>
      {retry && <button className="btn btn-secondary btn-sm" onClick={retry}>Try again</button>}
    </div>
  )
}
