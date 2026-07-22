import { chromium } from "playwright-core";

const baseURL = process.env.BASE_URL || "http://localhost:4001";
const executablePath = process.env.CHROMIUM_PATH || "/snap/bin/chromium";
const browserMessages = [];
const failedRequests = [];

const browser = await chromium.launch({
  executablePath,
  headless: true,
  args: [
    "--no-sandbox",
    "--use-fake-ui-for-media-stream",
    "--use-fake-device-for-media-stream",
    "--autoplay-policy=no-user-gesture-required",
  ],
});

try {
  const context = await browser.newContext({ permissions: ["microphone"] });
  const page = await context.newPage();

  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      browserMessages.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on("requestfailed", (request) => {
    failedRequests.push(`${request.method()} ${request.url()} — ${request.failure()?.errorText}`);
  });

  const response = await page.goto(baseURL, { waitUntil: "networkidle" });
  if (!response?.ok()) throw new Error(`Page returned HTTP ${response?.status()}`);

  const voicesResponse = await page.request.get(`${baseURL}/api/elevenlabs/voices`);
  if (!voicesResponse.ok()) throw new Error(`Voices endpoint returned HTTP ${voicesResponse.status()}`);
  const voicesData = await voicesResponse.json();
  const selectedVoice = voicesData.voices.find((voice) => voice.voiceId !== voicesData.defaultVoiceId);
  if (!selectedVoice) throw new Error("No alternative voice is available for the override test.");
  await page.locator("#coach-voice").selectOption(selectedVoice.voiceId);

  const costBeforeResponse = await page.request.get(`${baseURL}/api/elevenlabs/costs`);
  if (!costBeforeResponse.ok()) throw new Error(`Costs endpoint returned HTTP ${costBeforeResponse.status()}`);
  const costBefore = await costBeforeResponse.json();

  await page.getByRole("button", { name: "Begin conversation" }).click();

  await Promise.race([
    page.getByRole("heading", { name: /Luma is speaking|I’m listening|We’re connected/ }).waitFor({ timeout: 30_000 }),
    page.locator(".conversation-card .error").waitFor({ timeout: 30_000 }).then(async () => {
      throw new Error(`UI connection error: ${await page.locator(".conversation-card .error").innerText()}`);
    }),
  ]);

  await page.locator(".message.agent").first().waitFor({ timeout: 30_000 });
  const firstAgentMessage = await page.locator(".message.agent p").first().innerText();
  if (!firstAgentMessage.trim()) throw new Error("Agent connected but sent an empty first message.");

  await page.getByRole("button", { name: "End session" }).click();
  await page.getByRole("button", { name: "Begin conversation" }).waitFor({ timeout: 10_000 });

  let costAfter = costBefore;
  const costDeadline = Date.now() + 30_000;
  while (Date.now() < costDeadline) {
    await page.waitForTimeout(2000);
    const currentResponse = await page.request.get(`${baseURL}/api/elevenlabs/costs`);
    if (!currentResponse.ok()) continue;
    costAfter = await currentResponse.json();
    if (
      costAfter.conversationCount > costBefore.conversationCount &&
      costAfter.pricedConversationCount > costBefore.pricedConversationCount
    ) break;
  }
  if (costAfter.conversationCount <= costBefore.conversationCount) {
    throw new Error("Completed session did not appear in the spending endpoint.");
  }
  if (costAfter.pricedConversationCount <= costBefore.pricedConversationCount) {
    throw new Error("Completed session appeared, but its USD cost was not available within 30 seconds.");
  }

  console.log(JSON.stringify({
    ok: true,
    connected: true,
    agentSpoke: true,
    selectedVoice: { voiceId: selectedVoice.voiceId, name: selectedVoice.name },
    firstAgentMessage,
    spend: { beforeUsd: costBefore.totalUsd, afterUsd: costAfter.totalUsd },
    browserMessages,
    failedRequests,
  }, null, 2));
} catch (error) {
  console.error(JSON.stringify({
    ok: false,
    error: error instanceof Error ? error.message : String(error),
    browserMessages,
    failedRequests,
  }, null, 2));
  process.exitCode = 1;
} finally {
  await browser.close();
}
