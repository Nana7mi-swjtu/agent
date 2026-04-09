<script setup>
import ContentSection from "@/shared/ui/ContentSection.vue";
import { useUiStore } from "@/stores/ui";
import BankruptcyWorkspace from "@/widgets/bankruptcy-workspace/ui/BankruptcyWorkspace.vue";

const uiStore = useUiStore();
</script>

<template>
  <ContentSection :title="uiStore.t('bankruptcyAnalysis')" :subtitle="uiStore.t('bankruptcyAnalysisDesc')">
    <BankruptcyWorkspace />
  </ContentSection>
</template>
