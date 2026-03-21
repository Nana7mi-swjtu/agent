import { getCsrfToken, setCsrfToken } from "@/services/api/csrf";

const WRITE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

let unauthorizedHandler = null;

const resolveBaseUrl = () => {
  const configured = import.meta.env.VITE_API_BASE_URL;
  if (typeof configured === "string" && configured.trim()) {
    return configured.trim().replace(/\/$/, "");
  }
  return "";
};

const API_BASE_URL = resolveBaseUrl();

export const setUnauthorizedHandler = (handler) => {
  unauthorizedHandler = handler;
};

export const apiRequest = async (path, options = {}) => {
  const method = String(options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  const csrfToken = getCsrfToken();

  if (WRITE_METHODS.has(method) && csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }

  let body = options.body;
  if (body && !(body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(body);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body,
    credentials: "include",
  });

  const data = await response.json().catch(() => ({}));
  if (typeof data?.csrfToken === "string") {
    setCsrfToken(data.csrfToken);
  }

  if (response.status === 401 && unauthorizedHandler) {
    unauthorizedHandler();
  }

  return {
    ok: response.ok,
    status: response.status,
    data,
  };
};
