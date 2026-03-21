import { storeToRefs } from "pinia";

import { patchWorkspaceContext, getWorkspaceContext } from "@/services/workspace";
import { useUiStore } from "@/stores/ui";
import { useWorkspaceStore } from "@/stores/workspace";

export const useWorkspaceContext = () => {
  const uiStore = useUiStore();
  const workspaceStore = useWorkspaceStore();
  const { selectedRole } = storeToRefs(workspaceStore);

  const loadContext = async () => {
    const result = await getWorkspaceContext();
    if (!result.ok) {
      workspaceStore.setContextReady();
      return result;
    }
    workspaceStore.applyContext(result.data?.data || {});
    return result;
  };

  const selectRole = async (roleKey) => {
    const result = await patchWorkspaceContext(roleKey);
    if (!result.ok) {
      return {
        ok: false,
        error: result.data?.error || uiStore.t("roleSwitchFailed"),
      };
    }
    workspaceStore.applyContext(result.data?.data || {});
    return { ok: true };
  };

  return {
    selectedRole,
    loadContext,
    selectRole,
  };
};
