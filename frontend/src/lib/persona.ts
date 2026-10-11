import type { Role } from '../types/api'

// Remembered across visits for convenience only. Every page also works from the URL
// alone, so a blocked or empty localStorage never breaks anything.
const KEY = 'rr.persona'

export interface StoredPersona {
  id: string
  role: Role
  name: string
}

export function loadPersona(): StoredPersona | null {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as StoredPersona) : null
  } catch {
    return null
  }
}

export function savePersona(persona: StoredPersona): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(persona))
  } catch {
    // storage unavailable (private window etc.) — fine, the URL carries the persona
  }
}

const REVIEWER_KEY = 'rr.reviewer'

export function loadReviewer(): string {
  try {
    return localStorage.getItem(REVIEWER_KEY) ?? 'L2-reviewer-01'
  } catch {
    return 'L2-reviewer-01'
  }
}

export function saveReviewer(name: string): void {
  try {
    localStorage.setItem(REVIEWER_KEY, name)
  } catch {
    // ignore
  }
}
