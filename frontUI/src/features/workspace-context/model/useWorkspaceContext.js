import { storeToRefs } from "pinia";

import { useWorkspaceStore } from "@/entities/workspace/model/store";
import {
  loadWorkspaceContextAction,
  selectWorkspaceRoleAction,
} from "@/features/workspace-context/model/actions";
import { useUiStore } from "@/shared/model/ui-store";

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
