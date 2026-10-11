/** Refs the validator stripped, parsed from a trace event's detail, e.g.
 * "citations stripped: ['EV-9999', 'POL-99']" or "..., policy stripped: POL-11". */
export function strippedRefs(detail?: string | null): string[] {
  if (!detail || !detail.includes('stripped')) return []
  const quoted = [...detail.matchAll(/'([A-Z][A-Z0-9-]+)'/g)].map((m) => m[1])
  const policy = detail.match(/policy stripped: (POL-[0-9-]+)/)?.[1]
  return [...new Set([...quoted, ...(policy ? [policy] : [])])]
}
