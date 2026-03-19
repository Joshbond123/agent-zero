# Cloudflare Workers AI verification

## What was added

- Provider integration for Cloudflare Workers AI in Agent Zero's model provider flow.
- Dedicated credential-management UI with add/edit/delete/test flows.
- Health tracking and last-status visibility.
- Round-robin credential routing with cooldown, retry, backoff, and recovery behavior.
- Tests for rotation and failover logic.

## Manual verification steps

1. Add two enabled credentials in **Settings → External Services → Cloudflare Workers AI**.
2. Confirm both rows appear with masked secrets.
3. Click **Test** on each credential and confirm health updates.
4. Set **Chat model provider** to `Cloudflare Workers AI`.
5. Send multiple prompts and inspect logs/status updates.
6. Temporarily break one credential and confirm the router skips it and serves traffic with the next healthy credential.
7. Restore the failed credential and confirm it recovers after cooldown and health re-check.

## Demo artifacts

- UI demo artifact: `docs/artifacts/cloudflare-workers-ai-settings-demo.svg`
- Provider/setup note: `docs/cloudflare-workers-ai.md`
