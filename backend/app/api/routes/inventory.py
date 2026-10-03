from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, handle_authz
from app.api.pagination import page
from app.core.permissions import AuthorizationError, PermissionCode, require_permission
from app.db.session import get_db
from app.models.enums import VehicleStatus
from app.schemas import (
    InventoryRequestCreate,
    InventoryRequestOut,
    VehicleBranchLink,
    VehicleContextOut,
    VehicleCreate,
    VehicleHistoryOut,
    VehicleImportResult,
    VehicleOut,
    VehicleStatusChange,
)
from app.services.inventory import InventoryService
from app.services.vehicle_import import (
    build_import_template_csv,
    build_import_template_xlsx,
    parse_vehicle_file_with_errors,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.post("/vehicles", response_model=VehicleOut)
async def create_vehicle(
    body: VehicleCreate,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await InventoryService(db).create_vehicle(
            organization_id=ctx.organization_id,
            vin=body.vin,
            brand=body.brand,
            model=body.model,
            year=body.year,
            actor_id=ctx.user.id,
            actor_permissions=ctx.permissions,
            stock_number=body.stock_number,
            color=body.color,
            trim=body.trim,
            mileage=body.mileage,
            purchase_price=body.purchase_price,
            sale_price=body.sale_price,
            currency=body.currency,
            description=body.description,
            notes=body.notes,
            body_type=body.body_type,
            transmission=body.transmission,
            fuel_type=body.fuel_type,
            engine=body.engine,
            plate_number=body.plate_number,
            doors=body.doors,
            seats=body.seats,
            options=body.options,
            exterior_condition=body.exterior_condition,
            interior_condition=body.interior_condition,
            import_source=body.import_source,
            branch_id=body.branch_id,
            owner_id=body.owner_id,
            status=body.status,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e


@router.get("/vehicles/import-template")
async def download_import_template(
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    ctx: AuthContext = Depends(get_current_user),
):
    try:
        require_permission(ctx.permissions, PermissionCode.INVENTORY_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    if format == "csv":
        return Response(
            content=build_import_template_csv(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="vehicles_import_template.csv"'},
        )
    return Response(
        content=build_import_template_xlsx(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="vehicles_import_template.xlsx"'},
    )


@router.post("/vehicles/import", response_model=VehicleImportResult)
async def import_vehicles(
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.INVENTORY_WRITE)
    except AuthorizationError as e:
        raise handle_authz(e) from e

    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    from app.core.files import UploadRejected, save_upload

    try:
        save_upload(file.filename or "vehicles.csv", file.content_type, data)
    except UploadRejected as e:
        raise HTTPException(400, str(e)) from e
    try:
        payloads, parse_errors = parse_vehicle_file_with_errors(file.filename or "upload.csv", data)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    svc = InventoryService(db)
    created: list = []
    skipped = 0
    errors = list(parse_errors)
    for payload in payloads:
        existing = await svc.search_vehicles(ctx.organization_id, vin=payload["vin"])
        if existing:
            skipped += 1
            errors.append(f"VIN {payload['vin']}: already exists")
            continue
        try:
            vehicle = await svc.create_vehicle(
                organization_id=ctx.organization_id,
                actor_id=ctx.user.id,
                actor_permissions=ctx.permissions,
                **payload,
            )
            created.append(vehicle)
        except Exception as e:  # noqa: BLE001
            errors.append(f"VIN {payload.get('vin')}: {e}")
            skipped += 1

    return VehicleImportResult(
        created=len(created),
        skipped=skipped,
        errors=errors[:50],
        vehicles=created,
    )


@router.get("/vehicles", response_model=list[VehicleOut])
async def search_vehicles(
    brand: str | None = None,
    model: str | None = None,
    branch_id: UUID | None = None,
    status: VehicleStatus | None = None,
    vin: str | None = None,
    stock_number: str | None = None,
    q: str | None = Query(None, description="Free-text brand/model/vin/stock"),
    envelope: bool = False,
    cursor: str | None = None,
    limit: int = 20,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.INVENTORY_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    rows = await InventoryService(db).search_vehicles(
        ctx.organization_id,
        brand=brand,
        model=model,
        branch_id=branch_id,
        status=status,
        vin=vin,
        stock_number=stock_number,
        q=q,
        scope=ctx.scope,
    )
    if envelope:
        dumped = [VehicleOut.model_validate(row).model_dump(mode="json") for row in rows]
        return JSONResponse(page(dumped, cursor=cursor, limit=limit))
    return rows


@router.get("/vehicles/{vehicle_id}", response_model=VehicleOut)
async def get_vehicle(
    vehicle_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.INVENTORY_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    vehicle = await InventoryService(db).get_vehicle(vehicle_id)
    if not vehicle or vehicle.organization_id != ctx.organization_id:
        raise HTTPException(404, "Vehicle not found")
    return vehicle


@router.get("/vehicles/{vehicle_id}/context", response_model=VehicleContextOut)
async def vehicle_context(
    vehicle_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.INVENTORY_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    try:
        data = await InventoryService(db).vehicle_context(vehicle_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    if data["vehicle"].organization_id != ctx.organization_id:
        raise HTTPException(404, "Vehicle not found")
    return data


@router.get("/vehicles/{vehicle_id}/history", response_model=list[VehicleHistoryOut])
async def vehicle_history(
    vehicle_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.INVENTORY_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    vehicle = await InventoryService(db).get_vehicle(vehicle_id)
    if not vehicle or vehicle.organization_id != ctx.organization_id:
        raise HTTPException(404, "Vehicle not found")
    return vehicle.history


@router.post("/vehicles/{vehicle_id}/status", response_model=VehicleOut)
async def change_status(
    vehicle_id: UUID,
    body: VehicleStatusChange,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.INVENTORY_WRITE)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    vehicle = await InventoryService(db).get_vehicle(vehicle_id)
    if not vehicle or vehicle.organization_id != ctx.organization_id:
        raise HTTPException(404, "Vehicle not found")
    try:
        return await InventoryService(db).change_status(
            vehicle_id=vehicle_id,
            to_status=body.to_status,
            actor_id=ctx.user.id,
            actor_permissions=ctx.permissions,
            note=body.note,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/vehicles/{vehicle_id}/branches")
async def link_branch(
    vehicle_id: UUID,
    body: VehicleBranchLink,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.INVENTORY_WRITE)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    vehicle = await InventoryService(db).get_vehicle(vehicle_id)
    if not vehicle or vehicle.organization_id != ctx.organization_id:
        raise HTTPException(404, "Vehicle not found")
    try:
        link = await InventoryService(db).link_branch(
            vehicle_id=vehicle_id,
            branch_id=body.branch_id,
            actor_id=ctx.user.id,
            is_primary=body.is_primary,
            note=body.note,
        )
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return {"id": link.id, "branch_id": link.branch_id, "is_primary": link.is_primary}


@router.post("/requests", response_model=InventoryRequestOut)
async def create_inventory_request(
    body: InventoryRequestCreate,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await InventoryService(db).create_inventory_request(
            organization_id=ctx.organization_id,
            requesting_branch_id=body.requesting_branch_id,
            requested_by=ctx.user.id,
            subject=body.subject,
            vehicle_id=body.vehicle_id,
            target_branch_id=body.target_branch_id,
            request_type=body.request_type,
            notes=body.notes,
            work_item_id=body.work_item_id,
            case_id=body.case_id,
            actor_permissions=ctx.permissions,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e


@router.get("/vehicles/{vehicle_id}/divar")
async def vehicle_divar(
    vehicle_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    from app.models.divar import DivarListing

    rows = list(
        (
            await db.execute(
                select(DivarListing).where(
                    DivarListing.vehicle_id == vehicle_id,
                    DivarListing.organization_id == ctx.organization_id,
                )
            )
        ).scalars()
    )
    return [
        {
            "id": str(row.id),
            "status": row.status,
            "divar_task_id": row.divar_task_id,
            "last_error": row.last_error,
            "title": row.title,
        }
        for row in rows
    ]
