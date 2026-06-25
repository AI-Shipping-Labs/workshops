import { eveChannel } from "eve/channels/eve";
import { localDev, none, vercelOidc } from "eve/channels/auth";

export default eveChannel({
  auth: [
    // Open on localhost for `eve dev` and the REPL; ignored in production.
    localDev(),
    // Lets the eve TUI and your Vercel deployments reach the deployed agent.
    vercelOidc(),
    // Public demo: anyone with the URL can use the agent (and spend gateway
    // credits). Swap for an auth provider (Auth.js, Clerk, …) to lock it down.
    none(),
  ],
});
