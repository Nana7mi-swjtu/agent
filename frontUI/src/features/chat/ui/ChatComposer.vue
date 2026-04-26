<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

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
  analysisModuleValues: {
    type: Array,
    default: () => [],
  },
  analysisModuleOptions: {
    type: Array,
    default: () => [],
  },
  analysisModuleLabel: {
    type: String,
    default: "Analysis module",
  },
  analysisGuidance: {
    type: Object,
    default: null,
  },
});

const emit = defineEmits(["update:modelValue", "update:analysisModuleValues", "submit"]);

const inputElement = ref(null);
const selectorElement = ref(null);
const isModuleMenuOpen = ref(false);

const value = computed({
  get: () => props.modelValue,
  set: (next) => emit("update:modelValue", next),
});

const selectedAnalysisModules = computed({
  get: () => {
    const result = [];
    if (!Array.isArray(props.analysisModuleValues)) return result;
    props.analysisModuleValues.forEach((item) => {
      const moduleId = String(item || "").trim();
      if (moduleId && !result.includes(moduleId)) {
        result.push(moduleId);
      }
    });
    return result;
  },
  set: (next) => emit("update:analysisModuleValues", Array.isArray(next) ? next : []),
});

const isModuleSelected = (moduleId) => selectedAnalysisModules.value.includes(String(moduleId || "").trim());

const setModuleSelected = (moduleId, checked) => {
  const cleanModuleId = String(moduleId || "").trim();
  if (!cleanModuleId) return;
  const current = selectedAnalysisModules.value;
  const next = checked
    ? [...current, cleanModuleId].filter((item, index, list) => list.indexOf(item) === index)
    : current.filter((item) => item !== cleanModuleId);
  selectedAnalysisModules.value = next;
};

const toggleModuleMenu = () => {
  if (props.sending) return;
  isModuleMenuOpen.value = !isModuleMenuOpen.value;
};

const closeModuleMenu = () => {
  isModuleMenuOpen.value = false;
};

const onDocumentPointerdown = (event) => {
  const element = selectorElement.value;
  if (!element || element.contains(event.target)) return;
  closeModuleMenu();
};

const onModuleSelectorKeydown = (event) => {
  if (event.key !== "Escape") return;
  event.preventDefault();
  closeModuleMenu();
};

const submitComposer = () => {
  closeModuleMenu();
  emit("submit");
};

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
  submitComposer();
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

watch(
  () => props.sending,
  (next) => {
    if (next) {
      closeModuleMenu();
    }
  },
);

onMounted(() => {
  document.addEventListener("pointerdown", onDocumentPointerdown);
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocumentPointerdown);
});
</script>

<template>
  <div class="dc-composer">
    <div class="dc-composer-inner">
      <div v-if="analysisGuidance?.title && analysisGuidance?.text" class="dc-composer-guidance">
        <strong>{{ analysisGuidance.title }}</strong>
        <p>{{ analysisGuidance.text }}</p>
      </div>
      <textarea
        ref="inputElement"
        v-model="value"
        rows="1"
        :placeholder="placeholder"
        @input="onInput"
        @keydown="onKeydown"
      />
      <div class="dc-composer-toolbar">
        <div
          ref="selectorElement"
          class="dc-module-select"
          :class="{ disabled: sending, open: isModuleMenuOpen }"
          role="group"
          :aria-label="analysisModuleLabel"
          @keydown="onModuleSelectorKeydown"
        >
          <button
            type="button"
            class="dc-module-trigger"
            :disabled="sending"
            :aria-label="analysisModuleLabel"
            :aria-expanded="isModuleMenuOpen"
            aria-haspopup="true"
            aria-controls="dc-module-menu"
            @click="toggleModuleMenu"
          >
            <span class="dc-module-select-icon" aria-hidden="true"></span>
            <span class="dc-module-select-label">{{ analysisModuleLabel }}</span>
            <span class="dc-module-chevron" aria-hidden="true"></span>
          </button>
          <div
            v-if="isModuleMenuOpen"
            id="dc-module-menu"
            class="dc-module-menu"
            role="group"
            :aria-label="analysisModuleLabel"
          >
            <label
              v-for="option in analysisModuleOptions"
              :key="option.value"
              class="dc-module-option"
              :class="{ selected: isModuleSelected(option.value) }"
            >
              <input
                type="checkbox"
                :checked="isModuleSelected(option.value)"
                :value="option.value"
                :disabled="sending"
                :aria-label="`${analysisModuleLabel}: ${option.label}`"
                @change="setModuleSelected(option.value, $event.target.checked)"
              />
              <span class="dc-module-check" aria-hidden="true"></span>
              <span class="dc-module-option-label">{{ option.label }}</span>
            </label>
          </div>
        </div>
        <button class="dc-composer-send" :disabled="sending" @click="submitComposer">{{ sendLabel }}</button>
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

.dc-composer-guidance {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid rgba(47, 107, 255, 0.12);
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(47, 107, 255, 0.08), rgba(31, 157, 116, 0.08));
}

.dc-composer-guidance strong {
  color: var(--text);
  font-size: 13px;
}

.dc-composer-guidance p {
  margin: 0;
  color: var(--text-channel);
  font-size: 12px;
  line-height: 1.5;
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
  min-width: 168px;
  max-width: min(100%, 240px);
}

.dc-module-trigger {
  width: 100%;
  min-height: 40px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface-panel-subtle);
  color: var(--text-channel);
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  box-shadow: inset 0 1px 0 var(--surface-highlight);
  cursor: pointer;
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
  flex: 1;
  text-align: left;
}

.dc-module-chevron {
  width: 8px;
  height: 8px;
  border-right: 2px solid var(--accent);
  border-bottom: 2px solid var(--accent);
  transform: rotate(45deg) translateY(-2px);
  transition: transform 0.16s ease;
  flex-shrink: 0;
}

.dc-module-select.open .dc-module-chevron {
  transform: rotate(225deg) translate(-2px, -1px);
}

.dc-module-menu {
  position: absolute;
  left: 0;
  bottom: calc(100% + 8px);
  z-index: 20;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 240px;
  max-width: min(320px, calc(100vw - 48px));
  padding: 8px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface-panel);
  color: var(--text-channel);
  box-shadow: var(--shadow-sm);
}

.dc-module-option {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  width: 100%;
  padding: 0 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface-panel-subtle);
  color: var(--text-channel);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  box-shadow: inset 0 1px 0 var(--surface-highlight);
}

.dc-module-option input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.dc-module-check {
  width: 14px;
  height: 14px;
  border: 1px solid var(--text-muted);
  border-radius: 3px;
  flex-shrink: 0;
}

.dc-module-option.selected {
  border-color: var(--accent);
  background: var(--accent-soft);
  color: var(--accent);
}

.dc-module-option.selected .dc-module-check {
  border-color: var(--accent);
  background: var(--accent);
  box-shadow: inset 0 0 0 2px var(--surface-panel);
}

.dc-module-option:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft), inset 0 1px 0 var(--surface-highlight);
}

.dc-module-option-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dc-module-trigger:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft), inset 0 1px 0 var(--surface-highlight);
}

.dc-module-select.disabled {
  opacity: 0.62;
}

.dc-module-trigger:disabled,
.dc-module-select.disabled .dc-module-option {
  cursor: not-allowed;
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

  .dc-module-trigger,
  .dc-module-menu {
    width: 100%;
  }

  .dc-module-menu {
    min-width: 100%;
    max-width: 100%;
  }
}
</style>
