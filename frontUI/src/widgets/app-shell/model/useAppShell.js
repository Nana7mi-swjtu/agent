import { computed } from "vue";
import { useRouter } from "vue-router";
import { storeToRefs } from "pinia";

import { createChatSessionAction, deleteChatSessionAction, openChatSessionAction } from "@/features/chat/model/actions";
import { selectWorkspaceRoleAndCreateSessionAction } from "@/features/workspace-context/model/actions";
import { useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";
import { useUiStore } from "@/stores/ui";
import { useWorkspaceStore } from "@/stores/workspace";

export const useAppShell = () => {
  const router = useRouter();
  const authStore = useAuthStore();
  const chatStore = useChatStore();
  const uiStore = useUiStore();
  const workspaceStore = useWorkspaceStore();

  const { sessions, activeSessionId } = storeToRefs(chatStore);
  const { roles, selectedRole, workspaceId } = storeToRefs(workspaceStore);

  const currentPath = computed(() => router.currentRoute.value.path);
  const workspaceGifUrl = computed(() => uiStore.authBgGifUrl);
  const displayName = computed(() => authStore.user?.nickname || authStore.user?.email || "User");
  const userAvatarUrl = computed(() => authStore.user?.avatarUrl || "");
  const userFallbackLetter = computed(() => {
    const source = displayName.value.trim();
    return source ? source.charAt(0).toUpperCase() : "U";
  });
  const activeSessionCount = computed(() => sessions.value.length);

  const initialize = async () => {
    await authStore.refreshUserProfile();
  };

  const openSession = (sessionId) => {
    openChatSessionAction({ sessionId, chatStore, router });
  };

  const newChat = () => {
    createChatSessionAction({ chatStore, uiStore, workspaceStore, router });
  };

  const quickSwitchRole = async (roleKey) =>
    selectWorkspaceRoleAndCreateSessionAction({
      roleKey,
      workspaceStore,
      uiStore,
      chatStore,
      router,
    });

  const removeSession = (sessionId) => {
    deleteChatSessionAction({ sessionId, chatStore });
  };

  const goHome = () => router.push("/app");
  const goBankruptcy = () => router.push("/bankruptcy-analysis");
  const goProfile = () => router.push("/profile");
  const logout = async () => {
    await authStore.logout();
    router.push("/login");
  };

  return {
    currentPath,
    roles,
    selectedRole,
    sessions,
    activeSessionId,
    workspaceId,
    workspaceGifUrl,
    displayName,
    userAvatarUrl,
    userFallbackLetter,
    activeSessionCount,
    initialize,
    openSession,
    newChat,
    quickSwitchRole,
    removeSession,
    goHome,
    goBankruptcy,
    goProfile,
    logout,
  };
};
