import { createRouter, createWebHashHistory } from "vue-router";

import { useAuthStore } from "@/entities/auth/model/store";
import { useWorkspaceStore } from "@/entities/workspace/model/store";
import { bootstrapAuthenticatedAppAction } from "@/features/auth/model/actions";
import { PUBLIC_ROUTES } from "@/shared/config/routes";
import AppShellLayout from "@/widgets/app-shell/ui/AppShellLayout.vue";

const LoginPage = () => import("@/pages/auth/LoginPage.vue");
const RegisterPage = () => import("@/pages/auth/RegisterPage.vue");
const ForgotPasswordPage = () => import("@/pages/auth/ForgotPasswordPage.vue");
const HomePage = () => import("@/pages/app/HomePage.vue");
const ChatPage = () => import("@/pages/app/ChatPage.vue");
const BankruptcyPage = () => import("@/pages/app/BankruptcyPage.vue");
const ProfilePage = () => import("@/pages/app/ProfilePage.vue");

const routes = [
  { path: "/", redirect: "/login" },
  { path: "/login", component: LoginPage, meta: { public: true } },
  { path: "/register", component: RegisterPage, meta: { public: true } },
  { path: "/forgot-password", component: ForgotPasswordPage, meta: { public: true } },
  {
    path: "/",
    component: AppShellLayout,
    children: [
      { path: "app", component: HomePage },
      { path: "chat", component: ChatPage },
      { path: "bankruptcy-analysis", component: BankruptcyPage },
      { path: "profile", component: ProfilePage },
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
