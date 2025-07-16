from threading import Event
import threading
import time
import cv2
from cv2.typing import MatLike
import numpy
from queue import Queue
import gi

gi.require_version("Gst", "1.0")
from gi.repository import (  # noqa: E402
    Gst, GLib  # type: ignore
)

class FrameReader:
    def __init__(
        self,
        rtsp_url: str,
        frame_queue: Queue[MatLike | None],
        frame_shape: tuple[int, int, int],
        stop_event: Event
    ):
        self.rtsp_url = rtsp_url
        self.frame_queue = frame_queue
        self.frame_shape = frame_shape
        self.stop_event = stop_event

        self.running = False
        self.pipeline: Gst.Bin | None = None
        self.loop = GLib.MainLoop.new(None, False)
        self.last_frame_time = time.time()

    def on_new_sample(self, appsink: Gst.Element):
        sample: Gst.Sample | None = appsink.emit("pull-sample")
        if sample is None:
            self.frame_queue.put(None)
            return Gst.FlowReturn.ERROR

        buffer = sample.get_buffer()
        caps = sample.get_caps()
        width = caps.get_structure(0).get_value("width")  # type: ignore
        height = caps.get_structure(0).get_value("height")  # type: ignore
        success, map_info = buffer.map(Gst.MapFlags.READ)  # type: ignore
        if not success:
            return Gst.FlowReturn.ERROR

        frame = numpy.frombuffer(
            map_info.data,
            dtype=numpy.uint8
        ).reshape(height, width, 3)  # type: ignore
        if frame.shape != self.frame_shape:
            frame = cv2.resize(
                frame,
                (self.frame_shape[1], self.frame_shape[0])
            )

        self.last_frame_time = time.time()
        self.frame_queue.put(frame)
        buffer.unmap(map_info)  # type: ignore
        return Gst.FlowReturn.OK

    def on_bus_message(self, bus: Gst.Bus, message: Gst.Message, loop: GLib.MainLoop):
        t = message.type
        if t == Gst.MessageType.EOS:
            self.running = False
            loop.quit()
        elif t == Gst.MessageType.ERROR:
            err, _debug = message.parse_error()
            print(f"GStreamer Error: {err}", flush=True)
            if "Timeout" in str(err):
                self.running = False
                loop.quit()
        return True

    def start_pipeline(self):
        pipeline_str = (
            f"rtspsrc location={self.rtsp_url} "
            "latency=0 timeout=3000000 protocols=tcp ! "
            "rtph264depay ! h264parse ! nvh264dec ! "
            "videoconvert ! video/x-raw,format=BGR ! "
            "appsink name=appsink drop=1 max-buffers=1 emit-signals=True"
        )
        try:
            Gst.init(None)

            self.pipeline = Gst.parse_launch(pipeline_str)  # type: ignore
            appsink = self.pipeline.get_by_name("appsink")  # type: ignore

            if appsink is None:
                print("🚫 appsink not found", flush=True)
                self.running = False
                return
            
            appsink.set_property("sync", False) 
            appsink.connect("new-sample", self.on_new_sample)

            ret = self.pipeline.set_state(Gst.State.PLAYING)  # type: ignore
            if ret == Gst.StateChangeReturn.FAILURE:
                print("🚫 Pipeline 시작 실패", flush=True)
                self.running = False
                return

            self.running = True

            bus = self.pipeline.get_bus()  # type: ignore
            bus.add_signal_watch()  # type: ignore
            bus.connect("message", self.on_bus_message, self.loop)  # type: ignore

        except Exception as e:
            print(f"Exception during pipeline setup: {e}", flush=True)
            self.running = False

    def stop_pipeline(self):
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None

    def read(self):
        MAX_TIMEOUT = 10  # seconds

        while not self.stop_event.is_set():
            self.start_pipeline()
            if self.running:
                self.last_frame_time = time.time()
                loop_thread = threading.Thread(target=self.loop.run)  # type: ignore
                loop_thread.start()

                while self.running and not self.stop_event.is_set():
                    if time.time() - self.last_frame_time > MAX_TIMEOUT:
                        print("❌ 프레임 timeout 발생, 재시도 중...", flush=True)
                        self.running = False
                        self.loop.quit()
                        break
                    time.sleep(1)

                loop_thread.join()
            else:
                print("🔁 카메라 재시도 대기 중...", flush=True)
                time.sleep(2)

            self.stop_pipeline()
