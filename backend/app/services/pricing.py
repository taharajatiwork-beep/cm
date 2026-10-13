"""قیمت فروش و تأیید قیمت برای ساعت پست."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import PermissionCode, require_permission, require_price_approve
from app.models import User
from app.models.inventory import Vehicle, VehiclePrice
from app.models.pricing import PostSlot
from app.services.notifications import notify
from app.services.org import get_user_permissions


MILLION = 1_000_000


class PricingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _price_approver_users(self, organization_id: UUID) -> list[User]:
        seen: set[UUID] = set()
        people: list[User] = []
        for code in (PermissionCode.PRICE_APPROVE, PermissionCode.PRICE_WRITE):
            for user in await self._users_with(organization_id, code):
                if user.id in seen:
                    continue
                perms = await get_user_permissions(self.db, user)
                if PermissionCode.PRICE_APPROVE in perms or PermissionCode.PRICE_WRITE in perms:
                    seen.add(user.id)
                    people.append(user)
        return people

    async def set_price(
        self,
        *,
        organization_id: UUID,
        vehicle_id: UUID,
        amount: int,
        actor_id: UUID,
        actor_permissions: set[str],
        note: str | None = None,
    ) -> Vehicle:
        require_price_approve(actor_permissions)
        vehicle = await self._vehicle(organization_id, vehicle_id)
        now = datetime.now(UTC)
        vehicle.sale_price = amount
        vehicle.price_updated_at = now
        vehicle.price_updated_by = actor_id
        self.db.add(
            VehiclePrice(
                organization_id=organization_id,
                vehicle_id=vehicle.id,
                amount=amount,
                actor_id=actor_id,
                note=note,
            )
        )
        slots = list(
            (
                await self.db.scalars(
                    select(PostSlot).where(
                        PostSlot.organization_id == organization_id,
                        PostSlot.vehicle_id == vehicle.id,
                        PostSlot.status == "confirmed",
                        PostSlot.post_at >= now,
                    )
                )
            ).all()
        )
        for slot in slots:
            slot.status = "needs_recheck"
            await notify(
                self.db,
                organization_id=organization_id,
                user_id=slot.requester_id,
                title="قیمت عوض شد، دوباره تأیید شود",
                body=f"{vehicle.brand} {vehicle.model} — قیمت تازه باید دوباره برای پست تأیید شود.",
                entity_type="post_slot",
                entity_id=slot.id,
            )
        await self.db.flush()
        return vehicle

    async def request_slot(
        self,
        *,
        organization_id: UUID,
        vehicle_id: UUID,
        post_at: datetime,
        requester_id: UUID,
        actor_permissions: set[str],
        slot_type: str = "video",
        channel: str | None = None,
    ) -> PostSlot:
        require_permission(actor_permissions, PermissionCode.CAMPAIGN_WRITE)
        vehicle = await self._vehicle(organization_id, vehicle_id)
        slot = PostSlot(
            organization_id=organization_id,
            vehicle_id=vehicle.id,
            post_at=post_at,
            slot_type=slot_type,
            channel=channel,
            requester_id=requester_id,
            status="requested",
        )
        self.db.add(slot)
        await self.db.flush()
        label = f"{vehicle.brand} {vehicle.model}"
        for user in await self._price_approver_users(organization_id):
            await notify(
                self.db,
                organization_id=organization_id,
                user_id=user.id,
                title="قیمت برای پست منتظر شماست",
                body=f"{label} برای {slot_type} نیاز به تأیید قیمت دارد.",
                entity_type="post_slot",
                entity_id=slot.id,
            )
        return slot

    async def queue_price_proposal(
        self,
        *,
        organization_id: UUID,
        vehicle_id: UUID,
        amount: int,
        requester_id: UUID,
    ) -> PostSlot:
        """مدیر فروش قیمت را پیشنهاد می‌دهد؛ فقط مالی ثبت می‌کند."""
        vehicle = await self._vehicle(organization_id, vehicle_id)
        slot = PostSlot(
            organization_id=organization_id,
            vehicle_id=vehicle.id,
            post_at=datetime.now(UTC),
            slot_type="price_change",
            channel="stock",
            requester_id=requester_id,
            status="requested",
            confirmed_price=amount,
        )
        self.db.add(slot)
        await self.db.flush()
        for user in await self._price_approver_users(organization_id):
            await notify(
                self.db,
                organization_id=organization_id,
                user_id=user.id,
                title="پیشنهاد قیمت موجودی",
                body=f"{vehicle.brand} {vehicle.model} — {amount // MILLION} میلیون.",
                entity_type="post_slot",
                entity_id=slot.id,
            )
        return slot

    async def confirm_slot(
        self,
        *,
        organization_id: UUID,
        slot_id: UUID,
        actor_id: UUID,
        actor_permissions: set[str],
        amount: int | None = None,
    ) -> PostSlot:
        require_price_approve(actor_permissions)
        slot = await self._slot(organization_id, slot_id)
        vehicle = await self._vehicle(organization_id, slot.vehicle_id)
        chosen = amount
        if (
            chosen is None
            and slot.slot_type == "price_change"
            and slot.status == "requested"
            and slot.confirmed_price is not None
        ):
            chosen = slot.confirmed_price
        if chosen is not None and chosen != vehicle.sale_price:
            await self.set_price(
                organization_id=organization_id,
                vehicle_id=vehicle.id,
                amount=chosen,
                actor_id=actor_id,
                actor_permissions=actor_permissions,
                note="تأیید قیمت پست",
            )
            await self.db.refresh(vehicle)
        price = vehicle.sale_price
        if price is None:
            raise ValueError("این خودرو هنوز قیمت ندارد")
        now = datetime.now(UTC)
        slot.status = "confirmed"
        slot.confirmed_price = price
        slot.confirmed_by = actor_id
        slot.confirmed_at = now
        await notify(
            self.db,
            organization_id=organization_id,
            user_id=slot.requester_id,
            title="قیمت پست تأیید شد",
            body=f"{vehicle.brand} {vehicle.model} — {price // MILLION} میلیون تومان.",
            entity_type="post_slot",
            entity_id=slot.id,
        )
        await self.db.flush()
        return slot

    async def mark_posted(
        self,
        *,
        organization_id: UUID,
        slot_id: UUID,
        actor_permissions: set[str],
    ) -> PostSlot:
        require_permission(actor_permissions, PermissionCode.CAMPAIGN_WRITE)
        slot = await self._slot(organization_id, slot_id)
        if slot.status not in ("confirmed",):
            raise ValueError("فقط پست تأییدشده را می‌توان منتشرشده کرد")
        slot.status = "posted"
        await self.db.flush()
        return slot

    async def list_slots(self, organization_id: UUID, *, day: datetime | None = None) -> list[PostSlot]:
        q = select(PostSlot).where(PostSlot.organization_id == organization_id)
        if day is not None:
            start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            q = q.where(PostSlot.post_at >= start, PostSlot.post_at < start + timedelta(days=1))
        q = q.order_by(PostSlot.post_at)
        return list((await self.db.scalars(q)).all())

    async def remind_due(self, *, now: datetime | None = None) -> int:
        """یک بار، اگر کمتر از ۶۰ دقیقه تا پست مانده و هنوز تأیید نشده."""
        now = now or datetime.now(UTC)
        horizon = now + timedelta(minutes=60)
        slots = list(
            (
                await self.db.scalars(
                    select(PostSlot).where(
                        PostSlot.status == "requested",
                        PostSlot.reminded_at.is_(None),
                        PostSlot.post_at <= horizon,
                        PostSlot.post_at >= now,
                    )
                )
            ).all()
        )
        sent = 0
        for slot in slots:
            vehicle = await self.db.get(Vehicle, slot.vehicle_id)
            label = f"{vehicle.brand} {vehicle.model}" if vehicle else "خودرو"
            targets = {slot.requester_id}
            for user in await self._price_approver_users(slot.organization_id):
                targets.add(user.id)
            for user_id in targets:
                await notify(
                    self.db,
                    organization_id=slot.organization_id,
                    user_id=user_id,
                    title="کمتر از یک ساعت تا پست مانده",
                    body=f"قیمت {label} هنوز تأیید نشده.",
                    entity_type="post_slot",
                    entity_id=slot.id,
                )
                sent += 1
            slot.reminded_at = now
        await self.db.flush()
        return sent

    async def _vehicle(self, organization_id: UUID, vehicle_id: UUID) -> Vehicle:
        vehicle = await self.db.get(Vehicle, vehicle_id)
        if not vehicle or vehicle.organization_id != organization_id:
            raise ValueError("Vehicle not found")
        return vehicle

    async def _slot(self, organization_id: UUID, slot_id: UUID) -> PostSlot:
        slot = await self.db.get(PostSlot, slot_id)
        if not slot or slot.organization_id != organization_id:
            raise ValueError("Slot not found")
        return slot

    async def _users_with(self, organization_id: UUID, code: str) -> list[User]:
        users = list(
            (
                await self.db.scalars(
                    select(User).where(
                        User.organization_id == organization_id,
                        User.is_active.is_(True),
                    )
                )
            ).all()
        )
        found = []
        for user in users:
            perms = await get_user_permissions(self.db, user)
            if code in perms or PermissionCode.ORG_ADMIN in perms:
                found.append(user)
        return found
