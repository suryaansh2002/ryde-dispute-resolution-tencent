import type { Role } from '../types/api'

export function PartyName({ role, name }: { role: Role; name: string }) {
  return <span className={`party ${role}`}>{name}</span>
}

export function PartyPill({ role, children }: { role: Role; children?: React.ReactNode }) {
  return <span className={`party-pill ${role}`}>{children ?? (role === 'rider' ? 'Rider' : 'Driver')}</span>
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}
