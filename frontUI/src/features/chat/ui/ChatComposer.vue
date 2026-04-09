<script setup>
import { computed } from "vue";

const props = defineProps({
  modelValue: {
    type: String,
    default: "",
  },
  sending: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: "",
  },
  placeholder: {
    type: String,
    default: "",
  },
});

const emit = defineEmits(["update:modelValue", "submit"]);

const value = computed({
  get: () => props.modelValue,
  set: (next) => emit("update:modelValue", next),
});
</script>

<template>
  <div class="dc-composer">
    <div class="dc-composer-inner">
      <input
        v-model="value"
        type="text"
        :placeholder="placeholder"
        @keydown.enter.exact.prevent="emit('submit')"
      />
      <button class="dc-composer-send" :disabled="sending" @click="emit('submit')">➤</button>
    </div>
    <div v-if="error" class="msg-err">{{ error }}</div>
  </div>
</template>

<style scoped>
.dc-composer {
  padding: 0 16px 24px;
  flex-shrink: 0;
}

.dc-composer-inner {
  background: var(--bg-input);
  border-radius: 8px;
  display: flex;
  align-items: flex-end;
  gap: 0;
  padding: 0 0 0 16px;
  min-height: 44px;
}

.dc-composer-inner input {
  flex: 1;
  background: none;
  border: none;
  color: var(--text);
  font-size: 15px;
  padding: 11px 4px;
  outline: none;
}

.dc-composer-inner input::placeholder {
  color: var(--text-muted);
}

.dc-composer-send {
  width: 44px;
  height: 44px;
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border-radius: 0 8px 8px 0;
  transition: color 0.1s;
  flex-shrink: 0;
  padding: 0;
}

.dc-composer-send:hover {
  color: var(--text);
}

.dc-composer-send:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
