from __future__ import annotations

from dataclasses import dataclass
from supabase import Client


PROFILE_SELECT_FIELDS = (
    "id,name,gender,gender_probability,sample_size,age,age_group,country_id,country_probability,created_at"
)


@dataclass(slots=True)
class ProfileRecord:
    id: str
    name: str
    gender: str
    gender_probability: float
    sample_size: int
    age: int
    age_group: str
    country_id: str
    country_probability: float
    created_at: str


@dataclass(slots=True)
class NewProfileRecord:
    id: str
    name: str
    normalized_name: str
    gender: str
    gender_probability: float
    sample_size: int
    age: int
    age_group: str
    country_id: str
    country_probability: float
    created_at: str
    normalized_gender: str
    normalized_age_group: str
    normalized_country_id: str


class ProfileRepository:
    def __init__(self, client: Client):
        self._client = client

    @staticmethod
    def _map_row(row: dict) -> ProfileRecord:
        return ProfileRecord(
            id=row["id"],
            name=row["name"],
            gender=row["gender"],
            gender_probability=row["gender_probability"],
            sample_size=row["sample_size"],
            age=row["age"],
            age_group=row["age_group"],
            country_id=row["country_id"],
            country_probability=row["country_probability"],
            created_at=row["created_at"],
        )

    def get_by_normalized_name(self, normalized_name: str) -> ProfileRecord | None:
        response = (
            self._client.table("profiles")
            .select(PROFILE_SELECT_FIELDS)
            .eq("normalized_name", normalized_name)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        row = rows[0] if rows else None

        if row is None:
            return None
        return self._map_row(row)

    def get_by_id(self, profile_id: str) -> ProfileRecord | None:
        response = (
            self._client.table("profiles")
            .select(PROFILE_SELECT_FIELDS)
            .eq("id", profile_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        row = rows[0] if rows else None

        if row is None:
            return None
        return self._map_row(row)

    def create(self, record: NewProfileRecord) -> ProfileRecord:
        self._client.table("profiles").insert(
            {
                "id": record.id,
                "name": record.name,
                "normalized_name": record.normalized_name,
                "gender": record.gender,
                "gender_probability": record.gender_probability,
                "sample_size": record.sample_size,
                "age": record.age,
                "age_group": record.age_group,
                "country_id": record.country_id,
                "country_probability": record.country_probability,
                "created_at": record.created_at,
                "normalized_gender": record.normalized_gender,
                "normalized_age_group": record.normalized_age_group,
                "normalized_country_id": record.normalized_country_id,
            }
        ).execute()

        return ProfileRecord(
            id=record.id,
            name=record.name,
            gender=record.gender,
            gender_probability=record.gender_probability,
            sample_size=record.sample_size,
            age=record.age,
            age_group=record.age_group,
            country_id=record.country_id,
            country_probability=record.country_probability,
            created_at=record.created_at,
        )

    def list_profiles(
        self,
        *,
        normalized_gender: str | None = None,
        normalized_country_id: str | None = None,
        normalized_age_group: str | None = None,
    ) -> list[ProfileRecord]:
        query = self._client.table("profiles").select(
            PROFILE_SELECT_FIELDS
        )

        if normalized_gender is not None:
            query = query.eq("normalized_gender", normalized_gender)

        if normalized_country_id is not None:
            query = query.eq("normalized_country_id", normalized_country_id)

        if normalized_age_group is not None:
            query = query.eq("normalized_age_group", normalized_age_group)

        response = query.order("created_at").execute()
        rows = response.data or []

        return [self._map_row(row) for row in rows]

    def delete(self, profile_id: str) -> bool:
        # Check if record exists
        existing = self.get_by_id(profile_id)
        if existing is None:
            return False
        
        # Delete it
        self._client.table("profiles").delete().eq("id", profile_id).execute()
        return True
