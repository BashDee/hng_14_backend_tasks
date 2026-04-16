from __future__ import annotations

from datetime import datetime, timezone
import os
import time
from typing import Literal
from uuid import UUID

from httpx import AsyncClient

from app.db import get_supabase_client
from app.models.classify import ErrorResponse
from app.models.profile import (
    ProfileAlreadyExistsResponse,
    ProfileData,
    ProfileSuccessResponse,
    ProfileSummary,
    ProfilesListResponse,
)
from app.repositories.profiles import NewProfileRecord, ProfileRecord, ProfileRepository
from app.services.agify import AgifyService
from app.services.genderize import (
    GenderizeService,
    NoPredictionAvailableError,
    UpstreamServiceError,
)
from app.services.nationalize import NationalizeService


class ProfileNotFoundError(Exception):
    pass


class ProfilesService:
    def __init__(self, client: AsyncClient):
        self._genderize_service = GenderizeService(client)
        self._agify_service = AgifyService(client)
        self._nationalize_service = NationalizeService(client)
        self._repository = ProfileRepository(get_supabase_client())

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        )

    @staticmethod
    def _uuid_v7() -> str:
        # UUIDv7 layout: 48-bit unix epoch milliseconds + random payload.
        unix_ms = int(time.time() * 1000)
        random_bytes = bytearray(os.urandom(10))
        raw = bytearray(16)

        raw[0:6] = unix_ms.to_bytes(6, byteorder="big", signed=False)
        raw[6] = 0x70 | (random_bytes[0] & 0x0F)
        raw[7] = random_bytes[1]
        raw[8] = 0x80 | (random_bytes[2] & 0x3F)
        raw[9:16] = random_bytes[3:10]

        return str(UUID(bytes=bytes(raw)))

    @staticmethod
    def _normalize_name(name: str) -> str:
        return name.strip().lower()

    @staticmethod
    def _age_group(age: int) -> Literal["child", "teenager", "adult", "senior"]:
        if age <= 12:
            return "child"
        if age <= 19:
            return "teenager"
        if age <= 59:
            return "adult"
        return "senior"

    @staticmethod
    def _validate_name(value: object) -> tuple[int, str | ErrorResponse]:
        if value is None:
            return 400, ErrorResponse(message="Missing or empty name")

        if not isinstance(value, str):
            return 422, ErrorResponse(message="Invalid type")

        stripped = value.strip()
        if stripped == "":
            return 400, ErrorResponse(message="Missing or empty name")

        return 200, stripped

    @staticmethod
    def _to_profile_data(record: ProfileRecord) -> ProfileData:
        return ProfileData(
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

    @staticmethod
    def _to_profile_summary(record: ProfileRecord) -> ProfileSummary:
        return ProfileSummary(
            id=record.id,
            name=record.name,
            gender=record.gender,
            age=record.age,
            age_group=record.age_group,
            country_id=record.country_id,
        )

    async def create_profile(
        self, name_value: object
    ) -> tuple[int, ProfileSuccessResponse | ProfileAlreadyExistsResponse | ErrorResponse]:
        validation_status, validated_name = self._validate_name(name_value)
        if isinstance(validated_name, ErrorResponse):
            return validation_status, validated_name

        normalized_name = self._normalize_name(validated_name)
        existing = self._repository.get_by_normalized_name(normalized_name)
        if existing is not None:
            return 200, ProfileAlreadyExistsResponse(data=self._to_profile_data(existing))

        try:
            gender_result = await self._genderize_service.classify(name=validated_name)
            agify_result = await self._agify_service.classify(name=validated_name)
            nationalize_result = await self._nationalize_service.classify(name=validated_name)
        except NoPredictionAvailableError:
            return 502, ErrorResponse(message="Genderize returned an invalid response")
        except UpstreamServiceError as exc:
            return 502, ErrorResponse(message=str(exc))

        age_group = self._age_group(agify_result.age)
        created_record = self._repository.create(
            NewProfileRecord(
                id=self._uuid_v7(),
                name=validated_name,
                normalized_name=normalized_name,
                gender=gender_result.data.gender,
                gender_probability=gender_result.data.probability,
                sample_size=gender_result.data.sample_size,
                age=agify_result.age,
                age_group=age_group,
                country_id=nationalize_result.country_id,
                country_probability=nationalize_result.country_probability,
                created_at=self._utc_now_iso(),
                normalized_gender=gender_result.data.gender.lower(),
                normalized_age_group=age_group.lower(),
                normalized_country_id=nationalize_result.country_id.lower(),
            )
        )

        return 201, ProfileSuccessResponse(data=self._to_profile_data(created_record))

    def get_profile(self, profile_id: str) -> ProfileSuccessResponse:
        record = self._repository.get_by_id(profile_id)
        if record is None:
            raise ProfileNotFoundError()
        return ProfileSuccessResponse(data=self._to_profile_data(record))

    def list_profiles(
        self,
        *,
        gender: str | None,
        country_id: str | None,
        age_group: str | None,
    ) -> ProfilesListResponse:
        records = self._repository.list_profiles(
            normalized_gender=gender.strip().lower() if isinstance(gender, str) else None,
            normalized_country_id=country_id.strip().lower()
            if isinstance(country_id, str)
            else None,
            normalized_age_group=age_group.strip().lower()
            if isinstance(age_group, str)
            else None,
        )

        summaries = [self._to_profile_summary(record) for record in records]
        return ProfilesListResponse(count=len(summaries), data=summaries)

    def delete_profile(self, profile_id: str) -> bool:
        return self._repository.delete(profile_id)
