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

        # 세션별 STT 서비스 생성
        stt_service = STTService()
        self.session_stt_services[session_id] = stt_service

        self.sessions[session_id] = session

        logger.info(f"✅ 새 스트리밍 세션 생성: {session_id}")
        return session_id

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
        """
        🌊 실시간 결과 스트리밍 (Server-Sent Events)

        🎯 이 함수가 HTTP 스트리밍의 핵심입니다!

        동작 원리:
        1. AsyncGenerator를 반환하여 무한 스트림 생성
        2. 세션별 큐(asyncio.Queue)에서 이벤트를 실시간으로 가져옴
        3. yield로 SSE 형식 데이터를 즉시 클라이언트에게 전송
        4. VirtualWebSocket이 큐에 넣은 데이터를 실시간으로 소비

        데이터 흐름:
        Deepgram → VirtualWebSocket → Queue → 이 함수 → yield → 클라이언트
        """
        if session_id not in self.sessions:
            error_event = {
                "event_type": "error",
                "data": {"message": f"세션을 찾을 수 없습니다: {session_id}"},
                "timestamp": time.time(),
                "session_id": session_id,
            }
            # 🚀 즉시 에러 이벤트 전송
            yield f"data: {json.dumps(error_event)}\n\n"
            return

        logger.info(f"🌊 스트리밍 시작: {session_id}")

        try:
            # 🎬 연결 시작 이벤트 - 클라이언트에게 연결 성공 알림
            start_event = StreamingTokenResponse(
                event_type="speech_start",
                data={"message": "스트리밍 연결됨"},
                timestamp=time.time(),
                session_id=session_id,
            )
            # 🚀 첫 번째 yield - 연결 확인 메시지 즉시 전송
            yield f"data: {start_event.model_dump_json()}\n\n"

            # 🔄 무한 루프 - 실시간 이벤트 처리의 핵심!
            while session_id in self.sessions:
                try:
                    # ⏰ 큐에서 이벤트 대기 (1초 타임아웃)
                    # 이 부분이 핵심: VirtualWebSocket이 큐에 넣은 데이터를 기다림
                    event = await asyncio.wait_for(
                        self.session_queues[session_id].get(), timeout=1.0
                    )

                    # 🚀 이벤트를 SSE 형식으로 즉시 전송!
                    # yield가 실행되는 순간 = 클라이언트가 데이터를 받는 순간
                    yield f"data: {event.model_dump_json()}\n\n"

                    # 🏁 세션 종료 이벤트면 루프 종료
                    if event.event_type == "session_end":
                        break

                except asyncio.TimeoutError:
                    # 💓 1초마다 heartbeat 전송 (연결 유지)
                    heartbeat = {
                        "event_type": "heartbeat",
                        "data": {"status": "alive"},
                        "timestamp": time.time(),
                        "session_id": session_id,
                    }
                    # 🚀 heartbeat도 즉시 전송
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
            # 🚀 에러 이벤트도 즉시 전송
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
    """
    🔗 STTService와 HTTP 스트리밍을 연결하는 브릿지

    🎯 역할:
    - STTService는 원래 WebSocket 인터페이스를 기대함
    - HTTP 스트리밍에서는 실제 WebSocket이 없음
    - 이 클래스가 가짜 WebSocket 역할을 하여 STT 결과를 큐로 전달

    🔄 데이터 흐름:
    STTService → VirtualWebSocket.send_text() → Queue → stream_results() → 클라이언트
    """

    def __init__(self, session_id: str, event_queue: asyncio.Queue):
        self.session_id = session_id
        self.event_queue = event_queue  # 🎯 핵심: 이 큐로 데이터를 전달
        logger.info(f"🔗 VirtualWebSocket 생성됨: {session_id}")

    async def send_text(self, message: str):
        """
        🎯 STT 결과를 큐로 전달하는 핵심 메서드

        STTService가 WebSocket.send_text()를 호출하면:
        1. JSON 메시지를 파싱
        2. StreamingTokenResponse 객체로 변환
        3. 세션별 큐에 추가
        4. stream_results()가 큐에서 가져가서 클라이언트로 전송
        """
        try:
            logger.info(
                f"📨 VirtualWebSocket 메시지 수신 ({self.session_id}): {message}"
            )
            data = json.loads(message)

            # 🎯 Deepgram 결과를 스트리밍 이벤트로 변환
            if data.get("type") == "transcript_interim":
                logger.info(f"⚡ 실시간 토큰 처리 중: {data.get('text', '')}")
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
                # 🚀 큐에 추가 → stream_results()에서 즉시 yield로 전송
                await self.event_queue.put(event)
                logger.info(f"✅ 실시간 토큰 큐에 추가됨: {data.get('text', '')}")

            elif data.get("type") == "transcript_final":
                logger.info(f"✅ 최종 결과 처리 중: {data.get('text', '')}")
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
                # 🚀 큐에 추가 → stream_results()에서 즉시 yield로 전송
                await self.event_queue.put(event)
                logger.info(f"✅ 최종 결과 큐에 추가됨: {data.get('text', '')}")

            elif data.get("type") == "speech_started":
                logger.info("🎤 음성 시작 이벤트 처리")
                event = StreamingTokenResponse(
                    event_type="speech_start",
                    data={"message": "음성 감지됨"},
                    timestamp=time.time(),
                    session_id=self.session_id,
                )
                await self.event_queue.put(event)

            elif data.get("type") == "utterance_end":
                logger.info("⏸️ 발화 종료 이벤트 처리")
                event = StreamingTokenResponse(
                    event_type="speech_end",
                    data={"message": "발화 종료"},
                    timestamp=time.time(),
                    session_id=self.session_id,
                )
                await self.event_queue.put(event)

            else:
                logger.debug(
                    f"🔍 처리되지 않은 메시지 타입: {data.get('type', 'unknown')}"
                )

        except Exception as e:
            logger.error(f"❌ 가상 WebSocket 메시지 처리 오류: {e}")
            import traceback

            logger.error(f"상세 오류: {traceback.format_exc()}")


# 글로벌 스트리밍 매니저 인스턴스
streaming_manager = StreamingSessionManager()
