import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const apiPaths = [
  "/get_sellers",
  "/set_sellers",
  "/define_sellers",
  "/parse",
];

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_API_PROXY_TARGET;
  if (!apiTarget) {
    throw new Error("VITE_API_PROXY_TARGET is required");
  }

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: Object.fromEntries(
        apiPaths.map((path) => [path, { target: apiTarget, changeOrigin: true }]),
      ),
    },
  };
});
