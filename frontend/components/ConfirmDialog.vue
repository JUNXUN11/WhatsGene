<script setup lang="ts">
const props = withDefaults(defineProps<{
  open: boolean
  title: string
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
  busy?: boolean
  busyLabel?: string
}>(), {
  confirmLabel: 'Confirm',
  cancelLabel: 'Cancel',
  danger: false,
  busy: false,
  busyLabel: 'Working…',
})

const emit = defineEmits<{
  confirm: []
  cancel: []
}>()

const cancelBtn = ref<HTMLButtonElement | null>(null)
const confirmBtn = ref<HTMLButtonElement | null>(null)

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open && !props.busy) emit('cancel')
}

watch(() => props.open, (isOpen) => {
  document.body.style.overflow = isOpen ? 'hidden' : ''
  if (isOpen) {
    // Focus the safe choice for destructive actions, the confirm button otherwise.
    nextTick(() => {
      if (props.danger) cancelBtn.value?.focus()
      else confirmBtn.value?.focus()
    })
  }
})

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open" class="modal-backdrop" @click.self="busy ? null : emit('cancel')">
        <div class="modal" role="dialog" aria-modal="true" :aria-label="title">
          <h2>{{ title }}</h2>
          <div class="modal-body">
            <slot />
          </div>
          <div class="modal-actions">
            <button ref="cancelBtn" class="btn btn-secondary btn-small" :disabled="busy" @click="emit('cancel')">
              {{ cancelLabel }}
            </button>
            <button
              ref="confirmBtn"
              :class="['btn', 'btn-small', danger ? 'btn-danger' : '']"
              :disabled="busy"
              @click="emit('confirm')"
            >
              {{ busy ? busyLabel : confirmLabel }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
