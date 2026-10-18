"""Evacuation shelters (FR-38..FR-40, FR-55, SR-05)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import User, require
from app.db import audit, pool

router = APIRouter(prefix="/api/v1/shelters", tags=["shelters"])
STATUS = "^(open|full|closed|unsafe)$"


class NewShelter(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    name_local: str | None = Field(default=None, max_length=160)
    district: str | None = Field(default=None, max_length=80)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    capacity: int = Field(ge=0, le=100000)
    accessible: bool = False
    accepts_livestock: bool = False
    has_medical: bool = False
    contact: str | None = Field(default=None, max_length=120)


class ShelterUpdate(BaseModel):
    status: str | None = Field(default=None, pattern=STATUS)
    occupancy: int | None = Field(default=None, ge=0, le=100000)
    capacity: int | None = Field(default=None, ge=0, le=100000)
    contact: str | None = Field(default=None, max_length=120)


SELECT = """select id, name, name_local, district, ST_X(geom) lon, ST_Y(geom) lat, capacity, occupancy, status, accessible,
                   accepts_livestock, has_medical, contact, updated_at, updated_by,
                   greatest(capacity - occupancy, 0) free_places"""


@router.get("")
async def list_shelters(lat: float | None = None, lon: float | None = None, open_only: bool = False,
                        accessible: bool = False, livestock: bool = False, limit: int = Query(200, le=1000)):
    """With lat/lon, sorted by distance. open_only applies SR-05: only open shelters with free places."""
    near = lat is not None and lon is not None
    dist = ", ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint($5, $6), 4326)::geography) / 1000 distance_km" if near else ", null::float distance_km"
    args = [open_only, accessible, livestock, limit] + ([lon, lat] if near else [])
    rows = await pool().fetch(
        f"""{SELECT}{dist} from shelters
            where ($1::bool = false or (status = 'open' and occupancy < capacity))
              and ($2::bool = false or accessible) and ($3::bool = false or accepts_livestock)
            order by {"distance_km" if near else "name"} limit $4""", *args)
    return [dict(r) for r in rows]


@router.post("")
async def create_shelter(body: NewShelter, user: User = Depends(require("operator"))):
    async with pool().acquire() as conn:
        sid = await conn.fetchval(
            """insert into shelters (name, name_local, district, geom, capacity, accessible, accepts_livestock, has_medical, contact, updated_by)
               values ($1, $2, $3, ST_SetSRID(ST_MakePoint($4, $5), 4326), $6, $7, $8, $9, $10, $11) returning id""",
            body.name, body.name_local, body.district, body.lon, body.lat, body.capacity, body.accessible,
            body.accepts_livestock, body.has_medical, body.contact, user.id)
        await audit(conn, user.id, "shelter.create", "shelter", str(sid), body.model_dump())
    return {"id": sid}


@router.patch("/{sid}")
async def update_shelter(sid: int, body: ShelterUpdate, user: User = Depends(require("operator"))):
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(400, "nothing to change")
    async with pool().acquire() as conn:
        row = await conn.fetchrow("select capacity, occupancy, status from shelters where id = $1", sid)
        if row is None:
            raise HTTPException(404, "shelter not found")
        cap = changes.get("capacity", row["capacity"])
        occ = changes.get("occupancy", row["occupancy"])
        status = changes.get("status", row["status"])
        if status == "open" and occ >= cap:
            status = "full"            # occupancy at capacity closes the shelter to new arrivals
        await conn.execute(
            """update shelters set capacity = $2, occupancy = $3, status = $4, contact = coalesce($5, contact),
                 updated_at = now(), updated_by = $6 where id = $1""", sid, cap, occ, status, changes.get("contact"), user.id)
        await audit(conn, user.id, "shelter.update", "shelter", str(sid), {**changes, "resulting_status": status})
    return {"id": sid, "status": status, "occupancy": occ, "capacity": cap}
