import { defineConfig } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { svelteTesting } from '@testing-library/svelte/vite';
import { resolve } from 'node:path';

export default defineConfig({
	plugins: [svelte({ hot: false }), svelteTesting()],
	resolve: {
		conditions: ['browser'],
		alias: {
			$lib: resolve('./src/lib'),
			$app: resolve('./node_modules/@sveltejs/kit/src/runtime/app'),
		},
	},
	test: {
		include: ['tests/dashboard/**/*.{test,spec}.{js,ts}'],
		environment: 'jsdom',
		globals: true,
		setupFiles: ['./tests/dashboard/setup.ts'],
	},
});
