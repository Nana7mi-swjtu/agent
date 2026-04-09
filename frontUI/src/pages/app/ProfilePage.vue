<script setup>
import ContentSection from "@/shared/ui/ContentSection.vue";
import { useUiStore } from "@/stores/ui";
import ProfileSettingsWorkspace from "@/widgets/profile-settings/ui/ProfileSettingsWorkspace.vue";

const uiStore = useUiStore();
</script>

<template>
  <ContentSection :title="uiStore.t('profile')" subtitle="Account, avatar and role preferences.">
    <ProfileSettingsWorkspace />
  </ContentSection>
</template>
