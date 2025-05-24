import asyncio
import base64
import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
import numpy as np
import requests
import sounddevice as sd
import streamlit as st
import websockets

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class STTConfig:
    """STT 설정"""

    model: str = "nova-2"
    language: str = "ko"
    interim_results: bool = True
    sample_rate: int = 16000
    channels: int = 1


class HTTPStreamingClient:
    """HTTP 스트리밍 기반 STT 클라이언트"""

    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.session_id = None
        self.session_info = None
        self.is_streaming = False
        self.is_recording = False
        self.transcript_queue = queue.Queue()
        self.audio_queue = queue.Queue()

        # 오디오 설정
        self.CHANNELS = 1
        self.RATE = 16000
        self.CHUNK = 1024
        self.DTYPE = np.int16

        # 스레드 관리
        self.streaming_thread = None
        self.audio_thread = None

    async def create_session(self, config: Optional[STTConfig] = None) -> bool:
        """새로운 스트리밍 세션 생성"""
        try:
            request_data = {}
            if config:
                request_data = {
                    "config": {
                        "model": config.model,
                        "language": config.language,
                        "interim_results": config.interim_results,
                        "sample_rate": config.sample_rate,
                        "channels": config.channels,
                    }
                }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/sessions/create", json=request_data, timeout=10.0
                )

                if response.status_code == 200:
                    self.session_info = response.json()
                    self.session_id = self.session_info["session_id"]
                    logger.info(f"✅ 세션 생성 성공: {self.session_id}")

                    # 시스템 메시지 추가
                    self.transcript_queue.put(
                        {
                            "type": "system",
                            "text": f"✅ HTTP 스트리밍 세션 생성: {self.session_id}",
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                        }
                    )
                    return True
                else:
                    logger.error(f"❌ 세션 생성 실패: {response.status_code}")
                    return False

        except Exception as e:
            logger.error(f"❌ 세션 생성 오류: {e}")
            return False

    def start_streaming(self):
        """SSE 스트리밍 시작"""
        if not self.session_id:
            logger.error("세션이 없습니다")
            return False

        self.is_streaming = True
        self.streaming_thread = threading.Thread(
            target=self._stream_sse_sync, daemon=True
        )
        self.streaming_thread.start()
        logger.info("🌊 SSE 스트리밍 시작됨")
        return True

    def _stream_sse_sync(self):
        """SSE 스트리밍 (동기 방식)"""
        try:
            url = f"{self.base_url}/stream/stt/{self.session_id}"
            headers = {"Accept": "text/event-stream", "Cache-Control": "no-cache"}

            with requests.get(
                url, headers=headers, stream=True, timeout=None
            ) as response:
                if response.status_code != 200:
                    logger.error(f"❌ 스트리밍 연결 실패: {response.status_code}")
                    return

                logger.info("🌊 SSE 스트리밍 연결됨")

                for line in response.iter_lines():
                    if not self.is_streaming:
                        break

                    if line:
                        line_str = line.decode("utf-8")
                        if line_str.startswith("data: "):
                            try:
                                data_str = line_str[6:]  # 'data: ' 제거
                                data = json.loads(data_str)
                                self._handle_sse_event(data)
                            except json.JSONDecodeError as e:
                                logger.warning(f"⚠️ JSON 파싱 오류: {e}")
                                continue

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ SSE 연결 오류: {e}")
        except Exception as e:
            logger.error(f"❌ 예상치 못한 SSE 오류: {e}")
        finally:
            logger.info("🏁 SSE 스트리밍 종료됨")

    def _handle_sse_event(self, data: Dict[str, Any]):
        """SSE 이벤트 처리"""
        event_type = data.get("event_type")
        event_data = data.get("data", {})
        timestamp = datetime.now().strftime("%H:%M:%S")

        if event_type == "token":
            # 실시간 토큰
            text = event_data.get("text", "")
            confidence = event_data.get("confidence", 0)
            logger.info(f"⚡ 실시간 토큰: {text}")

            self.transcript_queue.put(
                {
                    "type": "transcript_interim",
                    "text": text,
                    "confidence": confidence,
                    "timestamp": timestamp,
                }
            )

        elif event_type == "final":
            # 최종 결과
            text = event_data.get("text", "")
            confidence = event_data.get("confidence", 0)
            logger.info(f"✅ 최종 전사: {text}")

            self.transcript_queue.put(
                {
                    "type": "transcript_final",
                    "text": text,
                    "confidence": confidence,
                    "timestamp": timestamp,
                }
            )

        elif event_type == "speech_start":
            self.transcript_queue.put(
                {"type": "event", "text": "🎤 음성 감지됨...", "timestamp": timestamp}
            )

        elif event_type == "speech_end":
            self.transcript_queue.put(
                {"type": "event", "text": "⏸️ 발화 종료", "timestamp": timestamp}
            )

        elif event_type == "heartbeat":
            # Heartbeat는 로그만 남기고 UI에는 표시하지 않음
            logger.debug("💓 Heartbeat")

        elif event_type == "error":
            error_msg = event_data.get("message", "Unknown error")
            self.transcript_queue.put(
                {
                    "type": "error",
                    "text": f"❌ 오류: {error_msg}",
                    "timestamp": timestamp,
                }
            )

    async def upload_audio(self, audio_data: bytes) -> bool:
        """오디오 데이터 업로드"""
        if not self.session_id:
            return False

        try:
            audio_base64 = base64.b64encode(audio_data).decode("utf-8")
            request_data = {"audio_data": audio_base64, "timestamp": time.time()}

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/upload/audio/{self.session_id}",
                    json=request_data,
                    timeout=5.0,
                )

                return response.status_code == 200

        except Exception as e:
            logger.error(f"❌ 오디오 업로드 오류: {e}")
            return False

    def audio_callback(self, indata, frames, time, status):
        """오디오 콜백"""
        if status:
            logger.warning(f"Audio callback status: {status}")

        if self.is_recording:
            audio_bytes = indata.astype(self.DTYPE).tobytes()
            self.audio_queue.put(audio_bytes)

    def _upload_audio_sync(self):
        """오디오 업로드 (동기 방식)"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            while self.is_recording:
                try:
                    if not self.audio_queue.empty():
                        audio_data = self.audio_queue.get()
                        success = loop.run_until_complete(self.upload_audio(audio_data))
                        if not success:
                            logger.warning("⚠️ 오디오 업로드 실패")
                    time.sleep(0.01)  # 10ms 간격
                except Exception as e:
                    logger.error(f"❌ 오디오 처리 오류: {e}")
                    break
        finally:
            loop.close()

    def start_recording(self):
        """녹음 시작"""
        try:
            self.stream = sd.InputStream(
                samplerate=self.RATE,
                channels=self.CHANNELS,
                dtype=self.DTYPE,
                blocksize=self.CHUNK,
                callback=self.audio_callback,
            )

            self.is_recording = True
            self.stream.start()

            # 오디오 업로드 스레드 시작
            self.audio_thread = threading.Thread(
                target=self._upload_audio_sync, daemon=True
            )
            self.audio_thread.start()

            logger.info("🎤 HTTP 스트리밍 녹음 시작")
            return True

        except Exception as e:
            logger.error(f"❌ 녹음 시작 실패: {e}")
            return False

    def stop_recording(self):
        """녹음 중지"""
        self.is_recording = False

        if hasattr(self, "stream") and self.stream:
            self.stream.stop()
            self.stream.close()

        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=1.0)

        logger.info("⏹️ HTTP 스트리밍 녹음 중지")

    def stop_streaming(self):
        """스트리밍 중지"""
        self.is_streaming = False

        if self.streaming_thread and self.streaming_thread.is_alive():
            self.streaming_thread.join(timeout=2.0)

    async def close_session(self):
        """세션 종료"""
        if not self.session_id:
            return

        try:
            # 먼저 녹음과 스트리밍 중지
            self.stop_recording()
            self.stop_streaming()

            # 세션 삭제 요청
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"{self.base_url}/sessions/{self.session_id}", timeout=5.0
                )

                if response.status_code == 200:
                    logger.info(f"✅ 세션 종료 성공: {self.session_id}")
                else:
                    logger.warning(f"⚠️ 세션 종료 응답: {response.status_code}")

        except Exception as e:
            logger.error(f"❌ 세션 종료 오류: {e}")
        finally:
            self.session_id = None
            self.session_info = None


class WebSocketClient:
    """기존 WebSocket 기반 STT 클라이언트 (기존 코드 유지)"""

    def __init__(self, server_url="ws://localhost:8001/ws/stt"):
        self.server_url = server_url
        self.websocket = None
        self.audio_queue = queue.Queue()
        self.transcript_queue = queue.Queue()
        self.is_recording = False
        self.is_connected = False
        self.audio_thread = None
        self.websocket_thread = None
        self.connection_event = threading.Event()

        # 오디오 설정 - Deepgram 권장 설정
        self.CHANNELS = 1
        self.RATE = 16000  # Deepgram 권장: 16kHz
        self.CHUNK = 1024
        self.DTYPE = np.int16

    def connect(self):
        """서버에 WebSocket 연결"""
        try:
            # 웹소켓 연결을 별도 스레드에서 실행
            self.websocket_thread = threading.Thread(
                target=self.run_websocket_connection, daemon=True
            )
            self.websocket_thread.start()

            # 연결 완료까지 대기 (최대 5초)
            if self.connection_event.wait(timeout=5.0):
                return True
            else:
                logger.error("연결 타임아웃")
                return False

        except Exception as e:
            logger.error(f"서버 연결 실패: {e}")
            return False

    def run_websocket_connection(self):
        """웹소켓 연결과 메시지 수신을 별도 스레드에서 실행"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self.websocket_handler())
        except Exception as e:
            logger.error(f"웹소켓 연결 오류: {e}")
        finally:
            loop.close()

    async def websocket_handler(self):
        """웹소켓 연결 및 메시지 처리"""
        try:
            # 웹소켓 연결
            self.websocket = await websockets.connect(self.server_url)
            self.is_connected = True
            self.connection_event.set()  # 연결 완료 신호

            # 메시지 수신 루프
            await self.listen_messages()

        except Exception as e:
            logger.error(f"웹소켓 핸들러 오류: {e}")
            self.is_connected = False
        finally:
            if self.websocket:
                await self.websocket.close()
            self.websocket = None
            self.is_connected = False

    def disconnect(self):
        """서버 연결 해제"""
        self.is_connected = False
        self.connection_event.clear()

        # 웹소켓 스레드 종료 대기
        if self.websocket_thread and self.websocket_thread.is_alive():
            self.websocket_thread.join(timeout=2.0)

    async def listen_messages(self):
        """서버로부터 메시지 수신"""
        try:
            async for message in self.websocket:
                logger.info(f"📨 WebSocket 메시지 수신: {message[:100]}...")
                data = json.loads(message)
                logger.info(f"📋 메시지 타입: {data.get('type')}")

                # Deepgram 최종 전사 결과
                if data.get("type") == "transcript_final":
                    transcript = data.get("text", "")
                    confidence = data.get("confidence", 0)
                    logger.info(
                        f"✅ 최종 전사: {transcript} (신뢰도: {confidence:.2f})"
                    )
                    self.transcript_queue.put(
                        {
                            "type": "transcript_final",
                            "text": transcript,
                            "confidence": confidence,
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                        }
                    )

                # Deepgram 실시간 중간 전사 결과
                elif data.get("type") == "transcript_interim":
                    transcript = data.get("text", "")
                    confidence = data.get("confidence", 0)
                    logger.info(
                        f"⚡ 실시간 전사: {transcript} (신뢰도: {confidence:.2f})"
                    )
                    self.transcript_queue.put(
                        {
                            "type": "transcript_interim",
                            "text": transcript,
                            "confidence": confidence,
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                        }
                    )

                # 음성 감지 시작
                elif data.get("type") == "speech_started":
                    self.transcript_queue.put(
                        {
                            "type": "event",
                            "text": "🎤 음성 감지됨...",
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                        }
                    )

                # 발화 종료
                elif data.get("type") == "utterance_end":
                    self.transcript_queue.put(
                        {
                            "type": "event",
                            "text": "⏸️ 발화 종료",
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                        }
                    )

                # 연결 상태
                elif data.get("type") == "connection":
                    if data.get("status") == "connected":
                        message = data.get("message", "서버 연결 완료")
                        self.transcript_queue.put(
                            {
                                "type": "system",
                                "text": f"✅ {message}",
                                "timestamp": datetime.now().strftime("%H:%M:%S"),
                            }
                        )

                # 에러 처리
                elif data.get("type") == "error":
                    error_msg = data.get("message", "Unknown error")
                    self.transcript_queue.put(
                        {
                            "type": "error",
                            "text": f"❌ 오류: {error_msg}",
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                        }
                    )

        except websockets.exceptions.ConnectionClosed:
            logger.info("WebSocket 연결 종료")
        except Exception as e:
            logger.error(f"메시지 수신 오류: {e}")
            import traceback

            logger.error(f"상세 오류: {traceback.format_exc()}")

    def audio_callback(self, indata, frames, time, status):
        """sounddevice 오디오 콜백"""
        if status:
            logger.warning(f"Audio callback status: {status}")

        if self.is_recording:
            # numpy array를 bytes로 변환
            audio_bytes = indata.astype(self.DTYPE).tobytes()
            self.audio_queue.put(audio_bytes)

    def send_audio_data_sync(self):
        """오디오 데이터를 서버로 전송"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            while self.is_recording and self.websocket:
                try:
                    if not self.audio_queue.empty():
                        audio_data = self.audio_queue.get()
                        audio_base64 = base64.b64encode(audio_data).decode("utf-8")
                        message = {"type": "audio_data", "audio": audio_base64}
                        loop.run_until_complete(
                            self.websocket.send(json.dumps(message))
                        )
                    time.sleep(0.01)  # 10ms 간격
                except Exception as e:
                    logger.error(f"오디오 전송 오류: {e}")
                    break
        finally:
            loop.close()

    def start_recording(self):
        """녹음 시작"""
        try:
            self.stream = sd.InputStream(
                samplerate=self.RATE,
                channels=self.CHANNELS,
                dtype=self.DTYPE,
                blocksize=self.CHUNK,
                callback=self.audio_callback,
            )

            self.is_recording = True
            self.stream.start()

            # 오디오 전송을 별도 스레드에서 실행
            self.audio_thread = threading.Thread(
                target=self.send_audio_data_sync, daemon=True
            )
            self.audio_thread.start()
            return True

        except Exception as e:
            logger.error(f"녹음 시작 실패: {e}")
            return False

    def stop_recording(self):
        """녹음 중지"""
        self.is_recording = False

        if hasattr(self, "stream") and self.stream:
            self.stream.stop()
            self.stream.close()

        # 오디오 스레드 종료 대기
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=1.0)


# Streamlit UI
def main():
    st.set_page_config(
        page_title="🎤 실시간 STT 클라이언트 (WebSocket + HTTP Streaming)",
        page_icon="🎤",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # 한국어 폰트 및 개선된 스타일 적용
    st.markdown(
        """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Noto Sans KR', sans-serif;
    }
    
    .main-title {
        background: linear-gradient(90deg, #4285f4, #34a853, #ea4335, #fbbc04);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.5rem;
        font-weight: 700;
        text-align: center;
        margin-bottom: 1rem;
    }
    
    .subtitle {
        text-align: center;
        color: #666;
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }
    
    .method-card {
        padding: 15px;
        border-radius: 10px;
        border: 2px solid #e0e0e0;
        margin: 10px 0;
        transition: all 0.3s ease;
    }
    
    .method-card.selected {
        border-color: #4285f4;
        background-color: #f0f8ff;
    }
    
    .streaming-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 20px;
        border-radius: 15px;
        margin: 15px 0;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    
    .realtime-token {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        color: white;
        padding: 20px;
        border-radius: 15px;
        font-size: 1.3rem;
        font-weight: 500;
        min-height: 80px;
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        margin: 15px 0;
        animation: pulse-glow 2s infinite;
    }
    
    @keyframes pulse-glow {
        0%, 100% { box-shadow: 0 0 20px rgba(240, 147, 251, 0.4); }
        50% { box-shadow: 0 0 30px rgba(245, 87, 108, 0.6); }
    }
    
    .final-result {
        background: #f8f9fa;
        border-left: 4px solid #28a745;
        padding: 15px;
        border-radius: 8px;
        margin: 10px 0;
        transition: all 0.3s ease;
        animation: slideIn 0.5s ease;
    }
    
    @keyframes slideIn {
        from { opacity: 0; transform: translateX(-20px); }
        to { opacity: 1; transform: translateX(0); }
    }
    
    .metric-card {
        background: white;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        text-align: center;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )

    # 메인 타이틀
    st.markdown(
        '<h1 class="main-title">🎤 실시간 음성 인식 클라이언트</h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="subtitle">Deepgram Nova-2 기반 | WebSocket + HTTP 스트리밍 지원</p>',
        unsafe_allow_html=True,
    )

    # 세션 상태 초기화
    if "communication_method" not in st.session_state:
        st.session_state.communication_method = "http_streaming"

    if "websocket_client" not in st.session_state:
        st.session_state.websocket_client = WebSocketClient()

    if "http_client" not in st.session_state:
        st.session_state.http_client = HTTPStreamingClient()

    if "transcripts" not in st.session_state:
        st.session_state.transcripts = []

    # 통신 방식 선택
    st.markdown("## 🔄 통신 방식 선택")

    col_method1, col_method2 = st.columns(2)

    with col_method1:
        if st.button(
            "🌊 HTTP 스트리밍 (SSE)",
            key="http_method",
            use_container_width=True,
            type=(
                "primary"
                if st.session_state.communication_method == "http_streaming"
                else "secondary"
            ),
        ):
            st.session_state.communication_method = "http_streaming"
            st.rerun()

        st.markdown(
            """
        **특징:**
        - Server-Sent Events 기반
        - 토큰 단위 실시간 스트리밍 
        - 세션 기반 관리
        - HTTP 표준 프로토콜
        """
        )

    with col_method2:
        if st.button(
            "🔌 WebSocket",
            key="ws_method",
            use_container_width=True,
            type=(
                "primary"
                if st.session_state.communication_method == "websocket"
                else "secondary"
            ),
        ):
            st.session_state.communication_method = "websocket"
            st.rerun()

        st.markdown(
            """
        **특징:**
        - 양방향 실시간 통신
        - 낮은 지연시간
        - 연결 지속성
        - 기존 WebSocket 방식
        """
        )

    st.markdown("---")

    # 현재 선택된 방식에 따른 클라이언트 선택
    if st.session_state.communication_method == "http_streaming":
        current_client = st.session_state.http_client
        method_name = "HTTP 스트리밍"
        method_icon = "🌊"
    else:
        current_client = st.session_state.websocket_client
        method_name = "WebSocket"
        method_icon = "🔌"

    # 현재 방식 표시
    st.markdown(f"### {method_icon} {method_name} 모드")

    # 상태 정보 표시
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.session_state.communication_method == "http_streaming":
            status = "🟢 세션 활성" if current_client.session_id else "🔴 세션 없음"
            st.metric("세션 상태", status)
        else:
            status = "🟢 연결됨" if current_client.is_connected else "🔴 연결 안됨"
            st.metric("연결 상태", status)

    with col2:
        if st.session_state.communication_method == "http_streaming":
            streaming_status = (
                "🌊 스트리밍 중" if current_client.is_streaming else "⚪ 대기 중"
            )
            st.metric("스트리밍 상태", streaming_status)
        else:
            recording_status = (
                "🔴 녹음 중" if current_client.is_recording else "⚪ 대기 중"
            )
            st.metric("녹음 상태", recording_status)

    with col3:
        recording_status = "🔴 녹음 중" if current_client.is_recording else "⚪ 대기 중"
        st.metric("녹음 상태", recording_status)

    with col4:
        st.metric("인식 결과", f"{len(st.session_state.transcripts)}개")

    # 세션 정보 (HTTP 스트리밍일 때만)
    if (
        st.session_state.communication_method == "http_streaming"
        and current_client.session_id
    ):
        st.markdown("### 📋 세션 정보")
        session_info_col1, session_info_col2 = st.columns(2)

        with session_info_col1:
            st.info(f"**세션 ID:** `{current_client.session_id}`")

        with session_info_col2:
            if current_client.session_info:
                st.info(
                    f"**스트림 URL:** `{current_client.session_info.get('stream_url', 'N/A')}`"
                )

    # 연결/세션 관리
    st.markdown("### 🔗 연결/세션 관리")

    if st.session_state.communication_method == "http_streaming":
        col_connect1, col_connect2 = st.columns(2)

        with col_connect1:
            if st.button(
                "🌊 세션 생성 & 스트리밍 시작",
                disabled=bool(current_client.session_id),
                use_container_width=True,
            ):

                async def create_and_start():
                    config = STTConfig(language="ko", interim_results=True)
                    if await current_client.create_session(config):
                        if current_client.start_streaming():
                            st.success("✅ 세션 생성 및 스트리밍 시작 성공!")
                        else:
                            st.error("❌ 스트리밍 시작 실패")
                    else:
                        st.error("❌ 세션 생성 실패")

                import asyncio

                asyncio.run(create_and_start())
                time.sleep(0.5)
                st.rerun()

        with col_connect2:
            if st.button(
                "🗑️ 세션 종료",
                disabled=not bool(current_client.session_id),
                use_container_width=True,
            ):

                async def close_session():
                    await current_client.close_session()
                    st.success("✅ 세션 종료됨")

                asyncio.run(close_session())
                st.rerun()

    else:
        # WebSocket 연결 관리
        col_connect1, col_connect2 = st.columns(2)

        with col_connect1:
            if st.button(
                "🔌 WebSocket 연결",
                disabled=current_client.is_connected,
                use_container_width=True,
            ):
                if current_client.connect():
                    st.success("✅ WebSocket 연결 성공!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("❌ WebSocket 연결 실패!")

        with col_connect2:
            if st.button(
                "🔌 연결 해제",
                disabled=not current_client.is_connected,
                use_container_width=True,
            ):
                current_client.stop_recording()
                current_client.disconnect()
                st.success("✅ 연결 해제됨")
                st.rerun()

    # 녹음 컨트롤
    connection_ready = (
        st.session_state.communication_method == "http_streaming"
        and current_client.session_id
        and current_client.is_streaming
    ) or (
        st.session_state.communication_method == "websocket"
        and current_client.is_connected
    )

    if connection_ready:
        st.markdown("### 🎙️ 음성 녹음")
        col_record1, col_record2 = st.columns(2)

        with col_record1:
            if st.button(
                "🔴 녹음 시작",
                disabled=current_client.is_recording,
                use_container_width=True,
            ):
                if current_client.start_recording():
                    st.success("🎤 녹음 시작됨")
                    st.rerun()
                else:
                    st.error("❌ 녹음 시작 실패")

        with col_record2:
            if st.button(
                "⏹️ 녹음 중지",
                disabled=not current_client.is_recording,
                use_container_width=True,
            ):
                current_client.stop_recording()
                st.success("⏹️ 녹음 중지됨")
                st.rerun()
    else:
        st.warning("먼저 연결/세션을 생성해주세요.")

    # 새로운 전사 결과 확인 및 처리
    queue_size = current_client.transcript_queue.qsize()
    if queue_size > 0:
        logger.info(f"📦 큐에 {queue_size}개 메시지 대기중")

    while not current_client.transcript_queue.empty():
        new_item = current_client.transcript_queue.get()
        logger.info(f"📝 큐에서 메시지 처리: {new_item}")
        st.session_state.transcripts.append(new_item)

    # 실시간 토큰 표시 (개선된 UI)
    st.markdown("### 🔥 실시간 음성 인식")

    if connection_ready and current_client.is_recording:
        # 최신 실시간 토큰 찾기
        latest_interim = None
        for transcript in reversed(st.session_state.transcripts):
            if transcript.get("type") == "transcript_interim":
                latest_interim = transcript
                break

        if latest_interim:
            text = latest_interim.get("text", "")
            confidence = latest_interim.get("confidence", 0)

            st.markdown(
                f"""
                <div class="realtime-token">
                    <div>
                        <div style="font-size: 1.5rem; margin-bottom: 10px;">
                            {text}<span style="animation: blink 1s infinite;">│</span>
                        </div>
                        <div style="font-size: 0.9rem; opacity: 0.8;">
                            신뢰도: {confidence:.2f} | {method_name} 실시간 스트리밍
                        </div>
                    </div>
                </div>
                
                <style>
                @keyframes blink {{
                    0%, 50% {{ opacity: 1; }}
                    51%, 100% {{ opacity: 0; }}
                }}
                </style>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div class="realtime-token">
                    <div>
                        <div style="font-size: 1.2rem; opacity: 0.7;">
                            음성을 입력하면 실시간으로 텍스트가 나타납니다...
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("🎤 녹음을 시작하면 실시간 음성 인식 결과가 여기에 표시됩니다.")

    # 완료된 전사 결과들 표시
    if st.session_state.transcripts:
        st.markdown("### 📋 완료된 음성 인식 결과")

        # 최종 완료된 전사들만 필터링
        final_transcripts = [
            t
            for t in st.session_state.transcripts
            if t.get("type") == "transcript_final"
        ]

        if final_transcripts:
            # 최근 10개 표시
            for i, item in enumerate(reversed(final_transcripts[-10:])):
                timestamp = item.get("timestamp", "")
                text = item.get("text", "")
                confidence = item.get("confidence", 0)

                st.markdown(
                    f"""
                    <div class="final-result">
                        <div style="color: #333; font-size: 16px; margin-bottom: 5px; font-weight: 500;">
                            {text}
                        </div>
                        <div style="color: #666; font-size: 12px;">
                            <span style="margin-right: 15px;">🕒 {timestamp}</span>
                            <span style="margin-right: 15px;">📊 신뢰도: {confidence:.2f}</span>
                            <span>🔧 {method_name}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # 결과 지우기 버튼
            if st.button("🗑️ 결과 지우기", key="clear_results"):
                st.session_state.transcripts = []
                st.rerun()
        else:
            st.info("완료된 인식 결과가 아직 없습니다.")

        # 통계 정보
        st.markdown("### 📊 인식 통계")

        final_count = len(
            [
                t
                for t in st.session_state.transcripts
                if t.get("type") == "transcript_final"
            ]
        )
        interim_count = len(
            [
                t
                for t in st.session_state.transcripts
                if t.get("type") == "transcript_interim"
            ]
        )

        col_stat1, col_stat2, col_stat3 = st.columns(3)

        with col_stat1:
            st.metric("완료된 전사", final_count)

        with col_stat2:
            st.metric("실시간 토큰", interim_count)

        with col_stat3:
            if final_transcripts:
                confidences = [
                    t.get("confidence", 0)
                    for t in final_transcripts
                    if t.get("confidence", 0) > 0
                ]
                if confidences:
                    avg_confidence = sum(confidences) / len(confidences)
                    st.metric("평균 신뢰도", f"{avg_confidence:.2f}")
                else:
                    st.metric("평균 신뢰도", "N/A")
            else:
                st.metric("평균 신뢰도", "N/A")

        # 시스템 로그 (접힌 상태)
        with st.expander("🔍 시스템 로그 및 이벤트", expanded=False):
            system_logs = [
                t
                for t in st.session_state.transcripts
                if t.get("type") in ["event", "system", "error"]
            ]

            if system_logs:
                for item in reversed(system_logs[-20:]):  # 최근 20개
                    timestamp = item.get("timestamp", "")
                    text = item.get("text", "")
                    item_type = item.get("type", "")

                    if item_type == "event":
                        st.info(f"[{timestamp}] {text}")
                    elif item_type == "system":
                        st.success(f"[{timestamp}] {text}")
                    elif item_type == "error":
                        st.error(f"[{timestamp}] {text}")
            else:
                st.info("시스템 로그가 없습니다.")

    # 자동 새로고침 (녹음 중일 때만)
    if connection_ready and current_client.is_recording:
        time.sleep(0.5)
        st.rerun()

    # 사이드바에 정보 표시
    with st.sidebar:
        st.markdown("## 📋 사용법")

        if st.session_state.communication_method == "http_streaming":
            st.markdown(
                """
            ### 🌊 HTTP 스트리밍 방식
            1. **세션 생성**: '세션 생성 & 스트리밍 시작' 클릭
            2. **녹음 시작**: '🔴 녹음 시작' 클릭
            3. **음성 입력**: 마이크에 대고 말하기
            4. **실시간 확인**: 토큰 단위로 결과 확인
            5. **녹음 중지**: '⏹️ 녹음 중지' 클릭
            6. **세션 종료**: '🗑️ 세션 종료' 클릭
            """
            )
        else:
            st.markdown(
                """
            ### 🔌 WebSocket 방식
            1. **연결**: 'WebSocket 연결' 클릭
            2. **녹음 시작**: '🔴 녹음 시작' 클릭
            3. **음성 입력**: 마이크에 대고 말하기
            4. **결과 확인**: 실시간으로 전사 결과 확인
            5. **녹음 중지**: '⏹️ 녹음 중지' 클릭
            6. **연결 해제**: '연결 해제' 클릭
            """
            )

        st.markdown("## ⚙️ 서버 정보")
        st.markdown(
            """
        - **서버 주소**: localhost:8001
        - **STT 엔진**: Deepgram Nova-2
        - **지원 언어**: 한국어 우선, 다국어 지원
        - **오디오 포맷**: PCM16, 16kHz
        - **실시간 처리**: 토큰 단위 + 최종 결과
        """
        )

        st.markdown("## 🔗 API 문서")
        st.markdown(
            """
        - **Swagger UI**: [http://localhost:8001/docs](http://localhost:8001/docs)
        - **서버 상태**: [http://localhost:8001/health](http://localhost:8001/health)
        - **서버 정보**: [http://localhost:8001/info](http://localhost:8001/info)
        """
        )

        st.markdown("## 📈 실시간 성능")
        if connection_ready and current_client.is_recording:
            st.success("🔴 실시간 처리 중")
        else:
            st.info("⚪ 대기 중")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        st.info("프로그램이 중단되었습니다.")
    except Exception as e:
        st.error(f"예상치 못한 오류: {e}")
        logger.error(f"Streamlit 오류: {e}")
