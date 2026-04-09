import { loadWorkspaceContextAction } from "@/features/workspace-context/model/actions";

export const bootstrapAuthenticatedAppAction = async ({ authStore, workspaceStore }) => {
  if (!authStore.ready) {
    const authenticated = await authStore.restoreSession();
    if (!authenticated) {
      workspaceStore.clearWorkspaceState();
      return { ok: true, authenticated: false };
    }
  }

  if (!authStore.authenticated) {
    workspaceStore.clearWorkspaceState();
    return { ok: true, authenticated: false };
  }

  if (!workspaceStore.ready) {
    const workspaceResult = await loadWorkspaceContextAction({ workspaceStore });
    return {
      ok: workspaceResult.ok,
      authenticated: true,
      workspaceResult,
    };
  }

  return { ok: true, authenticated: true };
};

export const invalidateSessionAction = ({ authStore, workspaceStore, chatStore }) => {
  authStore.clearSessionState();
  workspaceStore.clearWorkspaceState();
  chatStore.clearRuntimeState();
  return { ok: true };
};

export const handleUnauthorizedAction = async ({
  authStore,
  workspaceStore,
  chatStore,
  router,
}) => {
  invalidateSessionAction({ authStore, workspaceStore, chatStore });

  const currentRoute = router?.currentRoute?.value;
  if (currentRoute?.meta?.public) {
    return { ok: true, redirected: false };
  }

  const redirect = currentRoute?.fullPath || "/app";
  await router?.replace({ path: "/login", query: { redirect } });
  return { ok: true, redirected: true };
};

export const logoutAction = async ({
  authStore,
  workspaceStore,
  chatStore,
  router,
}) => {
  const result = await authStore.requestLogout();
  invalidateSessionAction({ authStore, workspaceStore, chatStore });

  if (router?.currentRoute?.value?.path !== "/login") {
    await router?.push("/login");
  }

  return result;
};
