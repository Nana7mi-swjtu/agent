import { reactive, ref } from "vue";

import { useAuthStore } from "@/entities/auth/model/store";
import { useUiStore } from "@/shared/model/ui-store";

export const useLoginForm = () => {
  const authStore = useAuthStore();
  const uiStore = useUiStore();

  const form = reactive({
    email: "",
    password: "",
  });
  const error = ref("");

  const submit = async () => {
    error.value = "";
    const result = await authStore.login(form);
    if (!result.ok) {
      error.value = result.data?.error || uiStore.t("loginFailed");
    }
    return result;
  };

  return {
    form,
    error,
    submit,
  };
};
