import { CSRF_TOKEN_KEY } from "@/constants/storage";

export const getCsrfToken = () => localStorage.getItem(CSRF_TOKEN_KEY) || "";

export const setCsrfToken = (token) => {
  const value = String(token || "").trim();
  if (!value) {
    localStorage.removeItem(CSRF_TOKEN_KEY);
    return;
  }
  localStorage.setItem(CSRF_TOKEN_KEY, value);
};

export const clearCsrfToken = () => {
  localStorage.removeItem(CSRF_TOKEN_KEY);
};
