import { storeToRefs } from "pinia";

import {
  loadWorkspaceContextAction,
  selectWorkspaceRoleAction,
} from "@/features/workspace-context/model/actions";
import { useUiStore } from "@/stores/ui";
import { useWorkspaceStore } from "@/stores/workspace";

export const useWorkspaceContext = () => {
  const uiStore = useUiStore();
  const workspaceStore = useWorkspaceStore();
  const { selectedRole } = storeToRefs(workspaceStore);

  const loadContext = async () => loadWorkspaceContextAction({ workspaceStore });

  const selectRole = async (roleKey) => selectWorkspaceRoleAction({ roleKey, workspaceStore, uiStore });

  return {
    selectedRole,
    loadContext,
    selectRole,
  };
};
