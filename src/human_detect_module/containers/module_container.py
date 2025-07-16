from dependency_injector import containers, providers
import ray.actor
from ultralytics import YOLO  #type: ignore
import ray

from ..service.socket_service import SocketService
from ..service.kafka_consumer import KafkaConsumer
from ..service.module_manage_service import ModuleManageService
from ..service.kafka_service import KafkaService

class ModuleContainer(containers.DeclarativeContainer):
    config = providers.Configuration()

    yolo_model = providers.Singleton(YOLO, "yolo12n.pt")
    actors_dict = providers.Singleton(dict[int, ray.actor.ActorHandle])
    socket_service = providers.Singleton(SocketService)

    kafka_service = providers.Singleton(
        KafkaService,
        bootstrap_servers=config.kafka.bootstrap_servers,
    )

    module_manage_service = providers.Factory(
        ModuleManageService,
        yolo_model=yolo_model,
        actors_dict=actors_dict,
        base_address = config.base_address,
        sfu_address = config.sfu_address,
        turn_address = config.turn_address
    )
    
    kafka_consumer = providers.Singleton(
        KafkaConsumer,
        kafka_service=kafka_service,
        module_manage_service=module_manage_service,
        bootstrap_servers=config.kafka.bootstrap_servers,
    )
