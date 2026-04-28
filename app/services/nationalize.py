from __future__ import annotations

from dataclasses import dataclass

from httpx import AsyncClient, HTTPError

from app.services.genderize import UpstreamServiceError

import os

from dotenv import load_dotenv

load_dotenv()

nationalize_url = os.getenv("NATIONALIZE_URL")
NATIONALIZE_INVALID_RESPONSE_MESSAGE = "Nationalize returned an invalid response"


@dataclass(slots=True)
class NationalizePayload:
    country_id: str
    country_probability: float


class NationalizeService:
    def __init__(self, client: AsyncClient):
        self._client = client

    async def classify(self, name: str) -> NationalizePayload:
        try:
            response = await self._client.get(nationalize_url, params={"name": name})
            response.raise_for_status()
            body = response.json()
        except (HTTPError, ValueError, TypeError) as exc:
            raise UpstreamServiceError(NATIONALIZE_INVALID_RESPONSE_MESSAGE) from exc

        if not isinstance(body, dict):
            raise UpstreamServiceError(NATIONALIZE_INVALID_RESPONSE_MESSAGE)

        countries = body.get("country")
        if not isinstance(countries, list) or len(countries) == 0:
            raise UpstreamServiceError(NATIONALIZE_INVALID_RESPONSE_MESSAGE)

        best: tuple[str, float] | None = None

        for item in countries:
            if not isinstance(item, dict):
                continue
            country_id = item.get("country_id")
            probability = item.get("probability")
            if not isinstance(country_id, str):
                continue
            try:
                probability_value = float(probability)
            except (TypeError, ValueError):
                continue

            if best is None or probability_value > best[1]:
                best = (country_id, probability_value)

        if best is None:
            raise UpstreamServiceError(NATIONALIZE_INVALID_RESPONSE_MESSAGE)

        return NationalizePayload(country_id=best[0], country_probability=best[1])
