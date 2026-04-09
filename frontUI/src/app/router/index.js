import { createRouter, createWebHashHistory } from "vue-router";

import { bootstrapAuthenticatedAppAction } from "@/features/auth/model/actions";
import { PUBLIC_ROUTES } from "@/shared/config/routes";
import AppShellLayout from "@/layouts/AppShellLayout.vue";
import { useAuthStore } from "@/stores/auth";
import { useWorkspaceStore } from "@/stores/workspace";
import ForgotPasswordView from "@/views/auth/ForgotPasswordView.vue";
import LoginView from "@/views/auth/LoginView.vue";
import RegisterView from "@/views/auth/RegisterView.vue";
import AppBankruptcyAnalysisView from "@/views/app/AppBankruptcyAnalysisView.vue";
import AppHomeView from "@/views/app/AppHomeView.vue";
import AppChatView from "@/views/app/AppChatView.vue";
import AppProfileView from "@/views/app/AppProfileView.vue";

const routes = [
  { path: "/", redirect: "/login" },
  { path: "/login", component: LoginView, meta: { public: true } },
  { path: "/register", component: RegisterView, meta: { public: true } },
  { path: "/forgot-password", component: ForgotPasswordView, meta: { public: true } },
  {
    path: "/",
    component: AppShellLayout,
    children: [
      { path: "app", component: AppHomeView },
      { path: "chat", component: AppChatView },
      { path: "bankruptcy-analysis", component: AppBankruptcyAnalysisView },
      { path: "profile", component: AppProfileView },
    ],
    meta: { public: false },
  },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

router.beforeEach(async (to) => {
  const authStore = useAuthStore();
  const workspaceStore = useWorkspaceStore();
  await bootstrapAuthenticatedAppAction({ authStore, workspaceStore });

  if (PUBLIC_ROUTES.has(to.path)) {
    if (authStore.authenticated) {
      return "/app";
    }
    return true;
  }

  if (!authStore.authenticated) {
    return { path: "/login", query: { redirect: to.fullPath } };
  }

  return true;
});

export default router;
