import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      'react-refresh/only-export-components': [
        'error',
        { allowConstantExport: true, allowExportNames: ['useAuth'] },
      ],
    },
  },
  {
    files: [
      'src/hooks/use-auth.tsx',
      'src/hooks/use-polling.ts',
      'src/pages/KeysPage.tsx',
      'src/pages/LogsPage.tsx',
      'src/pages/TokenPage.tsx',
      'src/pages/LogDetailPage.tsx',
      'src/pages/DashboardPage.tsx',
    ],
    rules: {
      // Dashboard pages intentionally kick off async API reads on mount.
      'react-hooks/set-state-in-effect': 'off',
    },
  },
])
