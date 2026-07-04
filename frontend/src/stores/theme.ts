import { ref } from 'vue'
import { defineStore } from 'pinia'

export type Theme = 'light' | 'dark'

// Persistence key mandated by the design handoff.
export const THEME_STORAGE_KEY = 'aperture-theme'

function initialTheme(): Theme {
  const stored = localStorage.getItem(THEME_STORAGE_KEY)
  if (stored === 'light' || stored === 'dark') return stored
  if (typeof window.matchMedia === 'function') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return 'light'
}

export const useThemeStore = defineStore('theme', () => {
  const theme = ref<Theme>(initialTheme())

  function apply(): void {
    document.documentElement.dataset.theme = theme.value
  }

  function setTheme(value: Theme): void {
    theme.value = value
    localStorage.setItem(THEME_STORAGE_KEY, value)
    apply()
  }

  function toggle(): void {
    setTheme(theme.value === 'light' ? 'dark' : 'light')
  }

  apply()

  return { theme, setTheme, toggle }
})
