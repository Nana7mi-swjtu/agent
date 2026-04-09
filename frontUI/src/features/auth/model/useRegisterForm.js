import { reactive, ref } from "vue";

import { sendRegisterCode, verifyRegisterCode } from "@/features/auth/api";
import { useCooldown } from "@/features/auth/model/useCooldown";
import { useUiStore } from "@/shared/model/ui-store";

export const useRegisterForm = () => {
  const uiStore = useUiStore();
  const { cooldown, start } = useCooldown();

  const form = reactive({
    email: "",
    password: "",
    confirm_password: "",
    code: "",
  });
  const error = ref("");

  const sendCode = async () => {
    error.value = "";
    const result = await sendRegisterCode({
      email: form.email,
      password: form.password,
      confirm_password: form.confirm_password,
    });
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

  const verifyCode = async () => {
    error.value = "";
    const result = await verifyRegisterCode({
      email: form.email,
      code: form.code,
    });
    if (!result.ok) {
      error.value = result.data?.error || uiStore.t("registerFailed");
    }
    return result;
  };

  return {
    form,
    error,
    cooldown,
    sendCode,
    verifyCode,
  };
};
