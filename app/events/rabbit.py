import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol

import aio_pika
from pydantic import ValidationError
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.errors import AiError
from app.events.idempotency import InMemoryEventTracker, RedisEventTracker
from app.events.mapper import (
    command_from_event,
    generated_event,
    index_command_from_event,
    removed_document_id_from_event,
)
from app.schemas.events import EventEnvelope
from app.workflows.document_indexing import DocumentIndexingWorkflow
from app.workflows.minutes_generation import MinutesGenerationWorkflow


class IncomingMessage(Protocol):
    body: bytes

    async def ack(self) -> None: ...

    async def reject(self, *, requeue: bool) -> None: ...


class EventPublisher(Protocol):
    async def publish(self, envelope: EventEnvelope) -> None: ...


class AsyncEventTracker(Protocol):
    async def is_completed(self, event_id) -> bool: ...

    async def mark_completed(self, event_id) -> None: ...

    async def increment_retry(self, event_id) -> int: ...


class MinutesEventProcessor:
    def __init__(
        self,
        *,
        workflow: MinutesGenerationWorkflow,
        publisher: EventPublisher,
        tracker: AsyncEventTracker,
        max_retries: int,
        retry_delay_base_seconds: float,
        retry_delay_max_seconds: float,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._workflow = workflow
        self._publisher = publisher
        self._tracker = tracker
        self._max_retries = max_retries
        self._retry_delay_base_seconds = retry_delay_base_seconds
        self._retry_delay_max_seconds = retry_delay_max_seconds
        self._sleep = sleep

    async def process(self, message: IncomingMessage) -> None:
        try:
            envelope = EventEnvelope.model_validate_json(message.body)
        except ValidationError:
            await message.reject(requeue=False)
            return

        if await self._tracker.is_completed(envelope.event_id):
            await message.ack()
            return

        try:
            command = command_from_event(envelope)
            result = await self._workflow.execute(command)
            await self._publisher.publish(
                generated_event(
                    result=result,
                    correlation_id=envelope.correlation_id,
                    source_event_id=envelope.event_id,
                )
            )
        except AiError as exc:
            await self._handle_failure(
                message=message,
                event_id=envelope.event_id,
                retryable=exc.retryable,
            )
            return
        except Exception:
            await self._handle_failure(
                message=message,
                event_id=envelope.event_id,
                retryable=True,
            )
            return

        await self._tracker.mark_completed(envelope.event_id)
        await message.ack()

    async def _handle_failure(self, *, message: IncomingMessage, event_id, retryable: bool) -> None:
        if not retryable:
            await message.reject(requeue=False)
            return
        retry_count = await self._tracker.increment_retry(event_id)
        if retry_count > self._max_retries:
            await message.reject(requeue=False)
            return
        await self._sleep(self._retry_delay_seconds(retry_count))
        await message.reject(requeue=True)

    def _retry_delay_seconds(self, retry_count: int) -> float:
        return min(
            self._retry_delay_base_seconds * (2 ** max(retry_count - 1, 0)),
            self._retry_delay_max_seconds,
        )


class DocumentIndexEventProcessor:
    """BE의 색인 이벤트를 소비해 문서를 Qdrant에 색인한다(응답 이벤트 없는 fire-and-forget)."""

    def __init__(
        self,
        *,
        workflow: DocumentIndexingWorkflow,
        tracker: InMemoryEventTracker,
        max_retries: int,
    ) -> None:
        self._workflow = workflow
        self._tracker = tracker
        self._max_retries = max_retries

    async def process(self, message: IncomingMessage) -> None:
        try:
            envelope = EventEnvelope.model_validate_json(message.body)
        except ValidationError:
            await message.reject(requeue=False)
            return

        # 같은 이벤트가 다시 와도 중복 색인하지 않도록 처리 완료 여부를 먼저 확인한다.
        if self._tracker.is_completed(envelope.event_id):
            await message.ack()
            return

        try:
            command = index_command_from_event(envelope)
            await self._workflow.execute(command)
        except AiError as exc:
            # 계약 오류나 권한 오류는 재시도해도 바뀌지 않으므로 DLQ로 보내고,
            # provider/Qdrant 같은 일시 장애만 재큐잉한다.
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

        # Qdrant 교체 저장까지 끝난 뒤에만 ACK해 승인된 회의록 색인 요청이 유실되지 않게 한다.
        self._tracker.mark_completed(envelope.event_id)
        await message.ack()


class DocumentIndexRemovedEventProcessor:
    """BE의 색인 제거 이벤트를 소비해 삭제된 문서를 Qdrant 색인에서 제거한다(검색에서 빠지게 한다)."""

    def __init__(
        self,
        *,
        workflow: DocumentIndexingWorkflow,
        tracker: InMemoryEventTracker,
        max_retries: int,
    ) -> None:
        self._workflow = workflow
        self._tracker = tracker
        self._max_retries = max_retries

    async def process(self, message: IncomingMessage) -> None:
        try:
            envelope = EventEnvelope.model_validate_json(message.body)
        except ValidationError:
            await message.reject(requeue=False)
            return

        # 같은 제거 이벤트가 다시 와도 멱등하다(이미 지운 문서는 다시 지워도 무방). 중복 처리만 건너뛴다.
        if self._tracker.is_completed(envelope.event_id):
            await message.ack()
            return

        try:
            document_id = removed_document_id_from_event(envelope)
            await self._workflow.remove_document(document_id)
        except AiError:
            # 잘못된 payload/이벤트 타입은 재시도해도 동일하므로 DLQ로 보낸다.
            await message.reject(requeue=False)
            return
        except Exception:
            # Qdrant 일시 장애 등은 재큐잉한다.
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
            aio_pika.Message(
                body=body,
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=str(envelope.event_id),
                correlation_id=str(envelope.correlation_id),
                type=envelope.event_type,
                app_id=envelope.producer,
            ),
            routing_key=self._routing_key,
        )


class RabbitRuntime:
    def __init__(
        self,
        settings: Settings,
        minutes_workflow: MinutesGenerationWorkflow,
        document_indexing_workflow: DocumentIndexingWorkflow,
    ) -> None:
        self._settings = settings
        self._minutes_workflow = minutes_workflow
        self._document_indexing_workflow = document_indexing_workflow
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._idempotency_redis: Redis | None = None

    async def start(self) -> None:
        self._connection = await aio_pika.connect_robust(
            self._settings.rabbitmq_connection_url()
        )
        channel = await self._connection.channel(
            publisher_confirms=True,
            on_return_raises=True,
        )
        await channel.set_qos(prefetch_count=self._settings.rabbitmq_prefetch_count)
        exchange, _ = await self._declare_topology(channel)
        publisher = AioPikaEventPublisher(
            exchange, self._settings.rabbitmq_minutes_generated_routing_key
        )
        self._idempotency_redis = Redis.from_url(self._settings.redis_url)
        minutes_processor = MinutesEventProcessor(
            workflow=self._minutes_workflow,
            publisher=publisher,
            tracker=RedisEventTracker(
                self._idempotency_redis,
                namespace="meetbowl:ai:minutes-events",
                ttl_seconds=self._settings.rabbitmq_idempotency_ttl_seconds,
            ),
            max_retries=self._settings.rabbitmq_max_retries,
            retry_delay_base_seconds=self._settings.rabbitmq_retry_base_delay_seconds,
            retry_delay_max_seconds=self._settings.rabbitmq_retry_max_delay_seconds,
        )
        document_index_processor = DocumentIndexEventProcessor(
            workflow=self._document_indexing_workflow,
            tracker=InMemoryEventTracker(),
            max_retries=self._settings.rabbitmq_max_retries,
        )
        document_index_removed_processor = DocumentIndexRemovedEventProcessor(
            workflow=self._document_indexing_workflow,
            tracker=InMemoryEventTracker(),
            max_retries=self._settings.rabbitmq_max_retries,
        )
        await self._consume(
            channel,
            self._settings.rabbitmq_minutes_generate_queue,
            minutes_processor.process,
        )
        await self._consume(
            channel,
            self._settings.rabbitmq_minutes_regenerate_queue,
            minutes_processor.process,
        )
        await self._consume(
            channel,
            self._settings.rabbitmq_document_index_queue,
            document_index_processor.process,
        )
        await self._consume(
            channel,
            self._settings.rabbitmq_document_index_removed_queue,
            document_index_removed_processor.process,
        )

    async def stop(self) -> None:
        if self._connection is not None:
            await self._connection.close()
        if self._idempotency_redis is not None:
            await self._idempotency_redis.aclose()

    async def _consume(
        self,
        channel: aio_pika.abc.AbstractChannel,
        queue_name: str,
        callback: Callable[[IncomingMessage], Awaitable[None]],
    ) -> None:
        queue = await channel.get_queue(queue_name)
        await queue.consume(callback)

    async def _declare_topology(
        self,
        channel: aio_pika.abc.AbstractChannel,
    ) -> tuple[aio_pika.abc.AbstractExchange, aio_pika.abc.AbstractExchange]:
        exchange = await channel.declare_exchange(
            self._settings.rabbitmq_exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        dlx = await channel.declare_exchange(
            "meetbowl.dlx",
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        await self._declare_event_queue(
            channel=channel,
            exchange=exchange,
            dlx=dlx,
            queue_name=self._settings.rabbitmq_minutes_generate_queue,
            routing_key="meeting.ended",
            dead_letter_routing_key="dlq.meeting.ended",
        )
        await self._declare_event_queue(
            channel=channel,
            exchange=exchange,
            dlx=dlx,
            queue_name=self._settings.rabbitmq_minutes_regenerate_queue,
            routing_key="minutes.generation.requested",
            dead_letter_routing_key="dlq.minutes.generation.requested",
        )
        await self._declare_event_queue(
            channel=channel,
            exchange=exchange,
            dlx=dlx,
            queue_name=self._settings.rabbitmq_document_index_queue,
            routing_key="document.index.requested",
            dead_letter_routing_key="dlq.document.index.requested",
        )
        await self._declare_event_queue(
            channel=channel,
            exchange=exchange,
            dlx=dlx,
            queue_name=self._settings.rabbitmq_document_index_removed_queue,
            routing_key="document.index.removed",
            dead_letter_routing_key="dlq.document.index.removed",
        )

        minutes_generated_queue = await channel.declare_queue(
            "api.minutes.generated",
            durable=True,
            arguments={
                "x-queue-type": "quorum",
                "x-delivery-limit": 3,
                "x-dead-letter-exchange": dlx.name,
                "x-dead-letter-routing-key": "dlq.minutes.generated",
            },
        )
        await minutes_generated_queue.bind(
            exchange,
            routing_key=self._settings.rabbitmq_minutes_generated_routing_key,
        )
        dlq_minutes_generated = await channel.declare_queue(
            "dlq.api.minutes.generated",
            durable=True,
        )
        await dlq_minutes_generated.bind(dlx, routing_key="dlq.minutes.generated")

        return exchange, dlx

    async def _declare_event_queue(
        self,
        *,
        channel: aio_pika.abc.AbstractChannel,
        exchange: aio_pika.abc.AbstractExchange,
        dlx: aio_pika.abc.AbstractExchange,
        queue_name: str,
        routing_key: str,
        dead_letter_routing_key: str,
    ) -> None:
        queue = await channel.declare_queue(
            queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": dlx.name,
                "x-dead-letter-routing-key": dead_letter_routing_key,
            },
        )
        await queue.bind(exchange, routing_key=routing_key)

        dlq_name = f"dlq.{queue_name}"
        dead_letter_queue = await channel.declare_queue(dlq_name, durable=True)
        await dead_letter_queue.bind(dlx, routing_key=dead_letter_routing_key)
