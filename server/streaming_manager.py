import asyncio
import json
import logging
import queue
import threading
import time
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, Optional

from .models import StreamingSession, StreamingTokenResponse, STTConfig
from .stt_service import STTService

logger = logging.getLogger(__name__)


class StreamingSessionManager:
    """실시간 스트리밍 세션 매니저"""

    def __init__(self):
        self.sessions: Dict[str, StreamingSession] = {}
        self.session_queues: Dict[str, asyncio.Queue] = {}
        self.session_stt_services: Dict[str, STTService] = {}
        self.cleanup_interval = 300  # 5분마다 정리

        # 백그라운드 정리 태스크 시작
        self.cleanup_task = None

    def start_cleanup_task(self):
        """백그라운드 세션 정리 태스크 시작"""
        if not self.cleanup_task:
            self.cleanup_task = asyncio.create_task(self._cleanup_sessions())

    async def _cleanup_sessions(self):
        """비활성 세션 정리"""
        while True:
            try:
                current_time = time.time()
                expired_sessions = []

                for session_id, session in self.sessions.items():
                    # 30분 이상 비활성 세션 정리
                    if current_time - session.created_at > 1800:
                        expired_sessions.append(session_id)

                for session_id in expired_sessions:
                    await self.close_session(session_id)
                    logger.info(f"🧹 만료된 세션 정리: {session_id}")

                await asyncio.sleep(self.cleanup_interval)

            except Exception as e:
                logger.error(f"❌ 세션 정리 오류: {e}")
                await asyncio.sleep(60)

    async def create_session(self, config: Optional[STTConfig] = None) -> str:
        """새로운 스트리밍 세션 생성"""
        session_id = f"sess_{uuid.uuid4().hex[:12]}"

        if not config:
            config = STTConfig()

        session = StreamingSession(
            session_id=session_id,
            config=config,
            created_at=time.time(),
            status="active",
        )

        # 세션별 큐 생성
        self.session_queues[session_id] = asyncio.Queue()

        # 세션별 STT 서비스 생성 (콜백 포함)
        def session_callback(event_type: str, data: dict):
            """세션별 STT 이벤트 콜백"""
            asyncio.create_task(self._handle_stt_event(session_id, event_type, data))

        stt_service = STTService(stats_callback=session_callback)
        self.session_stt_services[session_id] = stt_service

        self.sessions[session_id] = session

        logger.info(f"✅ 새 스트리밍 세션 생성: {session_id}")
        return session_id

    async def _handle_stt_event(self, session_id: str, event_type: str, data: dict):
        """STT 이벤트를 스트리밍 큐로 전달"""
        if session_id not in self.session_queues:
            return

        try:
            # STT 이벤트를 스트리밍 응답으로 변환
            if event_type == "transcription_interim":
                streaming_event = StreamingTokenResponse(
                    event_type="token",
                    data={
                        "text": data.get("text", ""),
                        "confidence": data.get("confidence", 0),
                        "is_partial": True,
                    },
                    timestamp=time.time(),
                    session_id=session_id,
                )
            elif event_type == "transcription_final":
                streaming_event = StreamingTokenResponse(
                    event_type="final",
                    data={
                        "text": data.get("text", ""),
                        "confidence": data.get("confidence", 0),
                        "is_partial": False,
                    },
                    timestamp=time.time(),
                    session_id=session_id,
                )
            elif event_type == "speech_started":
                streaming_event = StreamingTokenResponse(
                    event_type="speech_start",
                    data={"message": "음성 감지됨"},
                    timestamp=time.time(),
                    session_id=session_id,
                )
            elif event_type == "utterance_end":
                streaming_event = StreamingTokenResponse(
                    event_type="speech_end",
                    data={"message": "발화 종료"},
                    timestamp=time.time(),
                    session_id=session_id,
                )
            else:
                return

            await self.session_queues[session_id].put(streaming_event)

        except Exception as e:
            logger.error(f"❌ STT 이벤트 처리 오류 ({session_id}): {e}")

    async def upload_audio(self, session_id: str, audio_data: bytes) -> bool:
        """세션에 오디오 데이터 업로드"""
        if session_id not in self.sessions:
            logger.warning(f"⚠️ 존재하지 않는 세션: {session_id}")
            return False

        if session_id not in self.session_stt_services:
            logger.warning(f"⚠️ STT 서비스가 없는 세션: {session_id}")
            return False

        try:
            stt_service = self.session_stt_services[session_id]

            # Deepgram 연결이 없으면 생성
            if not stt_service.dg_connection:
                # 가상 WebSocket으로 연결 (실제로는 큐로 전달)
                virtual_ws = VirtualWebSocket(
                    session_id, self.session_queues[session_id]
                )
                await stt_service.create_deepgram_connection(virtual_ws)

            # 오디오 데이터 전송
            await stt_service.send_audio_to_deepgram(audio_data)
            return True

        except Exception as e:
            logger.error(f"❌ 오디오 업로드 오류 ({session_id}): {e}")
            return False

    async def stream_results(self, session_id: str) -> AsyncGenerator[str, None]:
        """세션의 실시간 결과 스트리밍 (Server-Sent Events)"""
        if session_id not in self.sessions:
            error_event = {
                "event_type": "error",
                "data": {"message": f"세션을 찾을 수 없습니다: {session_id}"},
                "timestamp": time.time(),
                "session_id": session_id,
            }
            yield f"data: {json.dumps(error_event)}\n\n"
            return

        logger.info(f"🌊 스트리밍 시작: {session_id}")

        try:
            # 연결 시작 이벤트
            start_event = StreamingTokenResponse(
                event_type="speech_start",
                data={"message": "스트리밍 연결됨"},
                timestamp=time.time(),
                session_id=session_id,
            )
            yield f"data: {start_event.model_dump_json()}\n\n"

            # 실시간 이벤트 스트리밍
            while session_id in self.sessions:
                try:
                    # 1초 타임아웃으로 큐에서 이벤트 가져오기
                    event = await asyncio.wait_for(
                        self.session_queues[session_id].get(), timeout=1.0
                    )

                    # Server-Sent Events 형식으로 전송
                    yield f"data: {event.model_dump_json()}\n\n"

                    # 세션 종료 이벤트면 루프 종료
                    if event.event_type == "session_end":
                        break

                except asyncio.TimeoutError:
                    # Keep-alive 전송
                    heartbeat = {
                        "event_type": "heartbeat",
                        "data": {"status": "alive"},
                        "timestamp": time.time(),
                        "session_id": session_id,
                    }
                    yield f"data: {json.dumps(heartbeat)}\n\n"
                    continue

        except Exception as e:
            logger.error(f"❌ 스트리밍 오류 ({session_id}): {e}")
            error_event = {
                "event_type": "error",
                "data": {"message": str(e)},
                "timestamp": time.time(),
                "session_id": session_id,
            }
            yield f"data: {json.dumps(error_event)}\n\n"
        finally:
            logger.info(f"🏁 스트리밍 종료: {session_id}")

    async def close_session(self, session_id: str):
        """세션 종료"""
        if session_id in self.sessions:
            # 종료 이벤트 전송
            if session_id in self.session_queues:
                end_event = StreamingTokenResponse(
                    event_type="session_end",
                    data={"message": "세션이 종료되었습니다"},
                    timestamp=time.time(),
                    session_id=session_id,
                )
                try:
                    await self.session_queues[session_id].put(end_event)
                except:
                    pass

            # STT 서비스 정리
            if session_id in self.session_stt_services:
                stt_service = self.session_stt_services[session_id]
                if stt_service.dg_connection:
                    try:
                        await stt_service.dg_connection.finish()
                    except:
                        pass
                del self.session_stt_services[session_id]

            # 세션 정리
            del self.sessions[session_id]
            if session_id in self.session_queues:
                del self.session_queues[session_id]

            logger.info(f"🗑️ 세션 삭제됨: {session_id}")

    def get_session(self, session_id: str) -> Optional[StreamingSession]:
        """세션 정보 조회"""
        return self.sessions.get(session_id)

    def get_active_sessions_count(self) -> int:
        """활성 세션 수 반환"""
        return len(self.sessions)

    def get_all_sessions(self) -> Dict[str, StreamingSession]:
        """모든 세션 반환"""
        return self.sessions.copy()


class VirtualWebSocket:
    """STTService와 연동하기 위한 가상 WebSocket"""

    def __init__(self, session_id: str, event_queue: asyncio.Queue):
        self.session_id = session_id
        self.event_queue = event_queue

    async def send_text(self, message: str):
        """STT 결과를 큐로 전달"""
        try:
            data = json.loads(message)

            # Deepgram 결과를 스트리밍 이벤트로 변환
            if data.get("type") == "transcript_interim":
                event = StreamingTokenResponse(
                    event_type="token",
                    data={
                        "text": data.get("text", ""),
                        "confidence": data.get("confidence", 0),
                        "is_partial": True,
                    },
                    timestamp=time.time(),
                    session_id=self.session_id,
                )
                await self.event_queue.put(event)

            elif data.get("type") == "transcript_final":
                event = StreamingTokenResponse(
                    event_type="final",
                    data={
                        "text": data.get("text", ""),
                        "confidence": data.get("confidence", 0),
                        "is_partial": False,
                    },
                    timestamp=time.time(),
                    session_id=self.session_id,
                )
                await self.event_queue.put(event)

        except Exception as e:
            logger.error(f"❌ 가상 WebSocket 메시지 처리 오류: {e}")


# 글로벌 스트리밍 매니저 인스턴스
streaming_manager = StreamingSessionManager()
