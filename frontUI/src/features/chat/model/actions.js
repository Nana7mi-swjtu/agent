export const openChatSessionAction = ({ sessionId, chatStore, router }) => {
  chatStore.setActiveSession(sessionId);
  if (router.currentRoute.value.path !== "/chat") {
    router.push("/chat");
  }
};

export const createChatSessionAction = ({ chatStore, uiStore, workspaceStore, router, roleKey }) => {
  const nextRole = roleKey || workspaceStore.selectedRole;
  const record = chatStore.createSession(nextRole, uiStore.getRoleDisplayName, workspaceStore.workspaceId);
  if (router.currentRoute.value.path !== "/chat") {
    router.push("/chat");
  }
  return record;
};

export const deleteChatSessionAction = ({ sessionId, chatStore }) => chatStore.deleteSession(sessionId);
