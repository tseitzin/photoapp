<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterView } from 'vue-router'
import AppTopBar from '@/components/AppTopBar.vue'
import { getHealth } from '@/api/health'

const backendUnreachable = ref(false)
const checking = ref(false)

async function checkBackend(): Promise<void> {
  checking.value = true
  try {
    await getHealth()
    backendUnreachable.value = false
  } catch {
    backendUnreachable.value = true
  } finally {
    checking.value = false
  }
}

onMounted(checkBackend)
</script>

<template>
  <div class="shell">
    <AppTopBar />
    <div v-if="backendUnreachable" class="offline-banner" role="alert">
      <span class="offline-mark" aria-hidden="true">!</span>
      Can’t reach the library service
      <button type="button" class="retry" :disabled="checking" @click="checkBackend">
        {{ checking ? 'Retrying…' : 'Retry' }}
      </button>
    </div>
    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.shell {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: auto;
}

.offline-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  background: color-mix(in oklab, var(--danger) 12%, var(--bar));
  border-bottom: 1px solid var(--border);
  color: var(--fg);
}

.offline-mark {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--danger);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
}

.retry {
  margin-left: auto;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--fg);
  padding: 4px 12px;
  border-radius: 8px;
  font-size: 12.5px;
  cursor: pointer;
}
</style>
