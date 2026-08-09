<script setup lang="ts">
import { formatCount } from '@/utils/format'

/**
 * "Showing 50 of 242" plus a button for the next page.
 *
 * The duplicate lists fetch 50 at a time and previously had no way to reach the
 * rest, so most of a large library was simply unreachable.
 */
defineProps<{
  shown: number
  total: number
  hasMore: boolean
  busy: boolean
  noun: string
}>()

defineEmits<{ more: [] }>()
</script>

<template>
  <div v-if="total > shown || shown > 0" class="load-more">
    <span class="count"> Showing {{ formatCount(shown) }} of {{ formatCount(total) }} {{ noun }} </span>
    <button v-if="hasMore" type="button" class="btn" :disabled="busy" @click="$emit('more')">
      {{ busy ? 'Loading…' : 'Load more' }}
    </button>
  </div>
</template>

<style scoped>
.load-more {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 14px 0 4px;
}

.count {
  font-size: 12px;
  color: var(--muted);
}

.btn {
  padding: 7px 16px;
  border-radius: 9px;
  border: 1px solid var(--border);
  background: var(--chip);
  color: var(--fg);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
}

.btn:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
