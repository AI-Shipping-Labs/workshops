import { defineAgent } from "eve";

export default defineAgent({
  // Routed through the Vercel AI Gateway (keyless on Vercel via OIDC),
  // same model as Option 1.
  model: "openai/gpt-5.4-mini",
});
