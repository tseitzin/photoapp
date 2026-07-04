<script setup lang="ts">
defineProps<{
  title: string
  phase: string
}>()
</script>

<template>
  <section class="placeholder">
    <p class="kicker">Aperture</p>
    <h1 class="title">{{ title }}</h1>
    <p class="note">Coming in {{ phase }} — see TASKS.md.</p>
  </section>
</template>

<style scoped>
.placeholder {
  max-width: 1180px;
  width: 100%;
  margin: 0 auto;
  padding: 36px 40px;
}

.kicker {
  margin: 0 0 4px;
  font-size: 13px;
  color: var(--muted);
}

.title {
  margin: 0 0 8px;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.note {
  margin: 0;
  color: var(--sub);
}
</style>
