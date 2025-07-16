import uuid
import asyncio
import logging

from aiokafka import AIOKafkaConsumer  # type: ignore
from pydantic import BaseModel

from ..dto.kafka.consumer.change_human_detect_data_dto import ChangeHumanDetectDataDto
from ..dto.kafka.consumer.post_apc_log_dto import PostApcLogDto  # ✅ 추가
from ..dto.kafka.producer.saved_apc_frame_dto import SavedApcFrameDto  # ✅ 추가

from ..service.kafka_service import KafkaService
from ..service.module_manage_service import ModuleManageService

logger = logging.getLogger(__name__)


class KafkaConsumer:
    def __init__(
        self,
        bootstrap_servers: str,
        kafka_service: KafkaService,
        module_manage_service: ModuleManageService
    ):
        self.kafka_service = kafka_service
        self.bootstrap_servers = bootstrap_servers
        self.module_manage_service = module_manage_service

        self.tasks: list[asyncio.Task[None]] = []
        self.consumers: list[AIOKafkaConsumer] = []
        self.running = False
        self.ready_event = asyncio.Event()
        self.topic_model_map: dict[str, type[BaseModel]] = {}  # ✅ topic -> DTO 매핑

    async def start(self):
        self.running = True
        await self.set_consumer_group()

    async def stop(self):
        self.running = False
        for consumer in self.consumers:
            await consumer.stop()

        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def set_consumer_group(self):
        try:
            # ✅ 토픽별 DTO 정의
            self.topic_model_map = {
                "change-human-detect-config": ChangeHumanDetectDataDto,
                "post-apc-log": PostApcLogDto,
            }

            consumer = AIOKafkaConsumer(
                *self.topic_model_map.keys(),
                bootstrap_servers=self.bootstrap_servers,
                group_id=f"human_detect_module_{uuid.uuid4()}",
                auto_offset_reset="latest"
            )

        except Exception as e:
            print(f"AIOKafkaConsumer init error: {e}", flush=True)
            return

        await self._start_consumer(consumer)
        self.consumers.append(consumer)

        task = asyncio.create_task(self._consume_messages(consumer))
        self.tasks.append(task)

    async def _start_consumer(self, consumer: AIOKafkaConsumer):
        try:
            await asyncio.wait_for(consumer.start(), timeout=10.0)
            consumer.subscribe(topics=list(self.topic_model_map.keys()))
            
            print("✅ Subscribed to topics:", self.topic_model_map.keys(), flush=True)
            self.ready_event.set()
        except asyncio.TimeoutError:
            print("❌ Kafka consumer start timeout", flush=True)
        except Exception as e:
            print(f"❌ Kafka consumer start error: {e}", flush=True)

    async def _consume_messages(self, consumer: AIOKafkaConsumer):
        while not consumer.assignment() and self.running:
            await asyncio.sleep(1)
        if not self.running:
            return

        try:
            async for msg in consumer:
                topic = msg.topic
                model_class = self.topic_model_map.get(topic)

                if model_class is None:
                    print(f"⚠️ Unknown topic received: {topic}", flush=True)
                    continue

                if msg.value is None :
                    continue
                
                dto = self._safe_deserialize(model_class, msg.value)
                
                if dto is None:
                    continue

                print(f"📩 Received message from [{topic}]: {dto}", flush=True)

                if isinstance(dto, ChangeHumanDetectDataDto):
                    await self.module_manage_service.apply_human_detect_data(dto)

                elif isinstance(dto, PostApcLogDto):
                    try:
                        saved: SavedApcFrameDto = self.module_manage_service.save_frame(
                            cctv_id= dto.cctvId,
                            logId= dto.logId,
                            prefix= f"apc_{dto.cctvId}_{'in' if dto.isIn else 'out'}"
                        )
                        await self.kafka_service.send("saved-apc-frame", saved)
                        print(f"📸 Frame saved → {saved.path}", flush=True)
                    except Exception as e:
                        print(f"❌ Failed to save frame for {dto.cctvId}: {e}", flush=True)

        except asyncio.CancelledError:
            print("🛑 Kafka consumer cancelled", flush=True)

    def _safe_deserialize(
        self,
        model_class: type[BaseModel],
        value_bytes: bytes
    ) -> BaseModel | None:
        try:
            json_str = value_bytes.decode()
            print("📦 RAW Kafka message:", json_str[:300], flush=True)
            return model_class.model_validate_json(json_str)
        except Exception as e:
            print(f"❌ Deserialization failed for {model_class.__name__}: {e}", flush=True)
            return None
