import { apiRequest } from "@/services/api/client";

export const sendRegisterCode = (payload) =>
  apiRequest("/auth/register/send-code", {
    method: "POST",
    body: payload,
  });

export const verifyRegisterCode = (payload) =>
  apiRequest("/auth/register/verify-code", {
    method: "POST",
    body: payload,
  });

export const sendForgotPasswordCode = (payload) =>
  apiRequest("/auth/forgot-password/send-code", {
    method: "POST",
    body: payload,
  });

export const verifyForgotPasswordCode = (payload) =>
  apiRequest("/auth/forgot-password/verify-code", {
    method: "POST",
    body: payload,
  });
