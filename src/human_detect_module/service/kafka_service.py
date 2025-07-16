import json

from aiokafka import AIOKafkaProducer #type: ignore
from pydantic import BaseModel


class KafkaService:
    def __init__(
        self, 
        bootstrap_servers: str, 
    ):
        self.bootstrap_servers = bootstrap_servers
        self._producer = None

    async def start(self):
        self._producer = AIOKafkaProducer(
            # bootstrap_servers=self.bootstrap_servers,
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"), #type: ignore
            acks=1,
            linger_ms=10,
            request_timeout_ms=500,
            enable_idempotence=False
        )
        await self._producer.start()
        print("KafkaProducer started",flush=True)

    async def stop(self):
        if self._producer:
            await self._producer.stop()
            print("KafkaProducer stopped",flush=True)

    async def send(self, topic: str, value: BaseModel | str):
        try:
            payload = value if isinstance(value, str) else value.model_dump()
            result = await self._producer.send_and_wait(topic, value=payload) #type: ignore
            print(
                f"Kafka sent successfully [topic={topic}, offset={result.offset}]",  # type: ignore
                flush=True 
            )
        except Exception as ex:
            print(f"Kafka send failed [topic={topic}, error={ex}]", flush=True)

    