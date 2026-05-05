import globals from "globals";

export default [
  {
    ignores: [
      ".svelte-kit/**",
      "build/**",
      "dist/**",
      "node_modules/**",
      "**/*.svelte",
      "**/*.ts",
    ],
  },
  {
    files: ["**/*.{js,mjs,cjs}"],
    languageOptions: {
      globals: globals.browser,
      ecmaVersion: "latest",
      sourceType: "module",
    },
  },
];
