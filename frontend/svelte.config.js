import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  compilerOptions: {
    enableSourcemap: true,
  },
  onwarn: (warning, handler) => {
    if (warning.code?.startsWith('a11y-') || warning.message?.includes('A11y:')) return;
    handler(warning);
  },
  kit: {
    adapter: adapter(),
  },
};

export default config;
