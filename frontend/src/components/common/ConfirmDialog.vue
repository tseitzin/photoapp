<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    title: string
    confirmLabel?: string
    danger?: boolean
    /** When set, the confirm button stays disabled until this is typed. */
    typeToConfirm?: string
  }>(),
  { confirmLabel: 'Confirm', danger: false, typeToConfirm: undefined },
)

const emit = defineEmits<{ confirm: []; cancel: [] }>()

const typed = ref('')
const confirmEnabled = computed(
  () => !props.typeToConfirm || typed.value === props.typeToConfirm,
)
</script>

<template>
  <div class="backdrop" role="presentation" @click.self="emit('cancel')">
    <div class="dialog" role="dialog" aria-modal="true" :aria-label="title">
      <h2 class="title">{{ title }}</h2>
      <div class="body">
        <slot />
      </div>
      <label v-if="typeToConfirm" class="type-confirm">
        Type <code>{{ typeToConfirm }}</code> to enable:
        <input v-model="typed" type="text" class="type-input" :placeholder="typeToConfirm" />
      </label>
      <div class="actions">
        <button type="button" class="btn" @click="emit('cancel')">Cancel</button>
        <button
          type="button"
          class="btn"
          :class="danger ? 'btn--danger' : 'btn--primary'"
          :disabled="!confirmEnabled"
          @click="emit('confirm')"
        >
          {{ confirmLabel }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  z-index: 70;
  background: rgba(9, 9, 11, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.dialog {
  width: 520px;
  max-width: 100%;
  max-height: 84vh;
  display: flex;
  flex-direction: column;
  background: var(--card);
  color: var(--fg);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 20px;
  box-shadow: var(--shadow-modal);
}

.title {
  margin: 0 0 12px;
  font-size: 17px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  font-size: 13px;
  color: var(--sub);
}

.type-confirm {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  font-size: 12.5px;
  color: var(--sub);
}

.type-confirm code {
  font-family: var(--font-mono);
  color: var(--danger);
  font-weight: 600;
}

.type-input {
  flex: 1;
  height: 30px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--app-bg);
  color: var(--fg);
  font-family: var(--font-mono);
  font-size: 12px;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 16px;
}

.btn {
  padding: 7px 16px;
  border-radius: 9px;
  border: 1px solid var(--border);
  background: var(--chip);
  color: var(--fg);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}

.btn--primary {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--on-accent);
  font-weight: 600;
}

.btn--danger {
  background: var(--danger);
  border-color: var(--danger);
  color: #fff;
  font-weight: 600;
}

.btn:disabled {
  opacity: 0.45;
  cursor: default;
}
</style>
