import os
import asyncio
import json
import traceback
import uuid
import numpy as np 
from cv2.typing import MatLike
from asyncio import Queue
from typing import Any, Optional, cast
from av import VideoFrame
import websockets
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCIceCandidate,
    RTCConfiguration,
    RTCIceServer,
    VideoStreamTrack
)
from aiortc.sdp import candidate_from_sdp, candidate_to_sdp

import threading

class WebRTCPublisher:
    """
    GStreamer로부터 프레임을 받아 WebRTC로 송출하는 Publisher 클래스.
    Signaling, ICE, PeerConnection, 트랙 관리 등 WebRTC 송출의 모든 과정을 담당.
    """

    def __init__(
        self, 
        frame_queue: Queue[MatLike | None], 
        cctv_id: int,
        sfu_address: str,
        turn_address: str
    ):
        self.cctv_id = cctv_id
        self.sfu_address = sfu_address
        self.turn_address = turn_address

        self.frame_queue = frame_queue
        # WebRTC PeerConnection 인스턴스 (초기화는 run에서)
        self.pc: Optional[RTCPeerConnection] = None

        # Signaling/송출 자동 시작 (백그라운드 스레드에서 asyncio loop)
        self._thread = threading.Thread(target=self._start_signaling_loop, daemon=True)
        self._thread.start()

    def _start_signaling_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run_loop())
        except Exception as e:
            print(f"[WebRTCPublisher] Signaling loop error: {e}",flush=True)
        finally:
            self._loop.close()

    @staticmethod
    def parse_candidate(
        sdp: str, 
        sdpMid: Optional[str], 
        sdpMLineIndex: Optional[int]
    ) -> RTCIceCandidate:
        """
        SDP 문자열을 RTCIceCandidate 객체로 변환
        """
        parsed = candidate_from_sdp(sdp)
        return RTCIceCandidate(
            foundation=parsed.foundation,
            component=parsed.component,
            priority=parsed.priority,
            ip=parsed.ip,
            protocol=parsed.protocol,
            port=parsed.port,
            type=parsed.type,
            sdpMid=sdpMid,
            sdpMLineIndex=sdpMLineIndex
        )

    async def _run_loop(self):
        while True:
            try:
                await self._run()
            except Exception as e:
                print(f"🚨 WebRTC connect error: {e}", flush=True)
            print("🔁 Reconnecting in 3 seconds...", flush=True)
            await asyncio.sleep(3)
        
    async def _run(self):
        """
        WebRTC 송출의 메인 엔트리포인트.
        - PeerConnection 생성
        - GstVideoTrack 등록
        - signaling 서버와 offer/answer/ICE 교환
        """
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        configuration = RTCConfiguration(
            iceServers=[
                RTCIceServer(
                    urls=f"turn:{self.turn_address}?transport=tcp",
                    username="webrtc",
                    credential="webrtc"
                )
            ],
        )
        self.pc = RTCPeerConnection(configuration)
        video_track = QueueVideoTrack(self.frame_queue)
        self.pc.addTrack(video_track)
        for sender in self.pc.getSenders():
            print(
                f"🧩 Sender track: {sender.track.kind}, \
                readyState={sender.track.readyState}", 
                flush=True
            )
        for transceiver in self.pc.getTransceivers():
            print(
                f"💬 {transceiver.kind}, direction={transceiver.direction}, \
                mid={transceiver.mid}", 
                flush=True
            )
        signaling_url = f"ws://{self.sfu_address}"
        async with websockets.connect(signaling_url) as ws:
            print("✅ WebSocket connected", flush=True)
            
            @self.pc.on("track")
            async def on_track(track:VideoStreamTrack):
                print(f"📺 퍼블리셔 트랙 등록됨: {track.kind}, id={track.id}, readyState={track.readyState}", flush=True)
            
            @self.pc.on("iceconnectionstatechange")
            async def on_iceconnectionstatechange():
                if self.pc is None:
                    return
                
                print(f"🧊 ICE connection state = {self.pc.iceConnectionState}", flush=True)
                if self.pc.iceGatheringState == "complete":
                    print("📤 ICE gathering state complete", flush=True)
                if self.pc.iceConnectionState in ["failed", "disconnected", "closed"]:
                    print("🔥 ICE 연결 종료 감지 → 연결 종료 시도", flush=True)
                    await self.pc.close()
                    if hasattr(ws, "close_code") and ws.close_code is None:
                        await ws.close()
                    raise Exception("ICE 종료로 인한 재연결")
            
            @self.pc.on("connectionstatechange")
            async def on_connectionstatechange():
                if self.pc is None:
                    return
                print(f"📶 PeerConnection state = {self.pc.connectionState}", flush=True)
            
            @self.pc.on("icecandidate")
            async def on_icecandidate(candidate: Optional[RTCIceCandidate]):
                if candidate is None:
                    print("⚠️ ICE candidate is None.", flush=True)
                    return
                
                sdp = candidate_to_sdp(candidate)
                print(f"📨 ICE candidate: {sdp}", flush=True)
                msg = {
                    "method": "trickle",
                    "params": {
                        "candidate": {
                            "candidate": sdp,
                            "sdpMid": candidate.sdpMid,
                            "sdpMLineIndex": candidate.sdpMLineIndex
                        }
                    },
                    "id": 2
                }
                try:
                    await ws.send(json.dumps(msg))
                    print(f"📨 Sent relay ICE candidate: {sdp}", flush=True)
                except websockets.exceptions.ConnectionClosed:
                    print("⚠️ ICE candidate send skipped — WebSocket is already closed", flush=True)

            print(f"📤 self.pc.iceGatheringState before setLocalDescription={self.pc.iceGatheringState}", flush=True)
            offer = await self.pc.createOffer()
            await self.pc.setLocalDescription(offer)
            await asyncio.sleep(2)
            while self.pc.iceGatheringState != "complete":
                print("⏳ Gathering ICE candidates...", flush=True)
                await asyncio.sleep(0.1)
            print(f"📤 self.pc.iceGatheringState={self.pc.iceGatheringState}", flush=True)
            msg = {
                "method": "join",
                "params": {
                    "sid": str(self.cctv_id),
                    "uid": f"gst-pub-{self.cctv_id}-{uuid.uuid4().hex[:6]}",
                    "offer": {
                        "type": "offer",
                        "sdp": self.pc.localDescription.sdp
                    }
                },
                "id": 1
            }
            print(f"📤 Offer SDP: {self.pc.localDescription.sdp}", flush=True)
            await ws.send(json.dumps(msg))
            print("📤 Sent join + offer", flush=True)

            try:
                async for message in ws:
                    data: dict[str, Any] = json.loads(message)
                    print("📥 Received message:", json.dumps(data, indent=2), flush=True)
                    if "result" in data and "sdp" in data["result"]:
                        answer = data["result"]
                        await self.pc.setRemoteDescription(
                            RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
                        )
                        print("✅ SDP answer set", flush=True)
                    elif data.get("method") == "trickle":
                        c = data["params"]["candidate"]
                        await self.pc.addIceCandidate(
                            self.parse_candidate(c["candidate"], c["sdpMid"], c["sdpMLineIndex"])
                        )
                        print("🧊 ICE candidate added", flush=True)
            except websockets.exceptions.ConnectionClosed:
                print("❌ WebSocket connection closed.", flush=True)
            
            finally:
                print("🧹 Cleaning up PeerConnection (finally)", flush=True)
                if self.pc:
                    await self.pc.close()
                    self.pc = None

    def close(self):
        """
        PeerConnection 및 파이프라인 종료
        """
        if self.pc is None:
            return
        try:
            future = asyncio.run_coroutine_threadsafe(self.pc.close(), self._loop)
            future.result(timeout=3)  # optional: 결과 기다림 + timeout 설정 가능
        except Exception as error:
            print(f"[client: {self.cctv_id}] close failed: {error}")
            traceback.print_exc()

    async def _put_frame_async(self, frame):
        try:
            self.frame_queue.put_nowait(frame)
        except asyncio.QueueFull:
            try:
                _ = self.frame_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self.frame_queue.put_nowait(frame)

    def put_frame_to_queue(self, frame):
        """
        외부에서 호출할 수 있는 동기 함수.
        내부적으로 asyncio loop를 통해 비동기 put 처리.
        """
        print("📦 putting frame to async queue", flush=True)
        if self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._put_frame_async(frame), self._loop
            )
        
# HumanDetectModule에서 frame_copy를 큐에 넣으면, 이 큐에서 프레임을 꺼내 송출하는 VideoStreamTrack
class QueueVideoTrack(VideoStreamTrack):
    def __init__(self, frame_queue: Queue[MatLike | None]):
        super().__init__()
        self.frame_queue = frame_queue

    async def recv(self):
        print("▶️ recv called in QueueVideoTrack", flush=True)
        while True:
            try:
                frame = await asyncio.wait_for(self.frame_queue.get(), timeout=0.5)
                if frame is not None:
                    print("✅ Got frame from queue", flush=True)
                    video_frame = VideoFrame.from_ndarray(
                        cast(np.ndarray, frame), format="bgr24")
                else:
                    print("⚠️ Received None frame, using black frame", flush=True)
                    video_frame = VideoFrame.from_ndarray(np.zeros((480, 640, 3), dtype=np.uint8), format="bgr24")
            except asyncio.TimeoutError:
                print("⚠️ Frame fetch timeout in recv", flush=True)
                black = np.zeros((480, 640, 3), dtype=np.uint8)
                video_frame = VideoFrame.from_ndarray(black, format="bgr24")
                
            pts, time_base = await self.next_timestamp()
            video_frame.pts = pts
            video_frame.time_base = time_base
            print("🎥 pts:", pts, "time_base:", time_base, flush=True)
            return video_frame