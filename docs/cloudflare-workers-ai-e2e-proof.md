# Cloudflare Workers AI live proof

This document records the live verification run completed against a real Cloudflare Workers AI account configured in the local Agent Zero runtime.

## Live artifacts

- Settings payload with the Cloudflare Workers AI section: `docs/artifacts/cloudflare-workers-ai-settings-live.json`
- Live credential list payload: `docs/artifacts/cloudflare-workers-ai-credentials-live.json`
- Live credential test result: `docs/artifacts/cloudflare-workers-ai-credential-test.json`
- Live end-to-end task result: `docs/artifacts/cloudflare-workers-ai-e2e-task.json`
- UI demo artifact: `docs/artifacts/cloudflare-workers-ai-settings-demo.svg`

## What was verified

- A real Cloudflare Workers AI credential was stored locally and masked in API/UI output.
- The credential test endpoint succeeded and marked the credential healthy.
- Agent Zero completed a real task through the Cloudflare Workers AI provider and returned a valid answer.
