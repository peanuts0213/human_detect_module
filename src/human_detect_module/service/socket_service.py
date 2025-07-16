from typing import Any
from socketio import AsyncServer # type: ignore
import socketio # type: ignore

import logging
logger = logging.getLogger(__name__)

class SocketService:
    def __init__(self):
        self.sio: AsyncServer = socketio.AsyncServer(
            async_mode="asgi", cors_allowed_origins="*"
        )
        self.app = socketio.ASGIApp(self.sio)

        self.user_sid_map: dict[int, str] = {}

        # 핸들러 등록
        self.sio.on("connect", handler=self.handle_connect) # type: ignore
        self.sio.on("disconnect", handler=self.handle_disconnect) # type: ignore
        self.sio.on("register", handler=self.handle_register) # type: ignore
        self.sio.on("send_event", handler=self.handle_send_event) # type: ignore

        print("set socket server", flush=True)

    async def handle_connect(self, sid: str, environ: dict[str, Any]):
        print(f"[socket] Connected: {sid}", flush=True)

    async def handle_disconnect(self, sid: str):
        print(f"[socket] Disconnected: {sid}", flush=True)
        for cctv_id, mapped_sid in list(self.user_sid_map.items()):
            if mapped_sid == sid:
                del self.user_sid_map[cctv_id]

    async def handle_register(self, sid: str, data: dict[str, int]):
        cctv_id = data.get("cctv_id")
        if cctv_id is not None:
            room = str(cctv_id)
            await self.sio.enter_room(sid, room) # type: ignore
            print(f"[socket] sid={sid} joined room={room}", flush=True)

    async def handle_send_event(self, sid: str, data: dict[str, str | dict[str, Any]]):
        cctv_id = data.get("cctv_id")
        event_data = data.get("event_data")
        await self.sio.emit("human_detect_event", event_data, room=cctv_id)  # type: ignore
