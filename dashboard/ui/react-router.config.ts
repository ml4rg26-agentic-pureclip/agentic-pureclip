import type { Config } from "@react-router/dev/config";

export default {
  // Pure client-side SPA — it polls the monitor's JSON API in the browser.
  ssr: false,
} satisfies Config;
