import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API base URL is read from VITE_API_URL at build/dev time.
// Default: the FastAPI dev server on localhost:8000.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
