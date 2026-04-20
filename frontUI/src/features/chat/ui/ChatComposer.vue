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
  analysisModuleValue: {
    type: String,
    default: "",
  },
  analysisModuleOptions: {
    type: Array,
    default: () => [],
  },
  analysisModuleLabel: {
    type: String,
    default: "Analysis module",
  },
  noAnalysisModuleLabel: {
    type: String,
    default: "No module",
  },
});

const emit = defineEmits(["update:modelValue", "update:analysisModuleValue", "submit"]);

const inputElement = ref(null);

const value = computed({
  get: () => props.modelValue,
  set: (next) => emit("update:modelValue", next),
});

const selectedAnalysisModule = computed({
  get: () => props.analysisModuleValue,
  set: (next) => emit("update:analysisModuleValue", next),
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
      <div class="dc-composer-toolbar">
        <label class="dc-module-select">
          <span class="dc-module-select-icon" aria-hidden="true"></span>
          <span class="dc-module-select-label">{{ analysisModuleLabel }}</span>
          <select
            v-model="selectedAnalysisModule"
            :aria-label="analysisModuleLabel"
            :disabled="sending"
          >
            <option value="">{{ noAnalysisModuleLabel }}</option>
            <option
              v-for="option in analysisModuleOptions"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </option>
          </select>
        </label>
        <button class="dc-composer-send" :disabled="sending" @click="emit('submit')">{{ sendLabel }}</button>
      </div>
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
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 24px;
  background: var(--surface-panel);
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
  resize: none;
}

.dc-composer-inner textarea::placeholder {
  color: var(--text-muted);
}

.dc-composer-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 44px;
}

.dc-module-select {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 178px;
  max-width: min(100%, 280px);
  height: 40px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface-panel-subtle);
  color: var(--text-channel);
  box-shadow: inset 0 1px 0 var(--surface-highlight);
}

.dc-module-select-icon {
  width: 14px;
  height: 14px;
  border: 2px solid var(--accent);
  border-radius: 999px;
  box-shadow: 0 0 0 4px var(--accent-soft);
  flex-shrink: 0;
}

.dc-module-select-label {
  color: var(--accent);
  font-size: 13px;
  font-weight: 700;
  white-space: nowrap;
}

.dc-module-select select {
  min-width: 0;
  max-width: 148px;
  height: 38px;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.dc-module-select:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft), inset 0 1px 0 var(--surface-highlight);
}

.dc-module-select:has(select:disabled) {
  opacity: 0.62;
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

@media (max-width: 640px) {
  .dc-composer {
    padding: 0 14px 18px;
  }

  .dc-composer-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .dc-module-select,
  .dc-composer-send {
    width: 100%;
  }

  .dc-module-select {
    max-width: none;
  }

  .dc-module-select select {
    max-width: none;
    flex: 1;
  }
}
</style>
