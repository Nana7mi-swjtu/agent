# frontUI

Vue 3 + Vite frontend for this project.

## API / CORS contract

Persistent setup (recommended):

1. Keep `frontUI/.env.development` with:
   `VITE_API_BASE_URL=http://127.0.0.1:8000`
2. Run `npm run dev` in `frontUI`.
3. Open `http://127.0.0.1:4273/#/login`.

`npm run dev` will load `.env.development` automatically, so no per-run command override is needed.

Environment behavior:

- Development (recommended): set `VITE_API_BASE_URL` to backend origin (`http://127.0.0.1:8000`).
- Production same-origin deployment: leave `VITE_API_BASE_URL` empty to use relative paths.
- Production cross-origin deployment: set `VITE_API_BASE_URL` to API origin and configure backend CORS whitelist.

Runtime expectations:

- `credentials: "include"` is always sent for API requests.
- Write methods (`POST`, `PUT`, `PATCH`, `DELETE`) attach `X-CSRF-Token` when available.
- `401` responses trigger auth state cleanup and redirect to `/login` for protected routes.
- Backend must allow frontend origin via CORS and include `X-CSRF-Token` in allowed headers.

If `VITE_API_BASE_URL` is empty, requests use same-origin relative paths.
This template should help get you started developing with Vue 3 in Vite.

## Recommended IDE Setup

[VS Code](https://code.visualstudio.com/) + [Vue (Official)](https://marketplace.visualstudio.com/items?itemName=Vue.volar) (and disable Vetur).

## Recommended Browser Setup

- Chromium-based browsers (Chrome, Edge, Brave, etc.):
  - [Vue.js devtools](https://chromewebstore.google.com/detail/vuejs-devtools/nhdogjmejiglipccpnnnanhbledajbpd)
  - [Turn on Custom Object Formatter in Chrome DevTools](http://bit.ly/object-formatters)
- Firefox:
  - [Vue.js devtools](https://addons.mozilla.org/en-US/firefox/addon/vue-js-devtools/)
  - [Turn on Custom Object Formatter in Firefox DevTools](https://fxdx.dev/firefox-devtools-custom-object-formatters/)

## Customize configuration

See [Vite Configuration Reference](https://vite.dev/config/).

## Project Setup

```sh
npm install
```

### Compile and Hot-Reload for Development

```sh
npm run dev
```

### Compile and Minify for Production

```sh
npm run build
```
