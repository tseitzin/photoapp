<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useLibraryStore } from '@/stores/library'
import { useThemeStore } from '@/stores/theme'
import { formatCount } from '@/utils/format'
import type { GroupBy } from '@/utils/grouping'

const themeStore = useThemeStore()
const libraryStore = useLibraryStore()
const route = useRoute()

const onLibrary = computed(() => route.name === 'library')

const navItems = [
  { label: 'Home', to: '/' },
  { label: 'Library', to: '/library' },
  { label: 'Duplicates', to: '/duplicates' },
  { label: 'Cleanup', to: '/quarantine' },
  { label: 'Organize', to: '/organize' },
] as const

const GROUP_OPTIONS: { value: GroupBy; label: string }[] = [
  { value: 'folder', label: 'Folders' },
  { value: 'date', label: 'Date' },
  { value: 'camera', label: 'Camera' },
]

const searchInput = ref('')
let searchTimer: ReturnType<typeof setTimeout> | undefined

function onSearchInput(): void {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => void libraryStore.setSearch(searchInput.value.trim()), 300)
}
</script>

<template>
  <header class="top-bar">
    <RouterLink to="/" class="logo">
      <span class="logo-mark" aria-hidden="true" />
      <span class="logo-name">Aperture</span>
    </RouterLink>
    <span class="rule" aria-hidden="true" />
    <nav class="nav" aria-label="Primary">
      <RouterLink
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        class="nav-link"
        active-class="nav-link--active"
        :exact-active-class="item.to === '/' ? 'nav-link--active' : undefined"
      >
        {{ item.label }}
      </RouterLink>
    </nav>
    <input
      v-if="onLibrary"
      v-model="searchInput"
      class="search"
      type="search"
      :placeholder="`Search ${formatCount(libraryStore.total)} photos…`"
      aria-label="Search photos by filename"
      @input="onSearchInput"
    />
    <span class="spacer" />
    <div v-if="onLibrary" class="segmented" role="group" aria-label="Group by">
      <button
        v-for="option in GROUP_OPTIONS"
        :key="option.value"
        type="button"
        class="seg-btn"
        :class="{ 'seg-btn--active': libraryStore.groupBy === option.value }"
        @click="libraryStore.setGroupBy(option.value)"
      >
        {{ option.label }}
      </button>
    </div>
    <div
      class="theme-toggle"
      role="group"
      aria-label="Theme"
    >
      <button
        type="button"
        class="theme-btn"
        :class="{ 'theme-btn--active': themeStore.theme === 'light' }"
        aria-label="Light theme"
        @click="themeStore.setTheme('light')"
      >
        &#9728;
      </button>
      <button
        type="button"
        class="theme-btn"
        :class="{ 'theme-btn--active': themeStore.theme === 'dark' }"
        aria-label="Dark theme"
        @click="themeStore.setTheme('dark')"
      >
        &#9789;
      </button>
    </div>
    <div class="avatar" aria-hidden="true">JD</div>
  </header>
</template>

<style scoped>
.top-bar {
  height: 52px;
  flex: none;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 0 16px;
  background: var(--bar);
  border-bottom: 1px solid var(--border);
}

.logo {
  display: flex;
  align-items: center;
  gap: 9px;
  text-decoration: none;
  color: inherit;
}

.logo-mark {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: var(--accent);
}

.logo-name {
  font-weight: 600;
  letter-spacing: -0.01em;
}

.rule {
  width: 1px;
  height: 22px;
  background: var(--border);
}

.nav {
  display: flex;
  gap: 2px;
}

.nav-link {
  padding: 6px 11px;
  border-radius: 8px;
  text-decoration: none;
  color: var(--sub);
  font-size: 13px;
  font-weight: 500;
}

.nav-link:hover {
  background: var(--hover);
}

.nav-link--active {
  color: var(--fg);
  font-weight: 600;
  background: var(--chip);
}

.spacer {
  flex: 1;
}

.search {
  flex: 1;
  max-width: 440px;
  height: 32px;
  padding: 0 12px;
  border: 0;
  border-radius: 8px;
  background: var(--chip);
  color: var(--fg);
  font-size: 12.5px;
  font-family: inherit;
}

.search::placeholder {
  color: var(--muted);
}

.segmented {
  display: flex;
  background: var(--seg-bg);
  border-radius: 8px;
  padding: 2px;
  gap: 2px;
  font-size: 12.5px;
}

.seg-btn {
  border: 0;
  padding: 5px 13px;
  border-radius: 6px;
  background: transparent;
  color: var(--sub);
  font-weight: 500;
  cursor: pointer;
}

.seg-btn--active {
  background: var(--seg-active-bg);
  color: var(--seg-active-fg);
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
}

.theme-toggle {
  display: flex;
  background: var(--seg-bg);
  border-radius: 8px;
  padding: 2px;
  gap: 2px;
}

.theme-btn {
  border: 0;
  padding: 4px 10px;
  border-radius: 6px;
  background: transparent;
  color: var(--sub);
  font-size: 13px;
  cursor: pointer;
}

.theme-btn--active {
  background: var(--seg-active-bg);
  color: var(--seg-active-fg);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
}

.avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: oklch(0.58 0.08 30);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
}
</style>
