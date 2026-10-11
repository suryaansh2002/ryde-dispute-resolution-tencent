import type { Category, EvidenceIndex } from '../types/api'

/**
 * "What would change this outcome", from the policy's deterministic thresholds and the
 * case file's measured values. Never from the model.
 */
export function counterfactual(category: Category | null, index: EvidenceIndex | null): string | null {
  if (!index || !category) return null
  if (category === 'route_deviation') {
    const c = index['ROUTE-COMPARISON']?.data
    if (!c) return null
    const pct = Number(c.extra_pct).toFixed(1)
    return `Measured ${pct}% extra distance. Under 10% there is no refund; 10–25% refunds half the extra fare; over 25% refunds all of it. A recorded traffic incident on the route, or a detour the rider asked for, makes any deviation justified.`
  }
  if (category === 'no_show_charge') {
    const p = index['PICKUP-PROXIMITY']?.data
    if (!p) return null
    return `The driver’s closest GPS fix was ${Math.round(p.closest_approach_m)} m from the pickup, against a ${p.arrival_radius_m} m arrival radius. Inside the radius, the fee would stand if the driver waited the required time and tried to reach the rider.`
  }
  if (category === 'property_damage') {
    return 'With a valid photo, the fee is the tier amount: $40 for a spill, $120 for stains or bodily fluids, $200 for vomit. Without a valid photo the claim is declined, not denied, and can be refiled.'
  }
  return null
}
