<script setup>
defineProps({
  error: {
    type: String,
    default: "",
  },
  success: {
    type: String,
    default: "",
  },
  muted: {
    type: String,
    default: "",
  },
});
</script>

<template>
  <div v-if="muted" class="muted-text">{{ muted }}</div>
  <div v-if="error" class="msg-err">{{ error }}</div>
  <div v-if="success" class="msg-ok">{{ success }}</div>
</template>
