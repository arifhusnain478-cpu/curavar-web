import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Dedicated Vitest config (separate from vite.config.ts so the dev/proxy setup
// stays untouched). jsdom environment for component tests; globals so tests read
// like Jest (describe/it/expect without imports).
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
