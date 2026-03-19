# Cloudflare Workers AI support

## Default model

Agent Zero now ships with first-class support for Cloudflare Workers AI using Cloudflare's OpenAI-compatible API surface.

**Default recommended model:** `@cf/openai/gpt-oss-120b`

## Why this model

`@cf/openai/gpt-oss-120b` was selected as the default because Cloudflare documents it as an available Workers AI frontier reasoning model exposed through the OpenAI-compatible workflow, and it is currently the strongest broadly-available general-purpose option in the Workers AI catalog for:

- multi-step reasoning
- instruction following
- tool-oriented agent workflows
- reliable chat completion behavior through the OpenAI-compatible endpoint

If you need to override it, every credential entry in the UI can use a different Workers AI model.

## Setup

1. Open **Settings → External Services → Cloudflare Workers AI**.
2. Add a credential with:
   - Cloudflare Account ID
   - Workers AI API key
   - model name (defaults to `@cf/openai/gpt-oss-120b`)
   - enabled flag
3. Save the credential.
4. Optionally click **Test** to validate the credential.
5. Set any Agent Zero model provider field, such as **Chat model provider**, to `Cloudflare Workers AI`.
6. Keep the model name aligned with one of your configured credential models, or override per credential as needed.

## Rotation behavior

For every request sent through the Cloudflare Workers AI provider:

1. Agent Zero selects the next enabled healthy credential using round-robin.
2. If a request fails, that credential is marked unhealthy and placed into cooldown.
3. The router retries the request against the next available credential.
4. Retry delays use exponential backoff.
5. Credentials in cooldown are periodically re-tested and can recover automatically.
6. Routing decisions are logged structurally for diagnosis.

## Verification checklist

- Multiple credentials can be added from the UI.
- Credentials can be edited, deleted, and tested.
- Request routing rotates across enabled healthy credentials.
- Failed credentials are skipped until recovery checks pass.
- Cloudflare Workers AI requests use Cloudflare's account-specific OpenAI-compatible base URL.
