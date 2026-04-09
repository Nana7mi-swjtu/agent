<script setup>
import ContentSection from "@/shared/ui/ContentSection.vue";
import BankruptcyWorkspace from "@/widgets/bankruptcy-workspace/ui/BankruptcyWorkspace.vue";
import { useUiStore } from "@/shared/model/ui-store";

const uiStore = useUiStore();
</script>

<template>
  <ContentSection :title="uiStore.t('bankruptcyAnalysis')" :subtitle="uiStore.t('bankruptcyAnalysisDesc')">
    <BankruptcyWorkspace />
  </ContentSection>
</template>
