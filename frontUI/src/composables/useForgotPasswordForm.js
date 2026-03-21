import { reactive, ref } from "vue";

import { useCooldown } from "@/composables/useCooldown";
import { sendForgotPasswordCode, verifyForgotPasswordCode } from "@/services/auth";
import { useUiStore } from "@/stores/ui";

export const useForgotPasswordForm = () => {
  const uiStore = useUiStore();
  const { cooldown, start } = useCooldown();

  const form = reactive({
    email: "",
    code: "",
    new_password: "",
    confirm_password: "",
  });
  const error = ref("");

  const sendCode = async () => {
    error.value = "";
    const result = await sendForgotPasswordCode({ email: form.email });
    if (!result.ok) {
      error.value = result.data?.error || uiStore.t("sendFailed");
      if (result.data?.retryAfterSeconds) {
        start(result.data.retryAfterSeconds);
      }
      return result;
    }
    start(result.data?.cooldownSeconds || 60);
    return result;
  };

  const resetPassword = async () => {
    error.value = "";
    const result = await verifyForgotPasswordCode({
      email: form.email,
      code: form.code,
      new_password: form.new_password,
      confirm_password: form.confirm_password,
    });
    if (!result.ok) {
      error.value = result.data?.error || uiStore.t("resetFailed");
    }
    return result;
  };

  return {
    form,
    error,
    cooldown,
    sendCode,
    resetPassword,
  };
};
