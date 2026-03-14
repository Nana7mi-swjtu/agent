const { createApp, ref, reactive, computed, onMounted, watch } = Vue;
const { createRouter, createWebHashHistory } = VueRouter;

const CSRF_TOKEN_KEY = "csrf_token";
const PREFERENCES_KEY = "user_preferences";
const SESSIONS_KEY = "workspace_chat_sessions";
const AUTH_BG_GIF_KEY = "auth_bg_gif_url";
const DEFAULT_AUTH_BG_GIF_URL = "/docs/蓝色科粒子光效舞台.gif";

const getAuthBgGifUrl = () => {
  const globalValue = window.AUTH_BG_GIF_URL;
  if (typeof globalValue === "string" && globalValue.trim()) {
    return globalValue.trim();
  }
  const localValue = localStorage.getItem(AUTH_BG_GIF_KEY) || "";
  return localValue.trim() || DEFAULT_AUTH_BG_GIF_URL;
};

const getAuthHeroStyle = () => {
  const url = getAuthBgGifUrl();
  return url ? { backgroundImage: `url('${url}')` } : {};
};

const hasAuthBgGif = () => Boolean(getAuthBgGifUrl());
const setAuthBgGifUrl = (url) => {
  const value = String(url || "").trim();
  if (!value) {
    localStorage.removeItem(AUTH_BG_GIF_KEY);
    return;
  }
  localStorage.setItem(AUTH_BG_GIF_KEY, value);
};

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
    authWelcomeBack: "欢迎回来",
    needAccount: "需要账号？",
    createAccount: "创建账号",
    joinAgentStudio: "加入 Agent Studio",
    alreadyHaveAccount: "已有账号？",
    resetByEmail: "通过邮箱验证码重置密码",
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
    authBgGifUrlLabel: "登录页背景动图 URL",
    authBgGifUrlHint: "支持 GIF/WebP/MP4 直链，留空则使用默认背景。",
    clearAuthBg: "清除背景",
    emailLabel: "邮箱",
    passwordLabel: "密码",
    confirmPasswordLabel: "确认密码",
    codeLabel: "验证码",
    sendCode: "发送验证码",
    resendCountdown: "后可重发",
    completeRegister: "完成注册",
    resetPasswordButton: "重置密码",
    uploadAvatar: "上传头像",
    avatarCompressHint: "前端会先压缩图片再上传。",
    nicknameLabel: "昵称",
    nicknameHint: "支持中英文、数字、下划线、空格、连字符，2-32 个字符",
    registerEmailLabel: "注册邮箱",
    emailFormatOk: "邮箱格式合法",
    emailFormatBad: "邮箱格式不合法",
    emailFormatInvalid: "邮箱格式异常",
    oldPasswordLabel: "旧密码",
    newPasswordLabel: "新密码",
    confirmNewPasswordLabel: "确认新密码",
    passwordStrengthLabel: "密码强度",
    saveAccountButton: "保存账户",
    nicknameInvalidError: "昵称格式不合法",
    passwordOldNewRequired: "修改密码时必须填写旧密码和新密码",
    passwordNotMatch: "两次新密码不一致",
    passwordTooShortClient: "新密码至少 8 位",
    avatarProcessFailed: "头像处理失败",
    profileSaveFailed: "保存失败",
    profileSaveSuccess: "保存成功",
    preferencesSaveFailed: "偏好保存失败",
    roleSaveFailed: "角色保存失败",
    roleSwitchFailed: "角色切换失败",
    needLoginFirst: "请先登录",
    loadFailed: "加载失败",
    loginFailed: "登录失败",
    sendFailed: "发送失败",
    registerFailed: "注册失败",
    registerSuccess: "注册成功，请登录",
    resetFailed: "重置失败",
    resetSuccess: "密码已重置，请登录",
  },
  "en-US": {
    login: "Login",
    register: "Register",
    forgotPassword: "Forgot Password",
    authWelcomeBack: "Welcome back",
    needAccount: "Need an account?",
    createAccount: "Create one",
    joinAgentStudio: "Join Agent Studio",
    alreadyHaveAccount: "Already have an account?",
    resetByEmail: "Reset your password with an email code",
    logout: "Log out",
    profile: "Profile",
    workspace: "Workspace",
    roleSelection: "Choose Role",
    roleSelectionDesc:
      "Select your mode, then the Agent prompt will be loaded accordingly.",
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
    authBgGifUrlLabel: "Login Background GIF URL",
    authBgGifUrlHint: "Supports direct GIF/WebP/MP4 links. Leave empty for default.",
    clearAuthBg: "Clear Background",
    emailLabel: "Email",
    passwordLabel: "Password",
    confirmPasswordLabel: "Confirm Password",
    codeLabel: "Verification code",
    sendCode: "Send code",
    resendCountdown: "until you can resend",
    completeRegister: "Complete registration",
    resetPasswordButton: "Reset password",
    uploadAvatar: "Upload avatar",
    avatarCompressHint: "The frontend will compress the image before uploading.",
    nicknameLabel: "Nickname",
    nicknameHint:
      "Supports letters, numbers, underscore, spaces and hyphen, 2-32 characters.",
    registerEmailLabel: "Registered email",
    emailFormatOk: "Email format is valid",
    emailFormatBad: "Email format is invalid",
    emailFormatInvalid: "Email format is abnormal",
    oldPasswordLabel: "Old password",
    newPasswordLabel: "New password",
    confirmNewPasswordLabel: "Confirm new password",
    passwordStrengthLabel: "Password strength",
    saveAccountButton: "Save account",
    nicknameInvalidError: "Nickname format is invalid",
    passwordOldNewRequired:
      "Old and new password are both required to change password",
    passwordNotMatch: "The two new passwords do not match",
    passwordTooShortClient: "New password must be at least 8 characters",
    avatarProcessFailed: "Avatar processing failed",
    profileSaveFailed: "Save failed",
    profileSaveSuccess: "Saved successfully",
    preferencesSaveFailed: "Failed to save preferences",
    roleSaveFailed: "Failed to save role",
    roleSwitchFailed: "Failed to switch role",
    needLoginFirst: "Please log in first",
    loadFailed: "Load failed",
    loginFailed: "Login failed",
    sendFailed: "Send failed",
    registerFailed: "Registration failed",
    registerSuccess: "Registration successful, please log in",
    resetFailed: "Reset failed",
    resetSuccess: "Password has been reset, please log in",
  },
};

const t = (key) => {
  const lang = uiStore.preferences.language;
  return COPY[lang]?.[key] || COPY["zh-CN"][key] || key;
};

const getCsrfToken = () => localStorage.getItem(CSRF_TOKEN_KEY) || "";
const setCsrfToken = (token) => {
  if (!token) {
    localStorage.removeItem(CSRF_TOKEN_KEY);
    return;
  }
  localStorage.setItem(CSRF_TOKEN_KEY, token);
};

const clearAuthState = () => {
  setCsrfToken("");
  authStore.authenticated = false;
  authStore.userId = null;
  workspaceStore.ready = false;
  workspaceStore.roles = [];
  workspaceStore.selectedRole = "";
  workspaceStore.systemPrompt = "";
};

let routerRef = null;

const apiRequest = async (url, options = {}) => {
  const csrfToken = getCsrfToken();
  const method = options.method || "GET";
  const headers = new Headers(options.headers || {});

  if (["POST", "PUT", "PATCH", "DELETE"].includes(method.toUpperCase()) && csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
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

  if (typeof data?.csrfToken === "string") {
    setCsrfToken(data.csrfToken);
  }

  if (response.status === 401 && authStore.authenticated) {
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
  "zh-CN": {
    investor: "投资者",
    enterprise_manager: "企业管理者",
    regulator: "监管机构",
  },
  "en-US": {
    investor: "Investor",
    enterprise_manager: "Enterprise Manager",
    regulator: "Regulator",
  },
};

const getRoleDisplayName = (key) => {
  const lang = uiStore.preferences.language || "zh-CN";
  return ROLE_NAME_MAP[lang]?.[key] || ROLE_NAME_MAP["zh-CN"][key] || key;
};

const formatMessageTime = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(uiStore.preferences.language || "zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
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
    return { ok: false, error: result.data.error || COPY[uiStore.preferences.language].roleSwitchFailed || COPY["zh-CN"].roleSwitchFailed };
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
    ? `${getRoleDisplayName(workspaceStore.selectedRole)} 对话`
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
  if (score <= 2) return uiStore.preferences.language === "en-US" ? "Weak" : "弱";
  if (score <= 4) return uiStore.preferences.language === "en-US" ? "Medium" : "中";
  return uiStore.preferences.language === "en-US" ? "Strong" : "强";
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

        const mime = "image/jpeg";
        const ext = "jpeg";
        canvas.toBlob(
          (blob) => {
            if (!blob) {
              reject(new Error("图片压缩失败"));
              return;
            }
            resolve(new File([blob], `avatar.${ext}`, { type: mime }));
          },
          mime,
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
    <div class="auth-stage" :class="{ 'has-gif': hasGif }" :style="stageStyle">
      <div class="auth-overlay" v-if="hasGif"></div>
      <div class="auth-box">
        <h1>Agent Studio</h1>
        <p class="auth-sub">{{ i18n('authWelcomeBack') }}</p>
        <form @submit.prevent="onSubmit">
          <div class="field">
            <label>{{ i18n('emailLabel') }}</label>
            <input v-model="form.email" type="email" autocomplete="email" />
          </div>
          <div class="field">
            <label>{{ i18n('passwordLabel') }}</label>
            <input v-model="form.password" type="password" autocomplete="current-password" />
          </div>
          <div class="err-text" v-if="error">{{ error }}</div>
          <button type="submit" class="btn-primary">{{ i18n('login') }}</button>
        </form>
        <p class="auth-links" style="margin-top:16px">
          {{ i18n('needAccount') }}<router-link to="/register">{{ i18n('createAccount') }}</router-link>
          &nbsp;路&nbsp;
          <router-link to="/forgot-password">{{ i18n('forgotPassword') }}</router-link>
        </p>
      </div>
    </div>
  `,
  setup() {
    const form = reactive({ email: "", password: "" });
    const error = ref("");
    const router = VueRouter.useRouter();
    const i18n = (key) => t(key);
    const hasGif = computed(() => hasAuthBgGif());
    const stageStyle = computed(() => {
      const url = getAuthBgGifUrl();
      return url ? { '--auth-gif': `url('${url}')` } : {};
    });

    const onSubmit = async () => {
      error.value = "";
      const result = await apiRequest("/auth/login", {
        method: "POST",
        body: form,
      });
      if (!result.ok) {
        error.value = result.data.error || i18n("loginFailed");
        return;
      }
      setCsrfToken(result.data.csrfToken || "");
      await refreshSession();
      await loadWorkspaceContext();
      router.push("/app");
    };

    return { form, error, onSubmit, i18n, hasGif, stageStyle };
  },
};

const RegisterView = {
  template: `
    <div class="auth-stage" :class="{ 'has-gif': hasGif }" :style="stageStyle">
      <div class="auth-overlay" v-if="hasGif"></div>
      <div class="auth-box">
        <h1>{{ i18n('register') }}</h1>
        <p class="auth-sub">{{ i18n('joinAgentStudio') }}</p>
        <form @submit.prevent="sendCode">
          <div class="field">
            <label>{{ i18n('emailLabel') }}</label>
            <input v-model="form.email" type="email" autocomplete="email" />
          </div>
          <div class="field">
            <label>{{ i18n('passwordLabel') }}</label>
            <input v-model="form.password" type="password" autocomplete="new-password" />
          </div>
          <div class="field">
            <label>{{ i18n('confirmPasswordLabel') }}</label>
            <input v-model="form.confirm_password" type="password" autocomplete="new-password" />
          </div>
          <button type="submit" class="btn-primary" :disabled="cooldown > 0">
            {{ i18n('sendCode') }}<span v-if="cooldown > 0"> ({{ cooldown }}s)</span>
          </button>
        </form>
        <form @submit.prevent="verifyCode" style="margin-top:16px">
          <div class="field">
            <label>{{ i18n('codeLabel') }}</label>
            <input v-model="form.code" type="text" maxlength="6" placeholder="6位验证码" />
          </div>
          <button type="submit" class="btn-primary">{{ i18n('completeRegister') }}</button>
        </form>
        <div class="err-text" v-if="error">{{ error }}</div>
        <p class="auth-links" style="margin-top:16px">{{ i18n('alreadyHaveAccount') }}<router-link to="/login">{{ i18n('login') }}</router-link></p>
      </div>
    </div>
  `,
  setup() {
    const form = reactive({ email: "", password: "", confirm_password: "", code: "" });
    const error = ref("");
    const { cooldown, start } = useCooldown();
    const i18n = (key) => t(key);
    const hasGif = computed(() => hasAuthBgGif());
    const stageStyle = computed(() => {
      const url = getAuthBgGifUrl();
      return url ? { '--auth-gif': `url('${url}')` } : {};
    });

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
        error.value = result.data.error || i18n("sendFailed");
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
        error.value = result.data.error || i18n("registerFailed");
        return;
      }
      alert(i18n("registerSuccess"));
    };

    return { form, error, cooldown, sendCode, verifyCode, i18n, hasGif, stageStyle };
  },
};

const ForgotPasswordView = {
  template: `
    <div class="auth-stage" :class="{ 'has-gif': hasGif }" :style="stageStyle">
      <div class="auth-overlay" v-if="hasGif"></div>
      <div class="auth-box">
        <h1>{{ i18n('forgotPassword') }}</h1>
        <p class="auth-sub">{{ i18n('resetByEmail') }}</p>
        <form @submit.prevent="sendCode">
          <div class="field">
            <label>{{ i18n('emailLabel') }}</label>
            <input v-model="form.email" type="email" autocomplete="email" />
          </div>
          <button type="submit" class="btn-primary" :disabled="cooldown > 0">
            {{ i18n('sendCode') }}<span v-if="cooldown > 0"> ({{ cooldown }}s)</span>
          </button>
        </form>
        <form @submit.prevent="resetPassword" style="margin-top:16px">
          <div class="field">
            <label>{{ i18n('codeLabel') }}</label>
            <input v-model="form.code" type="text" maxlength="6" placeholder="6位验证码" />
          </div>
          <div class="field">
            <label>{{ i18n('newPasswordLabel') }}</label>
            <input v-model="form.new_password" type="password" autocomplete="new-password" />
          </div>
          <div class="field">
            <label>{{ i18n('confirmPasswordLabel') }}</label>
            <input v-model="form.confirm_password" type="password" autocomplete="new-password" />
          </div>
          <button type="submit" class="btn-primary">{{ i18n('resetPasswordButton') }}</button>
        </form>
        <div class="err-text" v-if="error">{{ error }}</div>
        <p class="auth-links" style="margin-top:16px"><router-link to="/login">{{ i18n('login') }}</router-link></p>
      </div>
    </div>
  `,
  setup() {
    const form = reactive({ email: "", code: "", new_password: "", confirm_password: "" });
    const error = ref("");
    const { cooldown, start } = useCooldown();
    const i18n = (key) => t(key);
    const hasGif = computed(() => hasAuthBgGif());
    const stageStyle = computed(() => {
      const url = getAuthBgGifUrl();
      return url ? { '--auth-gif': `url('${url}')` } : {};
    });

    const sendCode = async () => {
      error.value = "";
      const result = await apiRequest("/auth/forgot-password/send-code", {
        method: "POST",
        body: { email: form.email },
      });
      if (!result.ok) {
        error.value = result.data.error || i18n("sendFailed");
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
        error.value = result.data.error || i18n("resetFailed");
        return;
      }
      alert(i18n("resetSuccess"));
    };

    return { form, error, cooldown, sendCode, resetPassword, i18n, hasGif, stageStyle };
  },
};

const HomeView = {
  template: `
    <div class="content-panel">
      <div class="content-header">
        <h1>{{ i18n('roleSelection') }}</h1>
        <p>{{ i18n('roleSelectionDesc') }}</p>
      </div>

      <div v-if="!workspaceReady" class="muted-text">{{ i18n('loading') }}</div>
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

        <div class="prompt-box" v-if="systemPrompt">
          <strong>{{ i18n('promptLabel') }}</strong>
          <p style="margin:8px 0 0;font-size:13px;white-space:pre-wrap;word-break:break-word;">{{ systemPrompt }}</p>
        </div>

        <div class="msg-err" v-if="error">{{ error }}</div>

        <button type="button" class="start-btn" style="margin-top:20px" :disabled="!selectedRole" @click="toChat">
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
    <div class="dc-chat-layout">
      <div class="dc-toolbar">
        <span class="ch-hash">#</span>
        <span class="ch-name">{{ channelName }}</span>
        <span class="toolbar-divider"></span>
        <span class="ch-topic">{{ systemPrompt || '-' }}</span>
        <span class="badge-pill">{{ selectedRoleName || '-' }}</span>
      </div>

      <div class="dc-feed" ref="feedEl">
        <div v-if="!activeSession || !activeSession.messages.length" class="feed-welcome">
          <h2># {{ channelName }}</h2>
          <p>{{ i18n('inputPlaceholder') }}</p>
        </div>

        <article
          v-for="(msg, idx) in activeSession?.messages || []"
          :key="idx"
          class="msg-row"
          :class="{ 'is-first': idx === 0 || activeSession.messages[idx - 1].from !== msg.from }"
        >
          <template v-if="idx === 0 || activeSession.messages[idx - 1].from !== msg.from">
            <div class="msg-avatar" :class="{ 'is-agent': msg.from === 'agent' }">{{ msg.from === 'user' ? 'U' : 'AI' }}</div>
            <div class="msg-body">
              <div class="msg-meta">
                <span class="msg-author">{{ msg.from === 'user' ? 'You' : 'Agent Studio' }}</span>
                <span class="msg-timestamp">{{ displayTime(msg.time) }}</span>
              </div>
              <div class="msg-content">{{ msg.text }}</div>
            </div>
          </template>
          <template v-else>
            <div class="msg-avatar is-empty"></div>
            <div class="msg-body">
              <div class="msg-content">{{ msg.text }}</div>
            </div>
          </template>
        </article>
      </div>

      <div class="dc-composer">
        <div class="dc-composer-inner">
          <input
            v-model="input"
            type="text"
            :placeholder="i18n('inputPlaceholder')"
            @keydown.enter.exact.prevent="sendMessage"
          />
          <button class="dc-composer-send" :disabled="sending" @click="sendMessage">➤</button>
        </div>
        <div class="msg-err" v-if="error">{{ error }}</div>
      </div>
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
    const channelName = computed(() => {
      const title = activeSession.value?.title?.trim();
      if (title) {
        return title.toLowerCase().replace(/\s+/g, "-");
      }
      return selectedRoleName.value || "analysis-room";
    });

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
      current.messages.push({ from: "user", text, time: new Date().toISOString() });
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
        error.value = result.data.error || i18n("sendFailed");
        return;
      }

      const reply = result.data?.data?.reply || "";
      current.messages.push({ from: "agent", text: reply, time: new Date().toISOString() });
      current.updatedAt = new Date().toISOString();
      workspaceStore.systemPrompt = result.data?.data?.systemPrompt || workspaceStore.systemPrompt;
    };

    const displayTime = (value) => formatMessageTime(value);

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
      channelName,
      displayTime,
      sendMessage,
      feedEl: ref(null),
      i18n,
    };
  },
};

const ProfileView = {
  template: `
    <div class="content-panel">
      <div class="content-header">
        <h1>{{ i18n('profile') }}</h1>
        <p>Account, avatar and role preferences.</p>
      </div>

      <div v-if="loading" class="muted-text">{{ i18n('loading') }}</div>
      <div v-else class="profile-section">

        <div class="avatar-row">
          <img :src="avatarPreview || fallbackAvatar" alt="avatar" class="avatar-img" />
          <div>
            <label class="avatar-upload-btn">
              {{ i18n('uploadAvatar') }}
              <input type="file" accept="image/*" style="display:none" @change="onAvatarChange" />
            </label>
            <p class="hint-text">{{ i18n('avatarCompressHint') }}</p>
          </div>
        </div>

        <div class="preset-grid" v-if="defaultAvatars.length">
          <div v-for="url in defaultAvatars" :key="url" class="preset-item" @click="pickPreset(url)">
            <img :src="url" alt="preset" />
          </div>
        </div>

        <form @submit.prevent="saveProfile">
          <div class="form-row">
            <label>{{ i18n('nicknameLabel') }}</label>
            <input v-model="form.nickname" type="text" />
            <p class="hint-text" :style="form.nickname && !nicknameValid ? 'color:#f8716d' : ''">{{ i18n('nicknameHint') }}</p>
          </div>
          <div class="form-row">
            <label>{{ i18n('registerEmailLabel') }}</label>
            <input :value="form.email" type="email" disabled />
          </div>

          <hr style="margin:20px 0" />
          <h3 style="margin:0 0 12px;font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--text-muted);font-weight:700">{{ i18n('accountSecurity') }}</h3>
          <div class="form-row">
            <label>{{ i18n('oldPasswordLabel') }}</label>
            <input v-model="form.old_password" type="password" autocomplete="current-password" />
          </div>
          <div class="form-row">
            <label>{{ i18n('newPasswordLabel') }}</label>
            <input v-model="form.new_password" type="password" autocomplete="new-password" />
          </div>
          <div class="form-row">
            <label>{{ i18n('confirmNewPasswordLabel') }}</label>
            <input v-model="form.confirm_password" type="password" autocomplete="new-password" />
          </div>
          <p class="hint-text">{{ i18n('passwordStrengthLabel') }}：{{ passwordStrength }}</p>
          <div class="msg-err" v-if="error">{{ error }}</div>
          <div class="msg-ok" v-if="success">{{ success }}</div>
          <button type="submit" class="save-btn" :disabled="submitting">{{ i18n('saveAccountButton') }}</button>
        </form>

        <hr style="margin:28px 0 20px" />
        <h3 style="margin:0 0 12px;font-size:15px;font-weight:600">{{ i18n('preferences') }}</h3>
        <form @submit.prevent="savePreferences">
          <div class="form-row">
            <label>{{ i18n('theme') }}</label>
            <select v-model="prefForm.theme">
              <option value="light">{{ i18n('light') }}</option>
              <option value="dark">{{ i18n('dark') }}</option>
            </select>
          </div>
          <div class="form-row">
            <label>{{ i18n('language') }}</label>
            <select v-model="prefForm.language">
              <option value="zh-CN">{{ i18n('chinese') }}</option>
              <option value="en-US">{{ i18n('english') }}</option>
            </select>
          </div>
          <div class="form-row">
            <label>{{ i18n('authBgGifUrlLabel') }}</label>
            <input v-model="authBgGifUrl" type="url" placeholder="https://example.com/bg.gif" />
            <p class="hint-text">{{ i18n('authBgGifUrlHint') }}</p>
            <button
              type="button"
              class="avatar-upload-btn"
              @click="clearAuthBg"
              style="margin-top:8px"
            >{{ i18n('clearAuthBg') }}</button>
          </div>
          <div class="switch-row">
            <input v-model="prefForm.notifications.agentRun" type="checkbox" />
            <span>{{ i18n('notifyAgent') }}</span>
          </div>
          <div class="switch-row">
            <input v-model="prefForm.notifications.emailPush" type="checkbox" />
            <span>{{ i18n('notifyEmail') }}</span>
          </div>
          <div class="form-row">
            <label>{{ i18n('profileRole') }}</label>
            <select v-model="prefRole">
              <option value="investor">{{ getRoleDisplayName('investor') }}</option>
              <option value="enterprise_manager">{{ getRoleDisplayName('enterprise_manager') }}</option>
              <option value="regulator">{{ getRoleDisplayName('regulator') }}</option>
            </select>
            <p class="hint-text">{{ i18n('profileRoleHint') }}</p>
          </div>
          <button type="submit" class="save-btn">{{ i18n('savePreferences') }}</button>
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
    const authBgGifUrl = ref(getAuthBgGifUrl());

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
        error.value = profileRes.status === 401 ? i18n("needLoginFirst") : profileRes.data.error || i18n("loadFailed");
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
      authBgGifUrl.value = getAuthBgGifUrl();

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
        error.value = e.message || i18n("avatarProcessFailed");
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
        error.value = i18n("nicknameInvalidError");
        return;
      }
      if (!emailValid.value) {
        error.value = i18n("emailFormatInvalid");
        return;
      }

      const hasPasswordInput = form.old_password || form.new_password || form.confirm_password;
      if (hasPasswordInput) {
        if (!form.old_password || !form.new_password) {
          error.value = i18n("passwordOldNewRequired");
          return;
        }
        if (form.new_password !== form.confirm_password) {
          error.value = i18n("passwordNotMatch");
          return;
        }
        if (form.new_password.length < 8) {
          error.value = i18n("passwordTooShortClient");
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
        error.value = result.data.error || i18n("profileSaveFailed");
        return;
      }

      const updated = result.data.data || {};
      avatarPreview.value = updated.avatarUrl || avatarPreview.value;
      form.old_password = "";
      form.new_password = "";
      form.confirm_password = "";
      success.value = i18n("profileSaveSuccess");
    };

    const savePreferences = async () => {
      error.value = "";
      success.value = "";

      setAuthBgGifUrl(authBgGifUrl.value);
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
        error.value = prefRes.data.error || i18n("preferencesSaveFailed");
        return;
      }
      if (!roleRes.ok) {
        error.value = roleRes.data.error || i18n("roleSaveFailed");
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

    const clearAuthBg = () => {
      authBgGifUrl.value = "";
      setAuthBgGifUrl("");
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
      authBgGifUrl,
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
      clearAuthBg,
      i18n,
      getRoleDisplayName,
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

routerRef = router;

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
    const workspaceGifUrl = computed(() => getAuthBgGifUrl());

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

    const goHome = () => router.push("/app");
    const goProfile = () => router.push("/profile");

    const logout = async () => {
      await apiRequest("/auth/logout", { method: "POST" });
      clearAuthState();
      router.push("/login");
    };

    return {
      i18n,
      sidebarVisible,
      sessions,
      roles,
      selectedRole,
      workspaceGifUrl,
      activeSessionId,
      setActiveSession,
      newChat,
      quickSwitchRole,
      goHome,
      goProfile,
      logout,
      getRoleDisplayName,
    };
  },
  template: `
    <div v-if="!sidebarVisible">
      <router-view></router-view>
    </div>

    <div v-else class="dc-chrome">
      <!-- leftmost server icon strip -->
      <nav class="dc-server-bar">
        <div class="server-icon icon-home" :class="{active: $route.path==='/app'}" @click="goHome" title="主页">⚡</div>
        <div class="server-sep"></div>
        <div
          v-for="role in roles"
          :key="role.key"
          class="server-icon"
          :class="{active: selectedRole===role.key && $route.path==='/chat'}"
          @click="quickSwitchRole(role.key)"
          :title="role.name"
        >{{ role.name.slice(0,1).toUpperCase() }}</div>
      </nav>

      <!-- channel sidebar -->
      <div class="dc-sidebar">
        <div class="sidebar-guild-header">Agent Studio</div>
        <div class="sidebar-scroller">
          <div class="channel-section-header"><span class="ch-caret">▾</span>{{ i18n('switchRole') }}</div>
          <div
            v-for="role in roles"
            :key="role.key"
            class="channel-row"
            :class="{active: selectedRole===role.key && $route.path==='/chat'}"
            @click="quickSwitchRole(role.key)"
          >
            <span class="channel-hash">#</span>
            <span class="channel-row-name">{{ role.name }}</span>
          </div>

          <div class="channel-section-header" style="margin-top:16px"><span class="ch-caret">▾</span>{{ i18n('chatHistory') }}</div>
          <div
            v-for="s in sessions"
            :key="s.id"
            class="channel-row"
            :class="{active: activeSessionId===s.id}"
            @click="setActiveSession(s.id)"
          >
            <span class="channel-hash" style="font-size:13px">🕐</span>
            <span class="channel-row-name">{{ s.title }}</span>
          </div>

          <div class="channel-row" @click="newChat" style="color:var(--accent);margin-top:8px">
            <span class="channel-hash">＋</span>
            <span class="channel-row-name">{{ i18n('newChat') }}</span>
          </div>

          <div class="sidebar-gif-card" v-if="workspaceGifUrl">
            <img :src="workspaceGifUrl" alt="workspace animation" class="sidebar-gif-preview" />
            <div class="sidebar-gif-label">动态展示</div>
          </div>
        </div>

        <!-- user panel bottom -->
        <div class="sidebar-user-panel">
          <div class="user-avatar" @click="goProfile">
            A<div class="status-dot"></div>
          </div>
          <div class="user-name-block">
            <strong>User</strong>
            <small>在线</small>
          </div>
          <button class="panel-icon-btn" @click="goProfile" title="设置">⚙</button>
          <button class="panel-icon-btn" @click="logout" title="退出">⏻</button>
        </div>
      </div>

      <!-- main content area -->
      <div class="dc-main">
        <router-view></router-view>
      </div>
    </div>
  `
};

createApp(App).use(router).mount("#app");
