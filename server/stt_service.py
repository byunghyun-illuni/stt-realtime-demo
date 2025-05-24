import asyncio
import base64
import json
import logging
import os

import numpy as np
from deepgram import (
    DeepgramClient,
    LiveOptions,
    LiveTranscriptionEvents,
)
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)


class STTService:
    def __init__(self, stats_callback=None):
        self.api_key = os.getenv("DEEPGRAM_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPGRAM_API_KEY not found in environment variables")

        # Deepgram 클라이언트 설정 - 단순화
        self.deepgram = DeepgramClient(api_key=self.api_key)
        self.dg_connection = None
        self.client_ws = None

        # 통계 콜백 함수 설정
        self.stats_callback = stats_callback

    def set_stats_callback(self, callback):
        """통계 업데이트 콜백 함수 설정"""
        self.stats_callback = callback

    async def create_deepgram_connection(self, client_ws):
        """Deepgram Live Transcription 연결 생성"""
        try:
            self.client_ws = client_ws

            # Live Transcription 옵션 설정 - 한국어로 변경
            options = LiveOptions(
                model="nova-2",  # 최신 모델
                language="ko",  # 한국어로 변경
                smart_format=True,
                interim_results=True,  # 실시간 중간 결과
                vad_events=True,  # Voice Activity Detection
                punctuate=True,
                endpointing=300,  # 기본값으로 복원
                utterance_end_ms="1000",  # 기본값으로 복원
                encoding="linear16",  # PCM16 명시
                sample_rate=16000,  # 16kHz 명시
                channels=1,  # 모노 채널 명시
            )

            # Deepgram Live 연결 생성 - 새로운 API 사용
            self.dg_connection = self.deepgram.listen.asyncwebsocket.v("1")

            # 이벤트 핸들러 등록 - 모두 async 함수로 수정
            self.dg_connection.on(LiveTranscriptionEvents.Open, self.on_open)
            self.dg_connection.on(LiveTranscriptionEvents.Transcript, self.on_message)
            self.dg_connection.on(LiveTranscriptionEvents.Metadata, self.on_metadata)
            self.dg_connection.on(
                LiveTranscriptionEvents.SpeechStarted, self.on_speech_started
            )
            self.dg_connection.on(
                LiveTranscriptionEvents.UtteranceEnd, self.on_utterance_end
            )
            self.dg_connection.on(LiveTranscriptionEvents.Close, self.on_close)
            self.dg_connection.on(LiveTranscriptionEvents.Error, self.on_error)

            # 연결 시작
            await self.dg_connection.start(options)

            logger.info("✅ Deepgram 연결 완료")
            return True

        except Exception as e:
            logger.error(f"❌ Deepgram 연결 실패: {e}")
            logger.error(
                f"API 키 확인: {self.api_key[:20] if self.api_key else 'None'}..."
            )
            import traceback

            logger.error(f"상세 오류: {traceback.format_exc()}")
            return False

    async def on_open(self, *args, **kwargs):
        """Deepgram 연결 열림"""
        logger.info("🔗 Deepgram 연결 열림")
        logger.debug(f"Args: {args}, Kwargs: {list(kwargs.keys())}")

    async def on_message(self, *args, **kwargs):
        """Deepgram 전사 결과 수신"""
        try:
            logger.debug("📨 Deepgram 메시지 수신됨")
            logger.debug(f"Args: {args}, Kwargs: {list(kwargs.keys())}")

            # kwargs에서 result 객체 가져오기
            result = kwargs.get("result")
            if not result:
                logger.warning("⚠️ result 객체가 없습니다")
                logger.debug(f"전체 kwargs: {kwargs}")
                return

            sentence = result.channel.alternatives[0].transcript

            if len(sentence) == 0:
                logger.debug("🔇 빈 전사 결과")
                return

            # 중간 결과 vs 최종 결과 구분
            is_final = result.is_final
            confidence = result.channel.alternatives[0].confidence

            if is_final:
                # 최종 결과는 항상 INFO로 출력 (더 강조)
                logger.info(
                    f"✅ 최종 인식 완료: 「{sentence}」 (신뢰도: {confidence:.2f})"
                )

                # 통계 업데이트
                if self.stats_callback:
                    self.stats_callback(
                        "transcription_completed",
                        {"confidence": confidence, "text_length": len(sentence)},
                    )

                response = {
                    "type": "transcript_final",
                    "text": sentence,
                    "confidence": confidence,
                    "is_final": True,
                }
            else:
                # 실시간 중간 결과도 INFO로 출력 (토큰 단위 표시)
                logger.info(
                    f"⚡ 실시간 토큰: 「{sentence}」 (신뢰도: {confidence:.2f})"
                )
                response = {
                    "type": "transcript_interim",
                    "text": sentence,
                    "confidence": confidence,
                    "is_final": False,
                }

            # 직접 비동기 전송
            if self.client_ws:
                await self._send_to_client(response)

        except Exception as e:
            logger.error(f"❌ 메시지 처리 오류: {e}")
            import traceback

            logger.error(f"상세 오류: {traceback.format_exc()}")

    async def _send_to_client(self, message):
        """클라이언트로 메시지 전송 (비동기)"""
        try:
            if self.client_ws:
                msg_type = message.get("type", "unknown")
                if msg_type == "transcript_final":
                    logger.info(f"📤 최종 결과 전송: {message.get('text', '')}")
                elif msg_type == "transcript_interim":
                    logger.info(f"📤 실시간 결과 전송: {message.get('text', '')}")
                else:
                    logger.debug(f"📤 클라이언트로 메시지 전송: {message}")
                await self.client_ws.send_text(json.dumps(message))
            else:
                logger.warning("⚠️ 클라이언트 WebSocket 연결이 없습니다")
        except Exception as e:
            logger.error(f"❌ 클라이언트 전송 오류: {e}")

    async def on_metadata(self, *args, **kwargs):
        """메타데이터 수신"""
        metadata = kwargs.get("metadata")
        logger.info(f"📊 메타데이터 수신: {metadata}")
        logger.debug(f"Args: {args}, Kwargs: {list(kwargs.keys())}")

    async def on_speech_started(self, *args, **kwargs):
        """음성 감지 시작"""
        logger.info("🎤 음성 감지 시작 - 말하기 시작됨")
        logger.debug(f"Args: {args}, Kwargs: {list(kwargs.keys())}")
        try:
            speech_started = kwargs.get("speech_started")
            response = {
                "type": "speech_started",
                "timestamp": (
                    getattr(speech_started, "timestamp", None)
                    if speech_started
                    else None
                ),
            }
            if self.client_ws:
                await self._send_to_client(response)
        except Exception as e:
            logger.error(f"음성 시작 이벤트 처리 오류: {e}")

    async def on_utterance_end(self, *args, **kwargs):
        """발화 종료"""
        logger.info("⏸️ 발화 종료 - 말하기 완료됨")
        logger.debug(f"Args: {args}, Kwargs: {list(kwargs.keys())}")
        try:
            utterance_end = kwargs.get("utterance_end")
            response = {
                "type": "utterance_end",
                "timestamp": (
                    getattr(utterance_end, "last_word_end", None)
                    if utterance_end
                    else None
                ),
            }
            if self.client_ws:
                await self._send_to_client(response)
        except Exception as e:
            logger.error(f"발화 종료 이벤트 처리 오류: {e}")

    async def on_close(self, *args, **kwargs) -> None:
        """Deepgram 연결 종료"""
        close_info = kwargs.get("close")
        logger.info(f"🔌 Deepgram 연결 종료: {close_info}")
        logger.debug(f"Args: {args}, Kwargs: {list(kwargs.keys())}")

    async def on_error(self, *args, **kwargs):
        """Deepgram 오류"""
        error = kwargs.get("error")
        logger.error(f"🚨 Deepgram 오류: {error}")
        logger.debug(f"Args: {args}, Kwargs: {list(kwargs.keys())}")
        if error:
            logger.error(f"상세 오류 정보: {error}")

    async def send_audio_to_deepgram(self, audio_data: bytes):
        """오디오 데이터를 Deepgram으로 전송"""
        try:
            if self.dg_connection:
                # 오디오 데이터 분석
                audio_array = np.frombuffer(audio_data, dtype=np.int16)
                max_val = np.max(np.abs(audio_array)) if len(audio_array) > 0 else 0

                # 오디오 전송 로그는 DEBUG로 변경
                logger.debug(
                    f"🎵 오디오 전송: {len(audio_data)} bytes, 최대값: {max_val}"
                )

                # 음성이 있는지 간단 체크 (임계값 100) - 중요한 음성만 INFO로
                if max_val > 1000:  # 임계값을 높여서 중요한 음성만 로깅
                    logger.debug(f"🔊 음성 활동 감지: 진폭 {max_val}")
                else:
                    logger.debug(f"🔇 무음/저음량: 최대 진폭: {max_val}")

                # 올바른 비동기 전송
                await self.dg_connection.send(audio_data)
                logger.debug(f"✅ 오디오 전송 완료: {len(audio_data)} bytes")
            else:
                logger.warning("⚠️ Deepgram 연결이 없습니다")
        except Exception as e:
            logger.error(f"❌ 오디오 전송 오류: {e}")
            import traceback

            logger.error(f"상세 오류: {traceback.format_exc()}")

    async def handle_client_messages(self, client_ws):
        """클라이언트로부터 메시지 수신 및 Deepgram으로 전달"""
        try:
            # Keepalive 태스크 시작
            keepalive_task = asyncio.create_task(self.send_keepalive())

            async for message in client_ws.iter_text():
                try:
                    data = json.loads(message)

                    if data.get("type") == "audio_data":
                        # Base64 오디오 데이터를 디코딩하여 Deepgram으로 전송
                        audio_base64 = data.get("audio")
                        if audio_base64:
                            audio_bytes = base64.b64decode(audio_base64)
                            logger.debug(
                                f"📡 Base64 디코딩 완료: {len(audio_bytes)} bytes"
                            )
                            await self.send_audio_to_deepgram(audio_bytes)
                        else:
                            logger.warning("⚠️ 오디오 데이터가 비어있습니다")

                    elif data.get("type") == "start_transcription":
                        logger.info("🎙️ 음성 인식 시작 요청")
                        # 이미 연결되어 있으므로 특별한 처리 불필요

                    elif data.get("type") == "stop_transcription":
                        logger.info("⏹️ 음성 인식 중지 요청")
                        if self.dg_connection:
                            await self.dg_connection.finish()

                except json.JSONDecodeError:
                    logger.warning("⚠️ 잘못된 JSON 데이터 수신")
                except Exception as e:
                    logger.error(f"❌ 클라이언트 메시지 처리 오류: {e}")
                    import traceback

                    logger.error(f"상세 오류: {traceback.format_exc()}")

        except Exception as e:
            logger.error(f"❌ 클라이언트 메시지 수신 오류: {e}")
            import traceback

            logger.error(f"상세 오류: {traceback.format_exc()}")
        finally:
            # Keepalive 태스크 정리
            if "keepalive_task" in locals():
                keepalive_task.cancel()

    async def send_keepalive(self):
        """Deepgram 연결 유지를 위한 keepalive 메시지 전송"""
        try:
            while True:
                await asyncio.sleep(10)  # 10초마다
                if self.dg_connection:
                    # keepalive 메시지 전송
                    keepalive_msg = json.dumps({"type": "KeepAlive"})
                    logger.debug("💓 Keepalive 전송")
                    await self.dg_connection.send(keepalive_msg)
        except asyncio.CancelledError:
            logger.debug("💤 Keepalive 태스크 종료")
        except Exception as e:
            logger.error(f"❌ Keepalive 전송 오류: {e}")

    async def handle_websocket_connection(self, websocket):
        """WebSocket 연결 처리 메인 함수"""
        logger.info("🔗 새로운 클라이언트 연결")

        try:
            # Deepgram 연결 생성
            success = await self.create_deepgram_connection(websocket)
            if not success:
                await websocket.send_text(
                    json.dumps(
                        {"type": "error", "message": "Deepgram 연결에 실패했습니다."}
                    )
                )
                return

            # 연결 성공 알림
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "connection",
                        "status": "connected",
                        "message": "Deepgram STT 서비스에 연결되었습니다.",
                    }
                )
            )

            # 클라이언트 메시지 처리
            await self.handle_client_messages(websocket)

        except Exception as e:
            logger.error(f"❌ WebSocket 처리 오류: {e}")
        finally:
            # 정리
            if self.dg_connection:
                try:
                    await self.dg_connection.finish()
                except:
                    pass
            self.client_ws = None
            logger.info("🧹 연결 정리 완료")
