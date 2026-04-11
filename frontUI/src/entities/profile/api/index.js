import { apiRequest } from "@/shared/api/client";

export const getUserProfile = () => apiRequest("/api/user/profile");

export const updateUserProfile = (payload) =>
  apiRequest("/api/user/profile", {
    method: "PUT",
    body: payload,
  });

export const patchUserPreferences = (payload) =>
  apiRequest("/api/user/preferences", {
    method: "PATCH",
    body: payload,
  });
