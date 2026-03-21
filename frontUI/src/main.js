import { createApp } from "vue";
import { createPinia } from "pinia";

import App from "./App.vue";
import router from "./router";
import { useAuthStore } from "./stores/auth";
import { setUnauthorizedHandler } from "./services/api/client";
import "./styles/legacy.css";

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
