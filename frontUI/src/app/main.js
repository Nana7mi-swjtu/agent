import { createApp } from "vue";
import { createPinia } from "pinia";

import App from "@/App.vue";
import router from "@/app/router";
import { useAuthStore } from "@/stores/auth";
import { setUnauthorizedHandler } from "@/shared/api/client";
import "@/shared/styles/tokens.css";
import "@/shared/styles/base.css";
import "@/shared/styles/shell.css";

const app = createApp(App);
const pinia = createPinia();

setUnauthorizedHandler(() => {
  const authStore = useAuthStore(pinia);
  authStore.clearSession();
  const currentRoute = router.currentRoute.value;
  if (currentRoute.meta?.public) {
    return;
  }

  const redirect = currentRoute.fullPath || "/app";
  router.replace({ path: "/login", query: { redirect } });
});

app.use(pinia);
app.use(router);
app.mount("#app");
