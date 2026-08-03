export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unit = 'B'
  for (const next of units) {
    if (value < 1024) break
    value /= 1024
    unit = next
  }
  return `${value >= 100 ? Math.round(value) : value.toFixed(1)} ${unit}`
}

export function formatCount(value: number): string {
  return value.toLocaleString('en-US')
}

/**
 * Beyond this the place name is context, not a location, so it reads "near X".
 * Roughly the distance at which a town stops being where you were.
 */
export const NEAR_THRESHOLD_KM = 5

export interface PlaceLike {
  city?: string | null
  region?: string | null
  country?: string | null
  place_distance_km?: number | null
}

/**
 * "Boston, Massachusetts" when the photo is in the place, "near Gorham, New
 * Hampshire" when the nearest known town is some way off. Reverse geocoding
 * returns the closest populated place, which in open country can be tens of
 * kilometres away — saying so is the difference between context and a false
 * claim about where the photo was taken.
 */
export function formatPlace(photo: PlaceLike): string | null {
  if (!photo.city) return null
  // US states read naturally after the city; elsewhere the country is clearer
  // than an administrative region most people won't recognise.
  const qualifier = photo.country === 'US' ? photo.region : (photo.region ?? photo.country)
  const name = qualifier ? `${photo.city}, ${qualifier}` : photo.city
  const distance = photo.place_distance_km
  return distance != null && distance > NEAR_THRESHOLD_KM ? `near ${name}` : name
}

/** Decimal degrees as N/S + E/W, the form EXIF viewers and maps both accept. */
export function formatCoordinates(latitude: number, longitude: number): string {
  const lat = `${Math.abs(latitude).toFixed(5)}° ${latitude >= 0 ? 'N' : 'S'}`
  const lon = `${Math.abs(longitude).toFixed(5)}° ${longitude >= 0 ? 'E' : 'W'}`
  return `${lat}, ${lon}`
}

/**
 * Link to a map for these coordinates.
 *
 * Deliberately a link the user chooses to follow, not an embedded map: this is
 * a local-first app, and an iframe or tile request would hand the location of
 * the user's photos to a third party just for rendering the panel.
 */
export function mapUrl(latitude: number, longitude: number): string {
  return `https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=15/${latitude}/${longitude}`
}

export function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const date = new Date(iso)
  return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
}
