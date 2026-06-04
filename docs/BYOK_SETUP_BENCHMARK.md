# BYOK Setup Benchmark

Research completed on June 4, 2026. The benchmark used current official documentation and
browser inspection of the live TypingMind onboarding flow.

## Products Reviewed

| Product | Strong pattern | Friction or limitation |
| --- | --- | --- |
| [TypingMind](https://docs.typingmind.com/quickstart/get-started-with-typingmind) | The live app shows a first-run checklist with a direct "Enter API key to chat" action. Provider keys unlock models in the normal model picker. | Custom providers move into a separate model-management flow. |
| [Open WebUI](https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/) | A connection is described as URL plus API key, and available models are auto-detected after connection. Manual model IDs are a fallback. | The default connection screen still exposes a URL even for known providers. |
| [Cursor](https://docs.cursor.com/advanced/api-keys) | Provider keys live together in Models settings. The primary action is Verify, and verified keys immediately affect the model picker. | Provider-specific capability limits can make a verified key behave differently by feature. |
| [Jan](https://jan.ai/docs/manage-models) | Choose a provider, enter a key, then use the activated cloud models from the chat model selector. Advanced model tuning is separate. | Local and cloud model concepts share the same broader settings area. |
| [Msty](https://docs.msty.app/getting-started/onboarding) | Remote provider setup is a dedicated onboarding choice: enter a provider key and select desired models. Advanced local-provider setup is separate. | Some providers without model discovery require manual model IDs. |
| [LibreChat](https://www.librechat.ai/docs/quick_start/custom_endpoints) | Clearly distinguishes securely stored credentials, user-provided keys, and fetched models. | YAML, environment variables, endpoint fields, and restarts are appropriate for administrators, not a consumer default flow. |

## Common Patterns

- Start with a recognizable provider choice.
- Ask for one secret and use one primary action such as Connect or Verify.
- Validate immediately and show a short connected or actionable failure state.
- Populate the normal model picker automatically after a successful connection.
- Keep custom endpoints, manual model IDs, and tuning controls outside the common path.
- Explain where to obtain a key close to the key field.
- Show that a key is stored without displaying the secret again.
- Make changing or removing a connection explicit.

## Friction To Avoid

- Asking first-time users to name a profile or key.
- Showing priority, failover, enabled toggles, or multiple-key management by default.
- Asking for a base URL for providers whose endpoint is already known.
- Requiring users to type a default model before models have been fetched.
- Saving an invalid key before validation.
- Mixing connection setup, model selection, and advanced provider configuration into one dense form.
- Using static fallback model lists after live model discovery succeeds.

## Reweave Root Causes

The previous Reweave screen exposed the underlying storage model rather than the user task. It
showed profile name, provider, base URL, default model, custom models, key label, priority,
enable/disable state, profile save, key save, model refresh, and model selection at the same time.
It also saved a key before validating it, then relied on a separate model-loading request for
feedback.

## Chosen Design

The default Reweave flow is:

1. Choose a provider.
2. Paste an API key.
3. Select **Connect**.
4. Choose an automatically discovered model.

Connect validates the key by fetching the provider's current model list before saving it to the OS
keyring. A connected provider shows only a masked key, the selected model, and clear actions to
change the key, reconnect, or remove the connection. Base URL overrides and additional model IDs
remain available in a closed **Advanced settings** section.

OpenRouter is a dedicated provider option with its endpoint configured internally. Reweave does not
inspect API key prefixes to guess a provider. Unknown OpenAI-compatible services still require an
explicit Base URL.

The selected model is persisted. Refresh preserves it when it remains available and clearly marks
it unavailable when the provider no longer returns it.
