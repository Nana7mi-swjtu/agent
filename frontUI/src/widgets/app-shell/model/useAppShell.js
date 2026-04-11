import { computed } from "vue";
import { useRouter } from "vue-router";
import { storeToRefs } from "pinia";

import { useAuthStore } from "@/entities/auth/model/store";
import { useChatStore } from "@/entities/chat/model/store";
import { useWorkspaceStore } from "@/entities/workspace/model/store";
import { logoutAction } from "@/features/auth/model/actions";
import { createChatSessionAction, deleteChatSessionAction, openChatSessionAction } from "@/features/chat/model/actions";
import { selectWorkspaceRoleAndCreateSessionAction } from "@/features/workspace-context/model/actions";
import { useUiStore } from "@/shared/model/ui-store";

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
    await logoutAction({
      authStore,
      workspaceStore,
      chatStore,
      router,
    });
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
