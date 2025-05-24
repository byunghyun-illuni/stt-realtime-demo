#!/usr/bin/env python3
"""
Deepgram API 연결 테스트 스크립트
"""
import os
import asyncio
import json
from dotenv import load_dotenv
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
)

load_dotenv()


async def test_deepgram_connection():
    """Deepgram 연결 테스트"""
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        print("❌ DEEPGRAM_API_KEY가 설정되지 않았습니다.")
        return False

    print(f"✅ API 키 확인: {api_key[:20]}...")

    try:
        # Deepgram 클라이언트 생성
        config = DeepgramClientOptions(api_key=api_key)
        deepgram = DeepgramClient(api_key=api_key, config=config)

        # Live 연결 생성 - 새로운 API 사용
        dg_connection = deepgram.listen.asyncwebsocket.v("1")

        # 이벤트 핸들러
        async def on_open(*args, **kwargs):
            print("🔗 Deepgram 연결 열림")
            print(f"Args: {args}, Kwargs: {list(kwargs.keys())}")

        async def on_message(*args, **kwargs):
            print("📨 Deepgram 메시지 수신!")
            print(f"Args: {args}, Kwargs: {list(kwargs.keys())}")
            result = kwargs.get("result")
            if result:
                print(f"전사 결과: {result}")

        async def on_error(*args, **kwargs):
            print("❌ Deepgram 오류!")
            print(f"Args: {args}, Kwargs: {list(kwargs.keys())}")
            error = kwargs.get("error")
            if error:
                print(f"오류 내용: {error}")

        # 이벤트 핸들러 등록
        dg_connection.on(LiveTranscriptionEvents.Open, on_open)
        dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
        dg_connection.on(LiveTranscriptionEvents.Error, on_error)

        # Live 옵션
        options = LiveOptions(
            model="nova-2",
            language="ko",
            smart_format=True,
            interim_results=True,
            vad_events=True,
            endpointing=300,
            punctuate=True,
        )

        print("🚀 Deepgram 연결 시도...")
        await dg_connection.start(options)

        print("✅ 연결 성공! 3초 대기...")
        await asyncio.sleep(3)

        # 테스트 오디오 데이터 전송 (무음)
        print("🎵 테스트 오디오 전송...")
        test_audio = b"\x00" * 1024  # 1KB 무음 데이터
        await dg_connection.send(test_audio)

        print("⏰ 응답 대기...")
        await asyncio.sleep(2)

        # 연결 종료
        print("🔌 연결 종료...")
        await dg_connection.finish()

        return True

    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        import traceback

        print(f"상세 오류: {traceback.format_exc()}")
        return False


if __name__ == "__main__":
    print("🧪 Deepgram API 연결 테스트 시작")
    success = asyncio.run(test_deepgram_connection())
    if success:
        print("✅ 테스트 완료")
    else:
        print("❌ 테스트 실패")

