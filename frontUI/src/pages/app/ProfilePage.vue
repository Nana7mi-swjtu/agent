<script setup>
import ContentSection from "@/shared/ui/ContentSection.vue";
import ProfileSettingsWorkspace from "@/widgets/profile-settings/ui/ProfileSettingsWorkspace.vue";
import { useUiStore } from "@/shared/model/ui-store";

const uiStore = useUiStore();
</script>

<template>
  <ContentSection :title="uiStore.t('profile')" :subtitle="uiStore.t('profilePageSubtitle')">
    <ProfileSettingsWorkspace />
  </ContentSection>
</template>
