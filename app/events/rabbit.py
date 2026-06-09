from collections.abc import Awaitable, Callable
from typing import Protocol

import aio_pika
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AiError
from app.events.idempotency import InMemoryEventTracker
from app.events.mapper import command_from_event, generated_event
from app.schemas.events import EventEnvelope
from app.workflows.minutes_generation import MinutesGenerationWorkflow


class IncomingMessage(Protocol):
    body: bytes

    async def ack(self) -> None: ...

    async def reject(self, *, requeue: bool) -> None: ...


class EventPublisher(Protocol):
    async def publish(self, envelope: EventEnvelope) -> None: ...


class MinutesEventProcessor:
    def __init__(
        self,
        *,
        workflow: MinutesGenerationWorkflow,
        publisher: EventPublisher,
        tracker: InMemoryEventTracker,
        max_retries: int,
    ) -> None:
        self._workflow = workflow
        self._publisher = publisher
        self._tracker = tracker
        self._max_retries = max_retries

    async def process(self, message: IncomingMessage) -> None:
        try:
            envelope = EventEnvelope.model_validate_json(message.body)
        except ValidationError:
            await message.reject(requeue=False)
            return

        if self._tracker.is_completed(envelope.event_id):
            await message.ack()
            return

        try:
            command = command_from_event(envelope)
            result = await self._workflow.execute(command)
            await self._publisher.publish(
                generated_event(result=result, correlation_id=envelope.correlation_id)
            )
        except AiError as exc:
            if exc.retryable and self._tracker.increment_retry(envelope.event_id) <= self._max_retries:
                await message.reject(requeue=True)
            else:
                await message.reject(requeue=False)
            return
        except Exception:
            if self._tracker.increment_retry(envelope.event_id) <= self._max_retries:
                await message.reject(requeue=True)
            else:
                await message.reject(requeue=False)
            return

        self._tracker.mark_completed(envelope.event_id)
        await message.ack()


class AioPikaEventPublisher:
    def __init__(self, exchange: aio_pika.abc.AbstractExchange, routing_key: str) -> None:
        self._exchange = exchange
        self._routing_key = routing_key

    async def publish(self, envelope: EventEnvelope) -> None:
        body = envelope.model_dump_json(by_alias=True).encode()
        await self._exchange.publish(
            aio_pika.Message(body=body, content_type="application/json"),
            routing_key=self._routing_key,
        )


class RabbitRuntime:
    def __init__(self, settings: Settings, workflow: MinutesGenerationWorkflow) -> None:
        self._settings = settings
        self._workflow = workflow
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None

    async def start(self) -> None:
        self._connection = await aio_pika.connect_robust(self._settings.rabbitmq_url)
        channel = await self._connection.channel()
        exchange = await channel.get_exchange(self._settings.rabbitmq_exchange)
        publisher = AioPikaEventPublisher(
            exchange, self._settings.rabbitmq_minutes_generated_routing_key
        )
        processor = MinutesEventProcessor(
            workflow=self._workflow,
            publisher=publisher,
            tracker=InMemoryEventTracker(),
            max_retries=self._settings.rabbitmq_max_retries,
        )
        await self._consume(
            channel,
            self._settings.rabbitmq_minutes_generate_queue,
            processor.process,
        )
        await self._consume(
            channel,
            self._settings.rabbitmq_minutes_regenerate_queue,
            processor.process,
        )

    async def stop(self) -> None:
        if self._connection is not None:
            await self._connection.close()

    async def _consume(
        self,
        channel: aio_pika.abc.AbstractChannel,
        queue_name: str,
        callback: Callable[[IncomingMessage], Awaitable[None]],
    ) -> None:
        queue = await channel.get_queue(queue_name)
        await queue.consume(callback)
