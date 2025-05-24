import streamlit as st
import asyncio
import websockets
import json
import base64
import sounddevice as sd
import numpy as np
import threading
import queue
import time
from datetime import datetime
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class STTClient:
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
                logger.info(f"📨 메시지 수신: {message[:100]}...")
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
        page_title="실시간 STT 클라이언트 (Deepgram)",
        page_icon="🎤",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # 한국어 폰트 및 스타일 적용
    st.markdown(
        """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Noto Sans KR', sans-serif;
    }
    
    .main-title {
        background: linear-gradient(90deg, #4285f4, #34a853);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.5rem;
        font-weight: 700;
        text-align: center;
        margin-bottom: 2rem;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<h1 class="main-title">🎤 실시간 음성 인식 클라이언트</h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p style="text-align: center; color: #666; font-size: 1.1rem;">Deepgram Nova-2 기반 한국어 STT</p>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # 세션 상태 초기화
    if "client" not in st.session_state:
        st.session_state.client = STTClient()

    if "transcripts" not in st.session_state:
        st.session_state.transcripts = []

    # 서버 상태 체크
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        st.metric(
            "연결 상태",
            "🟢 연결됨" if st.session_state.client.is_connected else "🔴 연결 안됨",
        )

    with col2:
        st.metric(
            "녹음 상태",
            "🔴 녹음 중" if st.session_state.client.is_recording else "⚪ 대기 중",
        )

    with col3:
        st.metric("인식 결과", f"{len(st.session_state.transcripts)}개")

    # 연결 컨트롤
    st.markdown("### 🔗 서버 연결")
    col4, col5 = st.columns([1, 1])

    with col4:
        if st.button("연결", disabled=st.session_state.client.is_connected):
            success = st.session_state.client.connect()
            if success:
                st.success("서버 연결 성공!")
                time.sleep(0.5)  # 연결 완료 대기
                st.rerun()
            else:
                st.error("서버 연결 실패!")

    with col5:
        if st.button("연결 해제", disabled=not st.session_state.client.is_connected):
            st.session_state.client.stop_recording()
            st.session_state.client.disconnect()
            st.success("연결 해제됨")
            st.rerun()

    # 녹음 컨트롤
    if st.session_state.client.is_connected:
        st.markdown("### 🎙️ 음성 녹음")
        col6, col7 = st.columns([1, 1])

        with col6:
            if st.button("🔴 녹음 시작", disabled=st.session_state.client.is_recording):
                if st.session_state.client.start_recording():
                    st.success("녹음 시작됨")
                    st.rerun()
                else:
                    st.error("녹음 시작 실패")

        with col7:
            if st.button(
                "⏹️ 녹음 중지", disabled=not st.session_state.client.is_recording
            ):
                st.session_state.client.stop_recording()
                st.success("녹음 중지됨")
                st.rerun()
    else:
        st.warning("먼저 서버에 연결해주세요.")

    # 실시간 전사 결과
    st.markdown("### 📝 실시간 음성 인식")

    # 새로운 전사 결과 확인
    queue_size = st.session_state.client.transcript_queue.qsize()
    if queue_size > 0:
        logger.info(f"📦 큐에 {queue_size}개 메시지 대기중")

    while not st.session_state.client.transcript_queue.empty():
        new_item = st.session_state.client.transcript_queue.get()
        logger.info(f"📝 큐에서 메시지 처리: {new_item}")
        st.session_state.transcripts.append(new_item)

    # 현재 실시간 전사 표시 (타이핑 효과)
    if st.session_state.client.is_connected and st.session_state.client.is_recording:
        if st.session_state.transcripts:
            latest = st.session_state.transcripts[-1]
            if latest.get("type") == "transcript_interim":
                st.markdown("### 🔴 실시간 스트리밍")
                confidence = latest.get("confidence", 0)
                text = latest.get("text", "")

                # 타이핑 효과를 위한 컨테이너
                typing_container = st.container()
                with typing_container:
                    # 배경색과 함께 실시간 텍스트 표시
                    st.markdown(
                        f"""
                    <div style="
                        background-color: #f0f8ff;
                        padding: 15px;
                        border-radius: 10px;
                        border-left: 4px solid #4285f4;
                        font-size: 18px;
                        font-family: 'Noto Sans KR', sans-serif;
                        min-height: 60px;
                        display: flex;
                        align-items: center;
                    ">
                        <span style="color: #333; font-weight: 500;">
                            {text}<span style="animation: blink 1s infinite;">|</span>
                        </span>
                    </div>
                    <p style="color: #666; font-size: 12px; margin-top: 5px;">
                        신뢰도: {confidence:.2f} | 실시간 음성 인식 중...
                    </p>
                    
                    <style>
                    @keyframes blink {{
                        0%, 50% {{ opacity: 1; }}
                        51%, 100% {{ opacity: 0; }}
                    }}
                    </style>
                    """,
                        unsafe_allow_html=True,
                    )

    # 완료된 전사 결과들 표시
    if st.session_state.transcripts:
        st.markdown("### 📋 음성 인식 결과")

        # 최종 완료된 전사들만 필터링
        final_transcripts = [
            t
            for t in st.session_state.transcripts
            if t.get("type") == "transcript_final"
        ]

        if final_transcripts:
            # 최근 5개만 표시
            for i, item in enumerate(reversed(final_transcripts[-5:])):
                timestamp = item.get("timestamp", "")
                text = item.get("text", "")
                confidence = item.get("confidence", 0)

                # 완료된 전사를 카드 형태로 표시
                st.markdown(
                    f"""
                <div style="
                    background-color: #f8f9fa;
                    padding: 12px;
                    border-radius: 8px;
                    border-left: 3px solid #28a745;
                    margin-bottom: 10px;
                    font-family: 'Noto Sans KR', sans-serif;
                ">
                    <div style="color: #333; font-size: 16px; margin-bottom: 4px;">
                        {text}
                    </div>
                    <div style="color: #666; font-size: 11px;">
                        {timestamp} | 신뢰도: {confidence:.2f}
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("완료된 인식 결과가 아직 없습니다.")

        # 시스템 메시지들 (접힌 상태로 표시)
        with st.expander("🔍 시스템 로그 보기", expanded=False):
            for item in reversed(st.session_state.transcripts[-10:]):
                timestamp = item.get("timestamp", "")
                text = item.get("text", "")
                item_type = item.get("type", "transcript")
                confidence = item.get("confidence", 0)

                if item_type == "event":
                    st.text(f"[{timestamp}] {text}")
                elif item_type == "system":
                    st.success(f"[{timestamp}] {text}")
                elif item_type == "error":
                    st.error(f"[{timestamp}] {text}")
    else:
        st.info("음성을 녹음하면 실시간으로 인식된 텍스트가 여기에 표시됩니다.")

    # 전사 결과 통계
    if st.session_state.transcripts:
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

        col_stat1, col_stat2 = st.columns(2)
        with col_stat1:
            st.metric("완료된 인식", final_count)
        with col_stat2:
            st.metric("실시간 부분", interim_count)

    # 자동 새로고침 (녹음 중일 때만)
    if st.session_state.client.is_connected and st.session_state.client.is_recording:
        time.sleep(0.5)
        st.rerun()

    # 사이드바에 사용법 표시
    with st.sidebar:
        st.markdown("## 📋 사용법")
        st.markdown(
            """
        1. **서버 연결**: '연결' 버튼 클릭
        2. **녹음 시작**: '🔴 녹음 시작' 버튼 클릭
        3. **음성 입력**: 마이크에 대고 말하기
        4. **결과 확인**: 실시간으로 전사 결과 확인
        5. **녹음 중지**: '⏹️ 녹음 중지' 버튼 클릭
        """
        )

        st.markdown("## ⚙️ 서버 정보")
        st.markdown(
            """
        - **서버 주소**: localhost:8001
        - **STT 엔진**: Deepgram Nova-2
        - **지원 언어**: 한국어 우선, 다국어 지원
        - **오디오 포맷**: PCM16, 16kHz
        - **실시간 처리**: 중간 결과 + 최종 결과
        """
        )

        st.markdown("## 📊 음성 인식 신뢰도")
        if st.session_state.transcripts:
            # 신뢰도 통계
            confidences = [
                t.get("confidence", 0)
                for t in st.session_state.transcripts
                if t.get("type") == "transcript_final" and t.get("confidence", 0) > 0
            ]
            if confidences:
                avg_confidence = sum(confidences) / len(confidences)
                st.metric("평균 신뢰도", f"{avg_confidence:.2f}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        st.info("프로그램이 중단되었습니다.")
    except Exception as e:
        st.error(f"예상치 못한 오류: {e}")
        logger.error(f"Streamlit 오류: {e}")
