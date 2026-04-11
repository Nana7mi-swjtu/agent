import { createApp } from "vue";
import { createPinia } from "pinia";

import App from "@/App.vue";
import router from "@/app/router";
import { useAuthStore } from "@/entities/auth/model/store";
import { useChatStore } from "@/entities/chat/model/store";
import { useWorkspaceStore } from "@/entities/workspace/model/store";
import { handleUnauthorizedAction } from "@/features/auth/model/actions";
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
