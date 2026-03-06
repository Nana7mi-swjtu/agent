const { createApp, ref, reactive, computed, onMounted, watch } = Vue;
const { createRouter, createWebHashHistory } = VueRouter;

const TOKEN_KEY = "user_token";
const PREFERENCES_KEY = "user_preferences";
const SESSIONS_KEY = "workspace_chat_sessions";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const NICKNAME_RE = /^[\w\u4e00-\u9fff\-\s]{2,32}$/;

const DEFAULT_PREFERENCES = {
  theme: "light",
  language: "zh-CN",
  notifications: {
    agentRun: true,
    emailPush: false,
  },
};

const normalizePreferences = (raw = {}) => ({
  theme: raw.theme === "dark" ? "dark" : "light",
  language: raw.language === "en-US" ? "en-US" : "zh-CN",
  notifications: {
    agentRun:
      typeof raw.notifications?.agentRun === "boolean"
        ? raw.notifications.agentRun
        : DEFAULT_PREFERENCES.notifications.agentRun,
    emailPush:
      typeof raw.notifications?.emailPush === "boolean"
        ? raw.notifications.emailPush
        : DEFAULT_PREFERENCES.notifications.emailPush,
  },
});

const loadPreferencesFromLocal = () => {
  try {
    const raw = JSON.parse(localStorage.getItem(PREFERENCES_KEY) || "{}");
    return normalizePreferences(raw);
  } catch {
    return {
      ...DEFAULT_PREFERENCES,
      notifications: { ...DEFAULT_PREFERENCES.notifications },
    };
  }
};

const applyTheme = (theme) => {
  document.documentElement.setAttribute(
    "data-theme",
    theme === "dark" ? "dark" : "light",
  );
};

const uiStore = reactive({
  preferences: loadPreferencesFromLocal(),
});

const setPreferences = (next) => {
  const normalized = normalizePreferences(next);
  uiStore.preferences = normalized;
  localStorage.setItem(PREFERENCES_KEY, JSON.stringify(normalized));
  applyTheme(normalized.theme);
};

const mergePreferences = (patch) => {
  const current = uiStore.preferences;
  setPreferences({
    ...current,
    ...patch,
    notifications: {
      ...current.notifications,
      ...(patch.notifications || {}),
    },
  });
};

applyTheme(uiStore.preferences.theme);

const COPY = {
  "zh-CN": {
    login: "登录",
    register: "注册",
    forgotPassword: "忘记密码",
    logout: "退出登录",
    profile: "个人设置",
    workspace: "智能体工作台",
    roleSelection: "角色站位选择",
    roleSelectionDesc: "请选择你的工作模式，系统将加载对应的 Agent Prompt。",
    startChat: "开始对话",
    switchRole: "切换模式",
    chatHistory: "聊天历史",
    newChat: "新建对话",
    selectedRole: "当前模式",
    promptLabel: "System Prompt",
    inputPlaceholder: "输入你的问题...",
    send: "发送",
    noRole: "请先选择角色",
    loading: "加载中...",
    savePreferences: "保存偏好",
    savePreferencesSuccess: "偏好已保存",
    preferences: "偏好与系统设置",
    theme: "界面主题",
    language: "系统语言",
    dark: "深色",
    light: "浅色",
    chinese: "中文",
    english: "English",
    notifyAgent: "Agent 运行成功/失败系统内提醒",
    notifyEmail: "邮件推送提醒",
    accountSecurity: "账号安全",
    profileRole: "默认工作角色",
    profileRoleHint: "在这里切换后，主页和工作台都会同步此模式。",
  },
  "en-US": {
    login: "Login",
    register: "Register",
    forgotPassword: "Forgot Password",
    logout: "Log out",
    profile: "Profile",
    workspace: "Workspace",
    roleSelection: "Choose Role",
    roleSelectionDesc: "Select your mode, then the Agent prompt will be loaded accordingly.",
    startChat: "Start Chat",
    switchRole: "Switch Mode",
    chatHistory: "Chat History",
    newChat: "New Chat",
    selectedRole: "Current Role",
    promptLabel: "System Prompt",
    inputPlaceholder: "Type your question...",
    send: "Send",
    noRole: "Please choose a role first",
    loading: "Loading...",
    savePreferences: "Save Preferences",
    savePreferencesSuccess: "Preferences saved",
    preferences: "Preferences & System",
    theme: "Theme",
    language: "Language",
    dark: "Dark",
    light: "Light",
    chinese: "Chinese",
    english: "English",
    notifyAgent: "In-app notifications for Agent runs",
    notifyEmail: "Email push notifications",
    accountSecurity: "Account Security",
    profileRole: "Default Workspace Role",
    profileRoleHint: "Changes here are synchronized to home and workspace.",
  },
};

const t = (key) => {
  const lang = uiStore.preferences.language;
  return COPY[lang]?.[key] || COPY["zh-CN"][key] || key;
};

const getToken = () => localStorage.getItem(TOKEN_KEY) || "";
const setToken = (token) => {
  if (!token) {
    localStorage.removeItem(TOKEN_KEY);
    return;
  }
  localStorage.setItem(TOKEN_KEY, token);
};

const apiRequest = async (url, options = {}) => {
  const token = getToken();
  const method = options.method || "GET";
  const headers = new Headers(options.headers || {});

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let body = options.body;
  if (body && !(body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(body);
  }

  const response = await fetch(url, {
    method,
    headers,
    body,
    credentials: "include",
  });

  const data = await response.json().catch(() => ({}));

  if (response.status === 401 && authStore.isLoggedIn) {
    clearAuthState();
    if (routerRef) {
      const redirect = routerRef.currentRoute.value.fullPath || "/app";
      routerRef.replace({ path: "/login", query: { redirect } });
    }
  }

  return { ok: response.ok, status: response.status, data };
};

const authStore = reactive({
  ready: false,
  authenticated: false,
  userId: null,
});

const refreshSession = async () => {
  const result = await apiRequest("/auth/session", { method: "GET" });
  authStore.authenticated = result.ok;
  authStore.userId = result.ok ? result.data?.data?.userId || null : null;
  authStore.ready = true;
  return authStore.authenticated;
};

const ROLE_NAME_MAP = {
  investor: "投资者",
  enterprise_manager: "企业管理者",
  regulator: "监管机构",
};

const safeJson = (raw, fallback) => {
  try {
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
};

const workspaceStore = reactive({
  ready: false,
  roles: [],
  selectedRole: "",
  systemPrompt: "",
  sessions: safeJson(localStorage.getItem(SESSIONS_KEY) || "[]", []),
  activeSessionId: "",
});

const persistSessions = () => {
  localStorage.setItem(SESSIONS_KEY, JSON.stringify(workspaceStore.sessions));
};

watch(
  () => workspaceStore.sessions,
  () => persistSessions(),
  { deep: true },
);

const loadWorkspaceContext = async () => {
  const result = await apiRequest("/api/workspace/context", { method: "GET" });
  if (!result.ok) {
    workspaceStore.ready = true;
    return false;
  }

  const data = result.data?.data || {};
  workspaceStore.roles = data.roles || [];
  workspaceStore.selectedRole = data.selectedRole || "";
  workspaceStore.systemPrompt = data.systemPrompt || "";
  workspaceStore.ready = true;

  if (!workspaceStore.activeSessionId && workspaceStore.sessions.length) {
    workspaceStore.activeSessionId = workspaceStore.sessions[0].id;
  }
  return true;
};

const setWorkspaceRole = async (roleKey) => {
  const result = await apiRequest("/api/workspace/context", {
    method: "PATCH",
    body: { role: roleKey },
  });
  if (!result.ok) {
    return { ok: false, error: result.data.error || "角色切换失败" };
  }

  const data = result.data?.data || {};
  workspaceStore.roles = data.roles || workspaceStore.roles;
  workspaceStore.selectedRole = data.selectedRole || "";
  workspaceStore.systemPrompt = data.systemPrompt || "";
  return { ok: true };
};

const createSession = () => {
  const id = `s_${Date.now()}`;
  const title = workspaceStore.selectedRole
    ? `${ROLE_NAME_MAP[workspaceStore.selectedRole] || workspaceStore.selectedRole} 对话`
    : "新对话";

  const record = {
    id,
    role: workspaceStore.selectedRole,
    title,
    messages: [],
    updatedAt: new Date().toISOString(),
  };

  workspaceStore.sessions.unshift(record);
  workspaceStore.activeSessionId = id;
  return record;
};

const getActiveSession = () =>
  workspaceStore.sessions.find((x) => x.id === workspaceStore.activeSessionId) || null;

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

const getPasswordStrength = (password) => {
  let score = 0;
  if (password.length >= 8) score += 1;
  if (/[A-Z]/.test(password)) score += 1;
  if (/[a-z]/.test(password)) score += 1;
  if (/\d/.test(password)) score += 1;
  if (/[^A-Za-z0-9]/.test(password)) score += 1;
  if (score <= 2) return "弱";
  if (score <= 4) return "中";
  return "强";
};

const compressImage = (file, maxSize = 640, quality = 0.82) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        const ratio = Math.min(1, maxSize / Math.max(img.width, img.height));
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(img.width * ratio);
        canvas.height = Math.round(img.height * ratio);

        const ctx = canvas.getContext("2d");
        if (!ctx) {
          reject(new Error("无法初始化 canvas"));
          return;
        }
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

        canvas.toBlob(
          (blob) => {
            if (!blob) {
              reject(new Error("图片压缩失败"));
              return;
            }
            const ext = file.type.includes("png") ? "png" : "jpeg";
            resolve(new File([blob], `avatar.${ext}`, { type: blob.type }));
          },
          "image/jpeg",
          quality,
        );
      };
      img.onerror = () => reject(new Error("图片读取失败"));
      img.src = String(reader.result);
    };
    reader.onerror = () => reject(new Error("文件读取失败"));
    reader.readAsDataURL(file);
  });

const LoginView = {
  template: `
    <div class="container auth-box">
      <h2>{{ i18n('login') }}</h2>
      <form @submit.prevent="onSubmit">
        <label>邮箱<input v-model="form.email" type="email" /></label>
        <label>密码<input v-model="form.password" type="password" /></label>
        <button type="submit">{{ i18n('login') }}</button>
      </form>
      <p class="error" v-if="error">{{ error }}</p>
      <p class="note">
        <router-link to="/register">{{ i18n('register') }}</router-link>
        | <router-link to="/forgot-password">{{ i18n('forgotPassword') }}</router-link>
      </p>
    </div>
  `,
  setup() {
    const form = reactive({ email: "", password: "" });
    const error = ref("");
    const router = VueRouter.useRouter();
    const i18n = (key) => t(key);

    const onSubmit = async () => {
      error.value = "";
      const result = await apiRequest("/auth/login", {
        method: "POST",
        body: form,
      });
      if (!result.ok) {
        error.value = result.data.error || "登录失败";
        return;
      }
      setToken(result.data.token || "");
      await refreshSession();
      await loadWorkspaceContext();
      router.push("/app");
    };

    return { form, error, onSubmit, i18n };
  },
};

const RegisterView = {
  template: `
    <div class="container auth-box">
      <h2>{{ i18n('register') }}</h2>
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
      <p class="note"><router-link to="/login">{{ i18n('login') }}</router-link></p>
    </div>
  `,
  setup() {
    const form = reactive({ email: "", password: "", confirm_password: "", code: "" });
    const error = ref("");
    const { cooldown, start } = useCooldown();
    const i18n = (key) => t(key);

    const sendCode = async () => {
      error.value = "";
      const result = await apiRequest("/auth/register/send-code", {
        method: "POST",
        body: {
          email: form.email,
          password: form.password,
          confirm_password: form.confirm_password,
        },
      });
      if (!result.ok) {
        error.value = result.data.error || "发送失败";
        if (result.data.retryAfterSeconds) start(result.data.retryAfterSeconds);
        return;
      }
      start(result.data.cooldownSeconds || 60);
    };

    const verifyCode = async () => {
      error.value = "";
      const result = await apiRequest("/auth/register/verify-code", {
        method: "POST",
        body: { email: form.email, code: form.code },
      });
      if (!result.ok) {
        error.value = result.data.error || "注册失败";
        return;
      }
      alert("注册成功，请登录");
    };

    return { form, error, cooldown, sendCode, verifyCode, i18n };
  },
};

const ForgotPasswordView = {
  template: `
    <div class="container auth-box">
      <h2>{{ i18n('forgotPassword') }}</h2>
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
      <p class="note"><router-link to="/login">{{ i18n('login') }}</router-link></p>
    </div>
  `,
  setup() {
    const form = reactive({ email: "", code: "", new_password: "", confirm_password: "" });
    const error = ref("");
    const { cooldown, start } = useCooldown();
    const i18n = (key) => t(key);

    const sendCode = async () => {
      error.value = "";
      const result = await apiRequest("/auth/forgot-password/send-code", {
        method: "POST",
        body: { email: form.email },
      });
      if (!result.ok) {
        error.value = result.data.error || "发送失败";
        if (result.data.retryAfterSeconds) start(result.data.retryAfterSeconds);
        return;
      }
      start(result.data.cooldownSeconds || 60);
    };

    const resetPassword = async () => {
      error.value = "";
      const result = await apiRequest("/auth/forgot-password/verify-code", {
        method: "POST",
        body: {
          email: form.email,
          code: form.code,
          new_password: form.new_password,
          confirm_password: form.confirm_password,
        },
      });
      if (!result.ok) {
        error.value = result.data.error || "重置失败";
        return;
      }
      alert("密码已重置，请登录");
    };

    return { form, error, cooldown, sendCode, resetPassword, i18n };
  },
};

const HomeView = {
  template: `
    <div class="container">
      <h2>{{ i18n('roleSelection') }}</h2>
      <p class="note">{{ i18n('roleSelectionDesc') }}</p>

      <div v-if="!workspaceReady" class="note">{{ i18n('loading') }}</div>
      <template v-else>
        <div class="role-grid">
          <button
            v-for="role in roles"
            :key="role.key"
            type="button"
            class="role-card"
            :class="{ active: selectedRole === role.key }"
            @click="selectRole(role.key)"
          >
            <strong>{{ role.name }}</strong>
            <span>{{ role.description }}</span>
          </button>
        </div>

        <p class="note" v-if="selectedRole">
          {{ i18n('selectedRole') }}：{{ selectedRoleName }}
        </p>
        <p class="note" v-if="systemPrompt">
          <strong>{{ i18n('promptLabel') }}:</strong> {{ systemPrompt }}
        </p>
        <p class="error" v-if="error">{{ error }}</p>

        <button type="button" :disabled="!selectedRole" @click="toChat">
          {{ i18n('startChat') }}
        </button>
      </template>
    </div>
  `,
  setup() {
    const router = VueRouter.useRouter();
    const error = ref("");

    const roles = computed(() => workspaceStore.roles);
    const selectedRole = computed(() => workspaceStore.selectedRole);
    const selectedRoleName = computed(() =>
      workspaceStore.roles.find((r) => r.key === workspaceStore.selectedRole)?.name || "",
    );
    const systemPrompt = computed(() => workspaceStore.systemPrompt);
    const workspaceReady = computed(() => workspaceStore.ready);

    const i18n = (key) => t(key);

    const selectRole = async (roleKey) => {
      error.value = "";
      const result = await setWorkspaceRole(roleKey);
      if (!result.ok) {
        error.value = result.error;
      }
    };

    const toChat = () => {
      if (!workspaceStore.selectedRole) {
        error.value = i18n("noRole");
        return;
      }
      router.push("/chat");
    };

    onMounted(async () => {
      if (!workspaceStore.ready) {
        await loadWorkspaceContext();
      }
    });

    return {
      roles,
      selectedRole,
      selectedRoleName,
      systemPrompt,
      workspaceReady,
      error,
      selectRole,
      toChat,
      i18n,
    };
  },
};

const ChatView = {
  template: `
    <div class="container">
      <h2>{{ i18n('workspace') }}</h2>
      <p class="note">{{ i18n('selectedRole') }}：{{ selectedRoleName || '-' }}</p>
      <p class="note"><strong>{{ i18n('promptLabel') }}:</strong> {{ systemPrompt || '-' }}</p>

      <div class="chat-panel">
        <div v-if="!activeSession || !activeSession.messages.length" class="note">
          {{ i18n('inputPlaceholder') }}
        </div>
        <div
          v-for="(msg, idx) in activeSession?.messages || []"
          :key="idx"
          class="chat-line"
          :class="msg.from"
        >
          <strong>{{ msg.from === 'user' ? 'You' : 'Agent' }}:</strong> {{ msg.text }}
        </div>
      </div>

      <form @submit.prevent="sendMessage">
        <label>
          {{ i18n('inputPlaceholder') }}
          <input v-model="input" type="text" />
        </label>
        <button type="submit" :disabled="sending">{{ i18n('send') }}</button>
      </form>
      <p class="error" v-if="error">{{ error }}</p>
    </div>
  `,
  setup() {
    const router = VueRouter.useRouter();
    const input = ref("");
    const sending = ref(false);
    const error = ref("");

    const activeSession = computed(() => getActiveSession());
    const selectedRoleName = computed(() =>
      workspaceStore.roles.find((x) => x.key === workspaceStore.selectedRole)?.name || "",
    );
    const systemPrompt = computed(() => workspaceStore.systemPrompt);

    const i18n = (key) => t(key);

    const ensureSession = () => {
      let current = getActiveSession();
      if (!current) {
        current = createSession();
      }
      return current;
    };

    const sendMessage = async () => {
      error.value = "";
      if (!workspaceStore.selectedRole) {
        error.value = i18n("noRole");
        router.push("/app");
        return;
      }

      const text = input.value.trim();
      if (!text) return;

      const current = ensureSession();
      current.role = workspaceStore.selectedRole;
      current.messages.push({ from: "user", text });
      current.updatedAt = new Date().toISOString();
      if (current.messages.length === 1) {
        current.title = text.slice(0, 20) || current.title;
      }
      input.value = "";
      sending.value = true;

      const result = await apiRequest("/api/workspace/chat", {
        method: "POST",
        body: { message: text },
      });
      sending.value = false;

      if (!result.ok) {
        error.value = result.data.error || "发送失败";
        return;
      }

      const reply = result.data?.data?.reply || "";
      current.messages.push({ from: "agent", text: reply });
      current.updatedAt = new Date().toISOString();
      workspaceStore.systemPrompt = result.data?.data?.systemPrompt || workspaceStore.systemPrompt;
    };

    onMounted(async () => {
      if (!workspaceStore.ready) {
        await loadWorkspaceContext();
      }
      if (!workspaceStore.selectedRole) {
        router.push("/app");
      }
      if (!workspaceStore.activeSessionId && workspaceStore.sessions.length) {
        workspaceStore.activeSessionId = workspaceStore.sessions[0].id;
      }
    });

    return {
      input,
      sending,
      error,
      activeSession,
      selectedRoleName,
      systemPrompt,
      sendMessage,
      i18n,
    };
  },
};

const ProfileView = {
  template: `
    <div class="container">
      <h2>{{ i18n('profile') }}</h2>

      <div v-if="loading">{{ i18n('loading') }}</div>
      <div v-else>
        <div class="avatar-block">
          <img :src="avatarPreview || fallbackAvatar" alt="avatar" class="avatar" />
          <label class="file-label">
            上传头像
            <input type="file" accept="image/*" @change="onAvatarChange" />
          </label>
          <p class="note">前端会先压缩图片再上传。</p>
        </div>

        <div class="preset-grid" v-if="defaultAvatars.length">
          <button
            v-for="url in defaultAvatars"
            :key="url"
            type="button"
            class="avatar-item"
            @click="pickPreset(url)"
          >
            <img :src="url" alt="preset avatar" />
          </button>
        </div>

        <form @submit.prevent="saveProfile">
          <label>
            昵称
            <input v-model="form.nickname" type="text" />
          </label>
          <p class="note" :class="{ error: form.nickname && !nicknameValid }">
            支持中英文、数字、下划线、空格、连字符，2-32 个字符
          </p>

          <label>
            注册邮箱
            <input :value="form.email" type="email" disabled />
          </label>
          <p class="note" :class="{ error: form.email && !emailValid }">
            {{ emailValid ? '邮箱格式合法' : '邮箱格式不合法' }}
          </p>

          <hr />
          <h3>{{ i18n('accountSecurity') }}</h3>
          <label>
            旧密码
            <input v-model="form.old_password" type="password" autocomplete="current-password" />
          </label>
          <label>
            新密码
            <input v-model="form.new_password" type="password" autocomplete="new-password" />
          </label>
          <label>
            确认新密码
            <input v-model="form.confirm_password" type="password" autocomplete="new-password" />
          </label>
          <p class="note">密码强度：{{ passwordStrength }}</p>
          <button type="submit" :disabled="submitting">保存账户</button>
        </form>

        <p class="error" v-if="error">{{ error }}</p>
        <p class="note" v-if="success">{{ success }}</p>

        <hr />
        <h3>{{ i18n('preferences') }}</h3>
        <form @submit.prevent="savePreferences">
          <label>
            {{ i18n('theme') }}
            <select v-model="prefForm.theme">
              <option value="light">{{ i18n('light') }}</option>
              <option value="dark">{{ i18n('dark') }}</option>
            </select>
          </label>

          <label>
            {{ i18n('language') }}
            <select v-model="prefForm.language">
              <option value="zh-CN">{{ i18n('chinese') }}</option>
              <option value="en-US">{{ i18n('english') }}</option>
            </select>
          </label>

          <label class="switch-line">
            <input v-model="prefForm.notifications.agentRun" type="checkbox" />
            <span>{{ i18n('notifyAgent') }}</span>
          </label>

          <label class="switch-line">
            <input v-model="prefForm.notifications.emailPush" type="checkbox" />
            <span>{{ i18n('notifyEmail') }}</span>
          </label>

          <label>
            {{ i18n('profileRole') }}
            <select v-model="prefRole">
              <option value="investor">投资者</option>
              <option value="enterprise_manager">企业管理者</option>
              <option value="regulator">监管机构</option>
            </select>
          </label>
          <p class="note">{{ i18n('profileRoleHint') }}</p>

          <button type="submit">{{ i18n('savePreferences') }}</button>
        </form>
      </div>
    </div>
  `,
  setup() {
    const loading = ref(true);
    const submitting = ref(false);
    const error = ref("");
    const success = ref("");
    const defaultAvatars = ref([]);
    const avatarFile = ref(null);
    const avatarPreset = ref("");
    const avatarPreview = ref("");
    const prefRole = ref("investor");

    const fallbackAvatar =
      "https://api.dicebear.com/9.x/fun-emoji/svg?seed=default-profile";

    const form = reactive({
      nickname: "",
      email: "",
      old_password: "",
      new_password: "",
      confirm_password: "",
    });
    const prefForm = reactive(normalizePreferences(uiStore.preferences));

    const nicknameValid = computed(() => NICKNAME_RE.test(form.nickname || ""));
    const emailValid = computed(() => EMAIL_RE.test(form.email || ""));
    const passwordStrength = computed(() => getPasswordStrength(form.new_password || ""));

    const i18n = (key) => t(key);

    const loadProfile = async () => {
      loading.value = true;
      error.value = "";

      const [profileRes, workspaceRes] = await Promise.all([
        apiRequest("/api/user/profile", { method: "GET" }),
        apiRequest("/api/workspace/context", { method: "GET" }),
      ]);
      loading.value = false;

      if (!profileRes.ok) {
        error.value = profileRes.status === 401 ? "请先登录" : profileRes.data.error || "加载失败";
        return;
      }

      const profile = profileRes.data.data || {};
      form.nickname = profile.nickname || "";
      form.email = profile.email || "";
      avatarPreview.value = profile.avatarUrl || "";
      defaultAvatars.value = profile.defaultAvatars || [];
      if (profile.preferences) {
        setPreferences(profile.preferences);
        prefForm.theme = uiStore.preferences.theme;
        prefForm.language = uiStore.preferences.language;
        prefForm.notifications.agentRun = uiStore.preferences.notifications.agentRun;
        prefForm.notifications.emailPush = uiStore.preferences.notifications.emailPush;
      }

      if (workspaceRes.ok) {
        prefRole.value = workspaceRes.data?.data?.selectedRole || "investor";
      }
    };

    const onAvatarChange = async (event) => {
      const [rawFile] = event.target.files || [];
      if (!rawFile) return;
      error.value = "";
      success.value = "";
      try {
        const compressed = await compressImage(rawFile);
        avatarFile.value = compressed;
        avatarPreset.value = "";
        avatarPreview.value = URL.createObjectURL(compressed);
      } catch (e) {
        error.value = e.message || "头像处理失败";
      }
    };

    const pickPreset = (url) => {
      avatarPreset.value = url;
      avatarFile.value = null;
      avatarPreview.value = url;
    };

    const saveProfile = async () => {
      error.value = "";
      success.value = "";

      if (!nicknameValid.value) {
        error.value = "昵称格式不合法";
        return;
      }
      if (!emailValid.value) {
        error.value = "邮箱格式异常";
        return;
      }

      const hasPasswordInput = form.old_password || form.new_password || form.confirm_password;
      if (hasPasswordInput) {
        if (!form.old_password || !form.new_password) {
          error.value = "修改密码时必须填写旧密码和新密码";
          return;
        }
        if (form.new_password !== form.confirm_password) {
          error.value = "两次新密码不一致";
          return;
        }
        if (form.new_password.length < 8) {
          error.value = "新密码至少 8 位";
          return;
        }
      }

      const payload = new FormData();
      payload.append("nickname", form.nickname);
      if (form.old_password) payload.append("old_password", form.old_password);
      if (form.new_password) payload.append("new_password", form.new_password);
      if (avatarFile.value) payload.append("avatar", avatarFile.value);
      else if (avatarPreset.value) payload.append("avatar_preset", avatarPreset.value);

      submitting.value = true;
      const result = await apiRequest("/api/user/profile", {
        method: "PUT",
        body: payload,
      });
      submitting.value = false;

      if (!result.ok) {
        error.value = result.data.error || "保存失败";
        return;
      }

      const updated = result.data.data || {};
      avatarPreview.value = updated.avatarUrl || avatarPreview.value;
      form.old_password = "";
      form.new_password = "";
      form.confirm_password = "";
      success.value = "保存成功";
    };

    const savePreferences = async () => {
      error.value = "";
      success.value = "";

      mergePreferences(prefForm);

      const [prefRes, roleRes] = await Promise.all([
        apiRequest("/api/user/preferences", {
          method: "PATCH",
          body: {
            theme: prefForm.theme,
            language: prefForm.language,
            notifications: {
              agentRun: prefForm.notifications.agentRun,
              emailPush: prefForm.notifications.emailPush,
            },
          },
        }),
        apiRequest("/api/workspace/context", {
          method: "PATCH",
          body: { role: prefRole.value },
        }),
      ]);

      if (!prefRes.ok) {
        error.value = prefRes.data.error || "偏好保存失败";
        return;
      }
      if (!roleRes.ok) {
        error.value = roleRes.data.error || "角色保存失败";
        return;
      }

      if (prefRes.data?.data?.preferences) {
        setPreferences(prefRes.data.data.preferences);
      }
      if (roleRes.data?.data) {
        workspaceStore.selectedRole = roleRes.data.data.selectedRole || workspaceStore.selectedRole;
        workspaceStore.systemPrompt = roleRes.data.data.systemPrompt || workspaceStore.systemPrompt;
        workspaceStore.roles = roleRes.data.data.roles || workspaceStore.roles;
      }

      success.value = i18n("savePreferencesSuccess");
    };

    onMounted(loadProfile);

    return {
      loading,
      submitting,
      error,
      success,
      form,
      prefForm,
      prefRole,
      nicknameValid,
      emailValid,
      passwordStrength,
      defaultAvatars,
      avatarPreview,
      fallbackAvatar,
      onAvatarChange,
      pickPreset,
      saveProfile,
      savePreferences,
      i18n,
    };
  },
};

const routes = [
  { path: "/", redirect: "/login" },
  { path: "/login", component: LoginView },
  { path: "/register", component: RegisterView },
  { path: "/forgot-password", component: ForgotPasswordView },
  { path: "/app", component: HomeView },
  { path: "/chat", component: ChatView },
  { path: "/profile", component: ProfileView },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

const PUBLIC_ROUTES = new Set(["/login", "/register", "/forgot-password"]);

router.beforeEach(async (to) => {
  if (!authStore.ready) {
    await refreshSession();
    if (authStore.authenticated && !workspaceStore.ready) {
      await loadWorkspaceContext();
    }
  }

  if (PUBLIC_ROUTES.has(to.path)) {
    if (authStore.authenticated) return "/app";
    return true;
  }

  if (!authStore.authenticated) {
    return "/login";
  }

  if (!workspaceStore.ready) {
    await loadWorkspaceContext();
  }

  return true;
});

const App = {
  setup() {
    const router = VueRouter.useRouter();

    const i18n = (key) => t(key);

    const activeSessionId = computed(() => workspaceStore.activeSessionId);
    const sessions = computed(() => workspaceStore.sessions);
    const roles = computed(() => workspaceStore.roles);
    const selectedRole = computed(() => workspaceStore.selectedRole);

    const sidebarVisible = computed(() => authStore.authenticated);

    const setActiveSession = (id) => {
      workspaceStore.activeSessionId = id;
      if (router.currentRoute.value.path !== "/chat") {
        router.push("/chat");
      }
    };

    const newChat = () => {
      createSession();
      router.push("/chat");
    };

    const quickSwitchRole = async (roleKey) => {
      const result = await setWorkspaceRole(roleKey);
      if (!result.ok) {
        return;
      }
      if (router.currentRoute.value.path !== "/app") {
        router.push("/app");
      }
    };

    const goProfile = () => router.push("/profile");

    const logout = async () => {
      await apiRequest("/auth/logout", { method: "POST" });
      setToken("");
      authStore.authenticated = false;
      authStore.userId = null;
      workspaceStore.ready = false;
      workspaceStore.selectedRole = "";
      workspaceStore.systemPrompt = "";
      router.push("/login");
    };

    return {
      i18n,
      sidebarVisible,
      sessions,
      roles,
      selectedRole,
      activeSessionId,
      setActiveSession,
      newChat,
      quickSwitchRole,
      goProfile,
      logout,
    };
  },
  template: `
    <div>
      <div v-if="!sidebarVisible">
        <router-view></router-view>
      </div>

      <div v-else class="ai-layout">
        <aside class="sidebar">
          <div class="sidebar-header">
            <div class="brand">
              <span class="brand-dot"></span>
              <span>Agent Studio</span>
            </div>
            <button type="button" class="ghost-btn" @click="newChat">{{ i18n('newChat') }}</button>
          </div>

          <section class="side-block">
            <h4>{{ i18n('switchRole') }}</h4>
            <div class="role-switch-list">
              <button
                type="button"
                v-for="role in roles"
                :key="role.key"
                class="role-pill"
                :class="{ active: selectedRole === role.key }"
                @click="quickSwitchRole(role.key)"
              >
                {{ role.name }}
              </button>
            </div>
          </section>

          <section class="side-block">
            <h4>{{ i18n('chatHistory') }}</h4>
            <div class="history-list">
              <button
                type="button"
                class="history-item"
                :class="{ active: activeSessionId === s.id }"
                v-for="s in sessions"
                :key="s.id"
                @click="setActiveSession(s.id)"
              >
                <strong>{{ s.title }}</strong>
                <span>{{ s.role ? (s.role === 'investor' ? '投资者' : s.role === 'enterprise_manager' ? '企业管理者' : '监管机构') : '-' }}</span>
              </button>
            </div>
          </section>

          <section class="side-actions">
            <button type="button" class="ghost-btn" @click="goProfile">{{ i18n('profile') }}</button>
            <button type="button" class="ghost-btn" @click="logout">{{ i18n('logout') }}</button>
          </section>
        </aside>

        <main class="workspace-main">
          <router-view></router-view>
        </main>
      </div>
    </div>
  `,
  setup() {
    const router = VueRouter.useRouter();

    const logout = async () => {
      await apiFetch("/auth/logout", {});
      clearAuthState();
      router.push("/login");
    };

    return { authStore, logout };
  },
};

createApp(App).use(router).mount("#app");
