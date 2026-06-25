import { defineConfig } from "vitest/config";

export default defineConfig({
  // `resolve.tsconfigPaths` makes the `@/...` import alias work in tests.
  resolve: { tsconfigPaths: true },
  test: {
    environment: "node",
  },
});
