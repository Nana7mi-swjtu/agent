<script setup>
defineProps({
  uiStore: {
    type: Object,
    required: true,
  },
  workspaceId: {
    type: String,
    default: "default",
  },
  enterpriseName: {
    type: String,
    default: "",
  },
  uploading: {
    type: Boolean,
    default: false,
  },
  fileInputKey: {
    type: Number,
    default: 0,
  },
});

defineEmits(["update:enterpriseName", "select-file", "submit"]);
</script>

<template>
  <div class="bankruptcy-upload-panel">
    <div class="prompt-box">
      <strong>{{ uiStore.t("bankruptcyWorkspaceScope") }}</strong>
      <p class="scope-text">{{ workspaceId }}</p>
    </div>

    <div class="prompt-box upload-card">
      <strong>{{ uiStore.t("bankruptcySaveUpload") }}</strong>
      <label class="bankruptcy-upload-dropzone">
        <span class="bankruptcy-upload-title">CSV</span>
        <span class="bankruptcy-upload-subtitle">{{ uiStore.t("bankruptcySaveUpload") }}</span>
        <input
          :key="fileInputKey"
          type="file"
          accept=".csv,text/csv"
          class="bankruptcy-file-input"
          @change="$emit('select-file', $event)"
        />
      </label>

      <div class="bankruptcy-form-row">
        <label class="bankruptcy-label">{{ uiStore.t("bankruptcyEnterpriseName") }}</label>
        <input
          :value="enterpriseName"
          type="text"
          :placeholder="uiStore.t('bankruptcyEnterpriseName')"
          class="bankruptcy-input"
          @input="$emit('update:enterpriseName', $event.target.value)"
        />
        <p class="bankruptcy-hint">{{ uiStore.t("bankruptcyEnterpriseNameHint") }}</p>
      </div>

      <button type="button" class="start-btn" :disabled="uploading" @click="$emit('submit')">
        {{ uploading ? uiStore.t("bankruptcyRunning") : uiStore.t("bankruptcySaveUpload") }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.bankruptcy-upload-panel {
  display: grid;
  gap: 16px;
}

.upload-card {
  margin-top: 0;
}

.scope-text {
  margin: 8px 0 0;
  font-size: 13px;
}

.bankruptcy-file-input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.bankruptcy-upload-dropzone {
  position: relative;
  display: grid;
  gap: 4px;
  margin-top: 14px;
  padding: 18px;
  border: 1px dashed rgba(47, 107, 255, 0.28);
  border-radius: 18px;
  background: rgba(47, 107, 255, 0.05);
  cursor: pointer;
}

.bankruptcy-upload-title {
  font-size: 24px;
  font-weight: 800;
  color: var(--accent);
}

.bankruptcy-upload-subtitle {
  font-size: 13px;
  color: var(--text-muted);
}

.bankruptcy-form-row {
  margin-top: 16px;
}

.bankruptcy-label {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.bankruptcy-input {
  width: 100%;
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid var(--line);
  background: #fff;
  color: var(--text);
  outline: none;
}

.bankruptcy-input:focus {
  border-color: var(--accent);
}

.bankruptcy-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
