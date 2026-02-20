const { createApp, ref, reactive } = Vue;
const { createRouter, createWebHashHistory } = VueRouter;

const apiFetch = async (url, payload) => {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  return { ok: response.ok, status: response.status, data };
};

const useCooldown = () => {
  const cooldown = ref(0);
  let timer = null;

  const start = (seconds) => {
    cooldown.value = seconds;
    if (timer) {
      clearInterval(timer);
    }
    timer = setInterval(() => {
      cooldown.value -= 1;
      if (cooldown.value <= 0) {
        clearInterval(timer);
        timer = null;
      }
    }, 1000);
  };

  return { cooldown, start };
};

const LoginView = {
  template: `
    <div class="container">
      <h2>登录</h2>
      <form @submit.prevent="onSubmit">
        <label>邮箱<input v-model="form.email" type="email" /></label>
        <label>密码<input v-model="form.password" type="password" /></label>
        <button type="submit">登录</button>
      </form>
      <p class="error" v-if="error">{{ error }}</p>
      <p class="note">
        <router-link to="/register">注册</router-link>
        | <router-link to="/forgot-password">忘记密码</router-link>
      </p>
    </div>
  `,
  setup() {
    const form = reactive({ email: "", password: "" });
    const error = ref("");
    const router = VueRouter.useRouter();

    const onSubmit = async () => {
      error.value = "";
      const result = await apiFetch("/auth/login", form);
      if (!result.ok) {
        error.value = result.data.error || "登录失败";
        return;
      }
      router.push("/app");
    };

    return { form, error, onSubmit };
  },
};

const HomeView = {
  template: `
    <div class="container">
      <h2>欢迎</h2>
      <p>这里是主页面占位符，功能即将上线。</p>
    </div>
  `,
};

const RegisterView = {
  template: `
    <div class="container">
      <h2>注册</h2>
      <form @submit.prevent="sendCode">
        <label>邮箱<input v-model="form.email" type="email" /></label>
        <label>密码<input v-model="form.password" type="password" /></label>
        <label>确认密码<input v-model="form.confirm_password" type="password" /></label>
        <button type="submit" :disabled="cooldown > 0">发送验证码</button>
        <span class="note" v-if="cooldown > 0">{{ cooldown }}s 后可重发</span>
      </form>

      <form @submit.prevent="verifyCode">
        <label>验证码<input v-model="form.code" type="text" maxlength="6" /></label>
        <button type="submit">完成注册</button>
      </form>

      <p class="error" v-if="error">{{ error }}</p>
      <p class="note"><router-link to="/login">去登录</router-link></p>
    </div>
  `,
  setup() {
    const form = reactive({
      email: "",
      password: "",
      confirm_password: "",
      code: "",
    });
    const error = ref("");
    const { cooldown, start } = useCooldown();

    const sendCode = async () => {
      error.value = "";
      const result = await apiFetch("/auth/register/send-code", {
        email: form.email,
        password: form.password,
        confirm_password: form.confirm_password,
      });
      if (!result.ok) {
        error.value = result.data.error || "发送失败";
        if (result.data.retryAfterSeconds) {
          start(result.data.retryAfterSeconds);
        }
        return;
      }
      start(result.data.cooldownSeconds || 60);
    };

    const verifyCode = async () => {
      error.value = "";
      const result = await apiFetch("/auth/register/verify-code", {
        email: form.email,
        code: form.code,
      });
      if (!result.ok) {
        error.value = result.data.error || "注册失败";
        return;
      }
      alert("注册成功，请登录");
    };

    return { form, error, cooldown, sendCode, verifyCode };
  },
};

const ForgotPasswordView = {
  template: `
    <div class="container">
      <h2>忘记密码</h2>
      <form @submit.prevent="sendCode">
        <label>邮箱<input v-model="form.email" type="email" /></label>
        <button type="submit" :disabled="cooldown > 0">发送验证码</button>
        <span class="note" v-if="cooldown > 0">{{ cooldown }}s 后可重发</span>
      </form>

      <form @submit.prevent="resetPassword">
        <label>验证码<input v-model="form.code" type="text" maxlength="6" /></label>
        <label>新密码<input v-model="form.new_password" type="password" /></label>
        <label>确认密码<input v-model="form.confirm_password" type="password" /></label>
        <button type="submit">重置密码</button>
      </form>

      <p class="error" v-if="error">{{ error }}</p>
      <p class="note"><router-link to="/login">去登录</router-link></p>
    </div>
  `,
  setup() {
    const form = reactive({
      email: "",
      code: "",
      new_password: "",
      confirm_password: "",
    });
    const error = ref("");
    const { cooldown, start } = useCooldown();

    const sendCode = async () => {
      error.value = "";
      const result = await apiFetch("/auth/forgot-password/send-code", {
        email: form.email,
      });
      if (!result.ok) {
        error.value = result.data.error || "发送失败";
        if (result.data.retryAfterSeconds) {
          start(result.data.retryAfterSeconds);
        }
        return;
      }
      start(result.data.cooldownSeconds || 60);
    };

    const resetPassword = async () => {
      error.value = "";
      const result = await apiFetch("/auth/forgot-password/verify-code", {
        email: form.email,
        code: form.code,
        new_password: form.new_password,
        confirm_password: form.confirm_password,
      });
      if (!result.ok) {
        error.value = result.data.error || "重置失败";
        return;
      }
      alert("密码已重置，请登录");
    };

    return { form, error, cooldown, sendCode, resetPassword };
  },
};

const routes = [
  { path: "/", redirect: "/login" },
  { path: "/login", component: LoginView },
  { path: "/app", component: HomeView },
  { path: "/register", component: RegisterView },
  { path: "/forgot-password", component: ForgotPasswordView },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

const App = {
  template: `
    <div>
      <nav class="container">
        <router-link to="/login">登录</router-link>
        <router-link to="/app">主页</router-link>
        <router-link to="/register">注册</router-link>
        <router-link to="/forgot-password">忘记密码</router-link>
      </nav>
      <router-view></router-view>
    </div>
  `,
};

createApp(App).use(router).mount("#app");
