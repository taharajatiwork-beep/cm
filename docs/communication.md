# Communication

## Principle

Telegram (and future WhatsApp/Email) are **adapters**, not the core.

```text
Telegram / Web / System
        ↓
   Channel Adapter   (Phase 3: TelegramAdapter)
        ↓
 Communication Service
        ↓
   PostgreSQL (messages, conversations, work items)
```

## Telegram (Phase 3)

- Webhook: `POST /telegram/webhook` (secret header `X-Telegram-Bot-Api-Secret-Token`)
- Account link: `POST /telegram/link-code` → user sends `/link <code>` in Telegram
- Inbound text is always stored via `CommunicationService` with `channel=TELEGRAM`
- Deterministic `EntityResolver` resolves vehicles/people; **never invents** entities
- Ambiguous vehicles → clarification reply (no WorkItem created)
- High-confidence work requests → WorkItem + Tasks through domain services
- `HttpTelegramClient` when `TELEGRAM_BOT_TOKEN` is set; otherwise `FakeTelegramClient`

## Channels (enum)

Implemented now: `TELEGRAM`, `WEB`, `SYSTEM`  
Reserved: `WHATSAPP`, `EMAIL`, `PHONE`

Business logic must not live in Telegram handlers.

## Conversation

Holds participants, channel, optional branch/team/topic, and links to WorkItem/Case/vehicle.

## Message

Stored fields:

- organization_id, conversation_id, channel, channel_message_id
- sender_id, text, message_type, reply_to_message_id, created_at

## Link to work

Important operational threads escalate into WorkItem / Case / Task via the Communication Core (and Telegram adapter for NL shortcuts).
