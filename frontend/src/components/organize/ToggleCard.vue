<script setup lang="ts">
defineProps<{
  title: string
  modelValue: boolean
}>()

defineEmits<{ 'update:modelValue': [value: boolean] }>()
</script>

<template>
  <section class="card">
    <div class="row">
      <div class="text">
        <h2 class="card-title">{{ title }}</h2>
        <p class="desc"><slot name="description" /></p>
      </div>
      <button
        type="button"
        class="toggle"
        :class="{ 'toggle--on': modelValue }"
        role="switch"
        :aria-checked="modelValue"
        :aria-label="title"
        @click="$emit('update:modelValue', !modelValue)"
      >
        <span class="knob" />
      </button>
    </div>
    <slot name="extra" />
  </section>
</template>

<style scoped>
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 20px;
  margin-bottom: 16px;
}

.row {
  display: flex;
  align-items: center;
  gap: 14px;
}

.text {
  flex: 1;
}

.card-title {
  margin: 0 0 3px;
  font-size: 14px;
  font-weight: 600;
}

.desc {
  margin: 0;
  font-size: 12px;
  color: var(--sub);
}

/* 44×25 track, 21px knob — per handoff toggle spec. */
.toggle {
  width: 44px;
  height: 25px;
  border: 0;
  border-radius: 13px;
  background: var(--cb-border);
  position: relative;
  cursor: pointer;
  flex: none;
  padding: 0;
}

.toggle--on {
  background: var(--accent);
}

.knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 21px;
  height: 21px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
  transform: translateX(0);
  transition: transform 0.15s;
}

.toggle--on .knob {
  transform: translateX(19px);
}
</style>
