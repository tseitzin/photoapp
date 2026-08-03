import { describe, expect, it } from 'vitest'
import { formatCoordinates, formatPlace, mapUrl } from '../format'

describe('formatPlace', () => {
  it('names a US photo by city and state', () => {
    expect(
      formatPlace({ city: 'Boston', region: 'Massachusetts', country: 'US', place_distance_km: 0.2 }),
    ).toBe('Boston, Massachusetts')
  })

  it('says "near" when the closest known town is some way off', () => {
    // Reverse geocoding returns the nearest populated place, which in open
    // country is not where the photo was taken.
    expect(
      formatPlace({
        city: 'Gorham',
        region: 'New Hampshire',
        country: 'US',
        place_distance_km: 16.7,
      }),
    ).toBe('near Gorham, New Hampshire')
  })

  it('treats a place just outside town as still being that place', () => {
    expect(
      formatPlace({ city: 'Conway', region: 'New Hampshire', country: 'US', place_distance_km: 5 }),
    ).toBe('Conway, New Hampshire')
  })

  it('prefers the country abroad, where an admin region means less', () => {
    expect(
      formatPlace({ city: 'Kyoto', region: 'Kyoto', country: 'JP', place_distance_km: 1 }),
    ).toBe('Kyoto, Kyoto')
  })

  it('falls back to the country when there is no region', () => {
    expect(formatPlace({ city: 'Singapore', region: null, country: 'SG', place_distance_km: 1 })).toBe(
      'Singapore, SG',
    )
  })

  it('gives just the city when nothing else is known', () => {
    expect(formatPlace({ city: 'Atlantis', region: null, country: null })).toBe('Atlantis')
  })

  it('is null for a photo with no place — the row is then hidden entirely', () => {
    expect(formatPlace({})).toBeNull()
    expect(formatPlace({ city: null, region: 'Massachusetts', country: 'US' })).toBeNull()
  })

  it('does not claim precision when the distance is unknown', () => {
    expect(formatPlace({ city: 'Boston', region: 'Massachusetts', country: 'US' })).toBe(
      'Boston, Massachusetts',
    )
  })
})

describe('formatCoordinates', () => {
  it('marks hemispheres rather than showing signs', () => {
    expect(formatCoordinates(44.2697, -71.3034)).toBe('44.26970° N, 71.30340° W')
    expect(formatCoordinates(-33.8688, 151.2093)).toBe('33.86880° S, 151.20930° E')
  })

  it('handles the equator and prime meridian as positive', () => {
    expect(formatCoordinates(0, 0)).toBe('0.00000° N, 0.00000° E')
  })
})

describe('mapUrl', () => {
  it('points at OpenStreetMap with a marker, and nothing else', () => {
    const url = mapUrl(44.2697, -71.3034)

    expect(url).toContain('https://www.openstreetmap.org/')
    expect(url).toContain('mlat=44.2697')
    expect(url).toContain('mlon=-71.3034')
  })
})
