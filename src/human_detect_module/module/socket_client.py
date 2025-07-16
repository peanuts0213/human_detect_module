import asyncio

import traceback
import socketio # type: ignore
from threading import Thread

from ..dto.socket.result_dto import ResultDto

class SocketClient:
    def __init__(self, cctv_id: int):
        self.cctv_id = cctv_id
        self.sio = socketio.AsyncClient()
        self.server_url = "http://localhost:8000"
        self.sio.on("connect", self.on_connect) # type: ignore

        self.loop = asyncio.new_event_loop()
        self._thread = Thread(target=self._start, daemon=True)
        self._thread.start()

    def _start(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._connect())

    async def _connect(self):
        while True:
            try:
                print(
                    f"client: {self.cctv_id} attempting connection to {self.server_url}"
                )
                await self.sio.connect(  # type: ignore
                    self.server_url, 
                    socketio_path="ws/socket.io/",
                    transports=["websocket"]
                )
                await self.sio.wait()
            except Exception as e:
                print(f"[client:{self.cctv_id}] Connection failed: {e}")
                traceback.print_exc()
                await asyncio.sleep(5)

    async def on_connect(self):
        print(f"[client:{self.cctv_id}] Connected")
        await self.sio.emit("register", {"cctv_id": self.cctv_id}) # type: ignore

    
    def send_human_detect_event(self, cctv_id: int, data: list[ResultDto]):
        
        future = asyncio.run_coroutine_threadsafe(
            self.sio.emit( # type: ignore
                "send_event", {
                    "cctv_id": str(cctv_id), 
                    "event_data": [dto.model_dump() for dto in data]
                }
            ),
            self.loop
        )
        try:
            future.result(timeout=3)  # optional: 안 기다려도 됨
        except Exception as e:
            print(f"[WebSocket Emit Error] {e}")

    def close(self):
        try:
            future = asyncio.run_coroutine_threadsafe(self.sio.disconnect(), self.loop)
            future.result(timeout=3)  # optional: 결과 기다림 + timeout 설정 가능
        except Exception as error:
            print(f"[client: {self.cctv_id}] close failed: {error}")
            traceback.print_exc()