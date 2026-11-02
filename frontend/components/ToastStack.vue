<script setup lang="ts">
const { toasts, dismiss } = useToasts()
</script>

<template>
  <div class="toast-stack" aria-live="polite">
    <div v-for="t in toasts" :key="t.id" class="toast" :class="`toast-${t.kind}`">
      <div class="toast-text">
        <p class="toast-title">{{ t.title }}</p>
        <p v-if="t.body" class="toast-body">{{ t.body }}</p>
        <NuxtLink v-if="t.link" :to="t.link" class="toast-link" @click="dismiss(t.id)">
          {{ t.linkLabel || 'Open' }} →
        </NuxtLink>
      </div>
      <button class="toast-close" type="button" :aria-label="`Dismiss: ${t.title}`" @click="dismiss(t.id)">×</button>
    </div>
  </div>
</template>
