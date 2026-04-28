from __future__ import annotations

from dataclasses import dataclass

from httpx import AsyncClient, HTTPError

from app.services.genderize import UpstreamServiceError

import os

from dotenv import load_dotenv

load_dotenv()

agify_url = os.getenv("AGIFY_URL")


AGIFY_INVALID_RESPONSE_MESSAGE = "Agify returned an invalid response"


@dataclass(slots=True)
class AgifyPayload:
    age: int


class AgifyService:
    def __init__(self, client: AsyncClient):
        self._client = client

    async def classify(self, name: str) -> AgifyPayload:
        try:
            response = await self._client.get(agify_url, params={"name": name})
            response.raise_for_status()
            body = response.json()
        except (HTTPError, ValueError, TypeError) as exc:
            raise UpstreamServiceError(AGIFY_INVALID_RESPONSE_MESSAGE) from exc

        if not isinstance(body, dict):
            raise UpstreamServiceError(AGIFY_INVALID_RESPONSE_MESSAGE)

        age = body.get("age")
        if age is None:
            raise UpstreamServiceError(AGIFY_INVALID_RESPONSE_MESSAGE)

        try:
            age_value = int(age)
        except (TypeError, ValueError) as exc:
            raise UpstreamServiceError(AGIFY_INVALID_RESPONSE_MESSAGE) from exc

        if age_value < 0:
            raise UpstreamServiceError(AGIFY_INVALID_RESPONSE_MESSAGE)

        return AgifyPayload(age=age_value)
