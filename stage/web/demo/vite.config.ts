import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The demo build: the real app with demo/fake.ts in place of the server, in one JS file and one CSS file with every picture and font inside.
export default defineConfig({
  root: path.resolve(import.meta.dirname, '..'), // the project root, so that Tailwind finds the classes in src/
  base: './',
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, '../src') } },
  build: {
    outDir: path.resolve(import.meta.dirname, '../demo-dist'),
    emptyOutDir: true,
    assetsInlineLimit: 100_000_000,
    cssCodeSplit: false,
    rollupOptions: { input: path.resolve(import.meta.dirname, 'index.html'), output: { inlineDynamicImports: true } },
  },
})
