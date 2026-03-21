import { defineStore } from "pinia";
import { ref } from "vue";

export const useProfileStore = defineStore("profile", () => {
  const loading = ref(false);
  const submitting = ref(false);
  const error = ref("");
  const success = ref("");
  const profile = ref({
    nickname: "",
    email: "",
    avatarUrl: "",
    defaultAvatars: [],
  });

  const setLoading = (value) => {
    loading.value = Boolean(value);
  };

  const setSubmitting = (value) => {
    submitting.value = Boolean(value);
  };

  const setError = (message = "") => {
    error.value = String(message || "");
    if (error.value) {
      success.value = "";
    }
  };

  const setSuccess = (message = "") => {
    success.value = String(message || "");
    if (success.value) {
      error.value = "";
    }
  };

  const clearFeedback = () => {
    error.value = "";
    success.value = "";
  };

  const setProfile = (next) => {
    profile.value = {
      nickname: next?.nickname || "",
      email: next?.email || "",
      avatarUrl: next?.avatarUrl || "",
      defaultAvatars: Array.isArray(next?.defaultAvatars) ? next.defaultAvatars : [],
    };
  };

  return {
    loading,
    submitting,
    error,
    success,
    profile,
    setLoading,
    setSubmitting,
    setError,
    setSuccess,
    clearFeedback,
    setProfile,
  };
});
