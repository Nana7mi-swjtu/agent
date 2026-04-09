<script setup>
import { computed, nextTick, ref, watch } from "vue";

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
  sendLabel: {
    type: String,
    default: "Send",
  },
});

const emit = defineEmits(["update:modelValue", "submit"]);

const inputElement = ref(null);

const value = computed({
  get: () => props.modelValue,
  set: (next) => emit("update:modelValue", next),
});

const resizeInput = () => {
  const element = inputElement.value;
  if (!element) return;
  element.style.height = "0px";
  element.style.height = `${Math.min(element.scrollHeight, 180)}px`;
};

const onKeydown = (event) => {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) {
    return;
  }
  event.preventDefault();
  emit("submit");
};

const onInput = () => {
  resizeInput();
};

watch(
  () => props.modelValue,
  async () => {
    await nextTick();
    resizeInput();
  },
  { immediate: true },
);
</script>

<template>
  <div class="dc-composer">
    <div class="dc-composer-inner">
      <textarea
        ref="inputElement"
        v-model="value"
        rows="1"
        :placeholder="placeholder"
        @input="onInput"
        @keydown="onKeydown"
      />
      <button class="dc-composer-send" :disabled="sending" @click="emit('submit')">{{ sendLabel }}</button>
    </div>
    <div v-if="error" class="msg-err">{{ error }}</div>
  </div>
</template>

<style scoped>
.dc-composer {
  padding: 0 24px 24px;
  flex-shrink: 0;
}

.dc-composer-inner {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 24px;
  background: var(--surface-panel);
  align-items: flex-end;
  min-height: 72px;
  box-shadow: inset 0 1px 0 var(--surface-highlight);
}

.dc-composer-inner textarea {
  flex: 1;
  min-height: 44px;
  max-height: 180px;
  background: none;
  border: none;
  color: var(--text);
  font-size: 15px;
  line-height: 1.6;
  padding: 2px 2px 0;
  outline: none;
}

.dc-composer-inner textarea::placeholder {
  color: var(--text-muted);
}

.dc-composer-send {
  min-width: 84px;
  height: 44px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform 0.16s ease, opacity 0.16s ease;
  flex-shrink: 0;
  padding: 0;
}

.dc-composer-send:hover {
  transform: translateY(-1px);
}

.dc-composer-send:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
