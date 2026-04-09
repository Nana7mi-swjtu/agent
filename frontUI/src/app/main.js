import { createApp } from "vue";
import { createPinia } from "pinia";

import App from "@/App.vue";
import router from "@/app/router";
import { handleUnauthorizedAction } from "@/features/auth/model/actions";
import { useChatStore } from "@/stores/chat";
import { useAuthStore } from "@/stores/auth";
import { useWorkspaceStore } from "@/stores/workspace";
import { setUnauthorizedHandler } from "@/shared/api/client";
import "@/shared/styles/tokens.css";
import "@/shared/styles/base.css";
import "@/shared/styles/shell.css";

const app = createApp(App);
const pinia = createPinia();

setUnauthorizedHandler(() => {
  const authStore = useAuthStore(pinia);
  const workspaceStore = useWorkspaceStore(pinia);
  const chatStore = useChatStore(pinia);
  handleUnauthorizedAction({
    authStore,
    workspaceStore,
    chatStore,
    router,
  });
});

app.use(pinia);
app.use(router);
app.mount("#app");
