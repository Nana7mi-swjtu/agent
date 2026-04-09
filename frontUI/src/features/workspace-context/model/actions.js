import { getWorkspaceContext, patchWorkspaceContext } from "@/services/workspace";

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

  chatStore.createSession(roleKey, uiStore.getRoleDisplayName, workspaceStore.workspaceId);
  if (router.currentRoute.value.path !== "/chat") {
    router.push("/chat");
  }
  return result;
};
