import { getCsrfToken, setCsrfToken } from "@/shared/api/csrf";

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
export const buildApiUrl = (path) => `${API_BASE_URL}${path}`;

export const setUnauthorizedHandler = (handler) => {
  unauthorizedHandler = handler;
};

export const notifyUnauthorized = (status) => {
  if (status === 401 && unauthorizedHandler) {
    unauthorizedHandler();
  }
};

export const buildApiRequestOptions = (options = {}) => {
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

  return {
    method,
    headers,
    body,
    credentials: "include",
  };
};

export const handleApiResponseMeta = (response, data = {}) => {
  if (typeof data?.csrfToken === "string") {
    setCsrfToken(data.csrfToken);
  }

  notifyUnauthorized(response.status);
};

export const apiRequest = async (path, options = {}) => {
  const response = await fetch(buildApiUrl(path), buildApiRequestOptions(options));

  const data = await response.json().catch(() => ({}));
  handleApiResponseMeta(response, data);

  return {
    ok: response.ok,
    status: response.status,
    data,
  };
};

export const streamApiRequest = async (path, options = {}) => {
  const response = await fetch(buildApiUrl(path), buildApiRequestOptions(options));
  handleApiResponseMeta(response);
  return response;
};
