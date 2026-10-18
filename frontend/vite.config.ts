import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
export default defineConfig({
  plugins: [react()],
  // Preserve the browser-facing Host so the API can compare it with Origin.
  // Vite's string shorthand enables changeOrigin and breaks same-origin writes.
  server: { proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false } } },
  test: { environment: 'jsdom', pool: 'forks', execArgv: ['--no-experimental-webstorage'], setupFiles: ['./tests/setup.ts'], clearMocks: true },
});
