import { getWorkspaceContext, patchWorkspaceContext } from "@/entities/workspace/api";
import { createChatSessionAction } from "@/features/chat/model/actions";

export const loadWorkspaceContextAction = async ({ workspaceStore }) => {
  const result = await getWorkspaceContext();
  if (!result.ok) {
    workspaceStore.setContextReady();
    return result;
  }
  workspaceStore.applyContext(result.data?.data || {});
  return result;
};

export const selectWorkspaceRoleAction = async ({ roleKey, workspaceStore, uiStore }) => {
  const result = await patchWorkspaceContext(roleKey);
  if (!result.ok) {
    return {
      ok: false,
      error: result.data?.error || uiStore.t("roleSwitchFailed"),
      data: result.data,
      status: result.status,
    };
  }

  workspaceStore.applyContext(result.data?.data || {});
  return { ok: true, data: result.data, status: result.status };
};

export const selectWorkspaceRoleAndCreateSessionAction = async ({
  roleKey,
  workspaceStore,
  uiStore,
  chatStore,
  router,
}) => {
  const result = await selectWorkspaceRoleAction({ roleKey, workspaceStore, uiStore });
  if (!result.ok) {
    return result;
  }

  createChatSessionAction({
    chatStore,
    uiStore,
    workspaceStore,
    router,
    roleKey: workspaceStore.selectedRole || roleKey,
  });
  return result;
};
