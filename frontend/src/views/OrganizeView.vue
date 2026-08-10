<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import DestinationCard from '@/components/organize/DestinationCard.vue'
import LibraryLayoutCard from '@/components/organize/LibraryLayoutCard.vue'
import DestinationPickerModal from '@/components/organize/DestinationPickerModal.vue'
import PreviewPanel from '@/components/organize/PreviewPanel.vue'
import ToggleCard from '@/components/organize/ToggleCard.vue'
import WorkingSetPanel from '@/components/organize/WorkingSetPanel.vue'
import { useOrganizeStore } from '@/stores/organize'
import { formatCount } from '@/utils/format'

const store = useOrganizeStore()
const router = useRouter()

onMounted(() => void store.load())
// The run continues on the server; only this view's 1s poll stops. load()
// picks an in-flight run back up when the view returns.
onUnmounted(() => store.stopPolling())

function discard(): void {
  store.discard()
  void router.push('/library')
}
</script>

<template>
  <div class="organize">
    <div v-if="store.phase === 'done' && store.activeRun" class="banner" role="status">
      <span class="banner-check" aria-hidden="true">✓</span>
      <span>
        Organized {{ formatCount(store.activeRun.moved) }} photos into
        <span class="banner-path">{{ store.activeRun.params.destination }}</span>
        · {{ formatCount(store.activeRun.skipped_duplicates) }} duplicates skipped.
      </span>
      <button type="button" class="banner-dismiss" @click="store.reset()">Dismiss</button>
    </div>
    <p v-else-if="store.error" class="error" role="alert">{{ store.error }}</p>

    <div class="body">
      <WorkingSetPanel />

      <main class="center">
        <div class="center-inner">
          <h1 class="title">Organize {{ store.workingSet.length }} folders</h1>
          <p class="intro">
            Set where these photos go and how they’re labelled. Nothing moves until you confirm.
          </p>

          <template v-if="store.workingSet.length > 0">
            <LibraryLayoutCard />

            <DestinationCard />

            <ToggleCard
              title="Rename files"
              :model-value="store.rename"
              @update:model-value="store.rename = $event"
            >
              <template #description>Use the capture date + time as the file name.</template>
              <template #extra>
                <div v-if="store.preview?.rename_example" class="rename-example">
                  <span class="rename-old">{{ store.preview.rename_example.old }}</span>
                  <span class="rename-arrow">→</span>
                  <span class="rename-new">{{ store.preview.rename_example.new }}</span>
                </div>
              </template>
            </ToggleCard>

            <ToggleCard
              title="Skip duplicates"
              :model-value="store.skipDuplicates"
              @update:model-value="store.skipDuplicates = $event"
            >
              <template #description>
                <span class="dup-count">{{
                  formatCount(store.preview?.duplicates_in_set ?? 0)
                }}</span>
                exact duplicates found in this set won’t be moved — only the best copy goes.
              </template>
            </ToggleCard>

            <button type="button" class="discard" @click="discard">Discard working set</button>
          </template>

          <div v-else class="empty">
            <p>
              Your working set is empty. Check folders in the Library sidebar, then come back to
              organize them.
            </p>
            <RouterLink to="/library" class="empty-link">Go to Library</RouterLink>
          </div>
        </div>
      </main>

      <PreviewPanel />
    </div>

    <DestinationPickerModal v-if="store.pickerOpen" />
  </div>
</template>

<style scoped>
.organize {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.banner {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 24px;
  background: var(--success-soft);
  color: var(--success-fg);
  font-size: 13px;
  font-weight: 600;
  border-bottom: 1px solid var(--border);
}

.banner-check {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--success);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  flex: none;
}

.banner-path {
  font-family: var(--font-mono);
}

.banner-dismiss {
  margin-left: auto;
  height: 28px;
  padding: 0 12px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.banner-dismiss:hover {
  background: var(--hover);
}

.error {
  flex: none;
  margin: 0;
  padding: 11px 24px;
  background: color-mix(in oklch, var(--danger) 12%, transparent);
  color: var(--danger);
  font-size: 13px;
  border-bottom: 1px solid var(--border);
}

.body {
  flex: 1;
  display: flex;
  min-height: 0;
}

.center {
  flex: 1;
  overflow: auto;
  min-width: 0;
  background: var(--app-bg);
}

.center-inner {
  max-width: 640px;
  margin: 0 auto;
  padding: 26px 30px 40px;
}

.title {
  margin: 0 0 4px;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.intro {
  margin: 0 0 24px;
  font-size: 13px;
  color: var(--sub);
}

.rename-example {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  font-family: var(--font-mono);
  font-size: 12px;
}

.rename-old {
  color: var(--muted);
  text-decoration: line-through;
}

.rename-arrow {
  color: var(--muted);
}

.rename-new {
  font-weight: 600;
  color: var(--accent);
}

.dup-count {
  font-weight: 600;
  color: var(--fg);
}

.discard {
  height: 34px;
  padding: 0 14px;
  border: 0;
  border-radius: 9px;
  background: var(--chip);
  color: var(--fg);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}

.empty {
  background: var(--card);
  border: 1px dashed var(--cb-border);
  border-radius: 14px;
  padding: 28px;
  text-align: center;
  color: var(--sub);
  font-size: 13px;
}

.empty-link {
  display: inline-block;
  margin-top: 12px;
  height: 34px;
  line-height: 34px;
  padding: 0 16px;
  border-radius: 9px;
  background: var(--accent);
  color: var(--on-accent);
  font-size: 12.5px;
  font-weight: 600;
}
</style>
