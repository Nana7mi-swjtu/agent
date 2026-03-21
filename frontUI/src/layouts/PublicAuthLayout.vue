<script setup>
import { useUiStore } from "@/stores/ui";

const uiStore = useUiStore();
</script>

<template>
  <div class="auth-stage" :class="{ 'has-gif': uiStore.hasAuthBgGif }" :style="uiStore.authStageStyle">
    <div class="auth-overlay" v-if="uiStore.hasAuthBgGif"></div>
    <div class="auth-box">
      <slot />
    </div>
  </div>
</template>
