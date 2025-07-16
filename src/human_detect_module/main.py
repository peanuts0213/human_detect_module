from fastapi.staticfiles import StaticFiles
import socketio # type: ignore
from dependency_injector import providers
from fastapi import FastAPI

from .containers.module_container import ModuleContainer
from .controller.module_manage_controller import router as module_manage_route
from contextlib import asynccontextmanager
import ray
import logging

from .service.socket_service import SocketService



logger = logging.getLogger(__name__)

# 1. SocketService 먼저 생성
socket_service = SocketService()

# 2. DI 컨테이너 초기화
container = ModuleContainer()
container.socket_service.override(providers.Object(socket_service)) #type: ignore

# 3. FastAPI 앱 만들고 DI 연결


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not ray.is_initialized(): # type: ignore
        ray.init() # type: ignore
    container.config.kafka.bootstrap_servers.from_env(
        "KAFKA_BOOTSTRAP_SERVERS", 
        "kafka:9092"
    )
    container.config.base_address.from_env(
        "BASE_ADDRESS",
        "human-detect-module:8000"
    )
    container.config.sfu_address.from_env(
        "SFU_ADDRESS",
        "sfu-server:8000/ws"
    )
    container.config.turn_address.from_env(
        "TURN_ADDRESS",
        "trun-server:8000"
    )
    
    container.init_resources() # type: ignore
    container.wire(modules=[
        ".controller.module_manage_controller"
    ])
    kafka_service = container.kafka_service()
    kafka_consumer = container.kafka_consumer()
    try:
        await kafka_service.start()
        print("✅ Kafka producer started", flush=True)
        
        await kafka_service.send("change-human-detect-config", "on")
        print("✅ Kafka change-human-detect-config topic init message sent", flush=True)

        await kafka_consumer.start()
        print("✅ Kafka consumer started and ready", flush=True)
        
        await kafka_consumer.ready_event.wait()

        await kafka_service.send("human-detect-module-is-on", "on")
        print("✅ Kafka is-on message sent", flush=True)

    except Exception as e:
        logger.exception(f"Kafka startup error {e}")

    yield

    await kafka_consumer.stop()
    await kafka_service.stop()
    service = container.module_manage_service()
    for cctv_id, actor in service.actors_dict.items():
        try:
            ray.get(actor.stop.remote()) # type: ignore
            ray.kill(actor) # type: ignore
        except Exception as e:
            print(f"Failed to stop actor {cctv_id}: {e}")
    ray.shutdown() # type: ignore
    
fastapi_app = FastAPI(
    root_path="/human-detect-module",
    docs_url="/swagger-ui/index.html",
    lifespan=lifespan
)
fastapi_app.mount("/saved_frames", StaticFiles(directory="saved_frames"), name="saved_frames")
fastapi_app.include_router(module_manage_route)

# 4. SocketIO + FastAPI 통합
app = socketio.ASGIApp(
    socketio_server=socket_service.sio,
    other_asgi_app=fastapi_app,
    socketio_path="/ws/socket.io"
)
