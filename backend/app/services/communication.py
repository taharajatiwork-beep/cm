from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.scope import DataScopeContext, apply_scope
from app.models import Conversation, ConversationParticipant, Message
from app.models.enums import Channel, MessageType, ParticipantRole
from app.services.audit import emit_event
from app.services.notifications import notify


class CommunicationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_conversation(
        self,
        *,
        organization_id: UUID,
        channel: Channel,
        participant_ids: list[UUID],
        topic: str | None = None,
        branch_id: UUID | None = None,
        team_id: UUID | None = None,
        work_item_id: UUID | None = None,
        case_id: UUID | None = None,
        vehicle_id: UUID | None = None,
        customer_id: UUID | None = None,
        campaign_id: UUID | None = None,
        actor_id: UUID | None = None,
    ) -> Conversation:
        conv = Conversation(
            organization_id=organization_id,
            channel=channel,
            topic=topic,
            branch_id=branch_id,
            team_id=team_id,
            work_item_id=work_item_id,
            case_id=case_id,
            vehicle_id=vehicle_id,
            customer_id=customer_id,
            campaign_id=campaign_id,
        )
        self.db.add(conv)
        await self.db.flush()
        people = list(dict.fromkeys([*participant_ids, *([actor_id] if actor_id else [])]))
        for uid in people:
            self.db.add(
                ConversationParticipant(
                    conversation_id=conv.id,
                    user_id=uid,
                    role=ParticipantRole.MEMBER,
                )
            )
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=organization_id,
            event_type="conversation.created",
            actor_id=actor_id,
            entity_type="conversation",
            entity_id=conv.id,
            payload={"topic": topic, "channel": channel.value},
        )
        return conv

    async def post_message(
        self,
        *,
        organization_id: UUID,
        conversation_id: UUID,
        sender_id: UUID,
        text: str,
        channel: Channel = Channel.WEB,
        message_type: MessageType = MessageType.TEXT,
        reply_to_message_id: UUID | None = None,
        channel_message_id: str | None = None,
    ) -> Message:
        msg = Message(
            organization_id=organization_id,
            conversation_id=conversation_id,
            channel=channel,
            channel_message_id=channel_message_id,
            sender_id=sender_id,
            text=text,
            message_type=message_type,
            reply_to_message_id=reply_to_message_id,
        )
        self.db.add(msg)
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=organization_id,
            event_type="message.sent",
            actor_id=sender_id,
            entity_type="message",
            entity_id=msg.id,
            payload={"conversation_id": str(conversation_id)},
        )
        participants = list(
            (
                await self.db.execute(
                    select(ConversationParticipant).where(
                        ConversationParticipant.conversation_id == conversation_id
                    )
                )
            ).scalars()
        )
        topic = await self.db.scalar(
            select(Conversation.topic).where(Conversation.id == conversation_id)
        )
        for person in participants:
            if person.user_id == sender_id:
                continue
            await notify(
                self.db,
                organization_id=organization_id,
                user_id=person.user_id,
                title=topic or "پیام جدید",
                body=text[:240],
                entity_type="conversation",
                entity_id=conversation_id,
            )
        return msg

    async def list_messages(self, conversation_id: UUID) -> list[Message]:
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        return list(result.scalars().all())

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        return await self.db.scalar(
            select(Conversation)
            .options(selectinload(Conversation.participants), selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id)
        )

    async def list_conversations(
        self,
        organization_id: UUID,
        *,
        work_item_id: UUID | None = None,
        case_id: UUID | None = None,
        campaign_id: UUID | None = None,
        scope: DataScopeContext | None = None,
        archived: bool = False,
        viewer_id: UUID | None = None,
    ) -> list[Conversation]:
        q = (
            select(Conversation)
            .options(selectinload(Conversation.participants))
            .where(Conversation.organization_id == organization_id)
            .order_by(Conversation.created_at.desc())
        )
        q = apply_scope(q, Conversation, scope)
        if viewer_id is not None:
            q = q.where(
                Conversation.id.in_(
                    select(ConversationParticipant.conversation_id).where(
                        ConversationParticipant.user_id == viewer_id
                    )
                )
            )
        # گفتگوهای آرشیوشده در لیست عادی دیده نمی‌شوند، مگر اینکه صراحتاً archived خواسته شود.
        if archived:
            q = q.where(Conversation.archived_at.is_not(None))
        else:
            q = q.where(Conversation.archived_at.is_(None))
        if work_item_id:
            q = q.where(Conversation.work_item_id == work_item_id)
        if case_id:
            q = q.where(Conversation.case_id == case_id)
        if campaign_id:
            q = q.where(Conversation.campaign_id == campaign_id)
        return list((await self.db.execute(q)).scalars().all())

    async def last_messages(self, conversation_ids: list[UUID]) -> dict[UUID, tuple[str, UUID | None, datetime]]:
        if not conversation_ids:
            return {}
        result = await self.db.execute(
            select(Message.conversation_id, Message.text, Message.sender_id, Message.created_at)
            .where(Message.conversation_id.in_(conversation_ids))
            .order_by(Message.created_at.desc())
        )
        found: dict[UUID, tuple[str, UUID | None, datetime]] = {}
        for conversation_id, text, sender_id, created_at in result.all():
            if conversation_id not in found and created_at is not None:
                found[conversation_id] = (text, sender_id, created_at)
        return found

    async def add_participant(
        self,
        *,
        organization_id: UUID,
        conversation_id: UUID,
        user_id: UUID,
    ) -> ConversationParticipant:
        conversation = await self.db.get(Conversation, conversation_id)
        if not conversation or conversation.organization_id != organization_id:
            raise ValueError("Conversation not found")
        existing = await self.db.scalar(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id,
            )
        )
        if existing:
            return existing
        row = ConversationParticipant(
            conversation_id=conversation_id,
            user_id=user_id,
            role=ParticipantRole.MEMBER,
        )
        self.db.add(row)
        await self.db.flush()
        return row
