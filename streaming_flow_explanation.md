# 🌊 HTTP 스트리밍 동작 원리 상세 설명

## 📋 전체 아키텍처 개요

```
클라이언트 (Streamlit)  ←→  FastAPI 서버  ←→  Deepgram API
     │                      │                    │
     │                      │                    │
  [EventSource]         [StreamingResponse]   [WebSocket]
     │                      │                    │
     └─── SSE 연결 ────────┘                    │
                            │                    │
                       [AsyncQueue] ←─── [VirtualWebSocket]
```

## 🔄 데이터 흐름 단계별 설명

### 1️⃣ **세션 생성 단계**
```python
# 클라이언트 요청
POST /sessions
{
  "config": {"language": "ko", "interim_results": true}
}

# 서버 처리
session_id = "sess_abc123"
session_queue = asyncio.Queue()  # 이벤트 저장소
stt_service = STTService()       # Deepgram 연결 관리
```

### 2️⃣ **스트리밍 연결 단계**
```python
# 클라이언트
const eventSource = new EventSource('/sessions/sess_abc123/stream');

# 서버 (FastAPI)
@app.get("/sessions/{session_id}/stream")
async def stream_stt_results(session_id: str):
    async def generate_stream():
        async for chunk in streaming_manager.stream_results(session_id):
            yield chunk  # ← 이 부분이 핵심!
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream"
    )
```

### 3️⃣ **오디오 업로드 & 처리 단계**
```python
# 클라이언트가 오디오 업로드
POST /sessions/sess_abc123/audio
{
  "audio_data": "base64_encoded_pcm16_data"
}

# 서버 처리 흐름:
1. Base64 디코딩
2. VirtualWebSocket 생성 (처음 업로드시)
3. Deepgram 연결 생성
4. 오디오 데이터 → Deepgram 전송
```

## 🎯 **핵심: AsyncGenerator와 yield의 동작**

### `stream_results` 메서드 상세 분석:

```python
async def stream_results(self, session_id: str) -> AsyncGenerator[str, None]:
    """
    이 함수는 AsyncGenerator를 반환합니다.
    yield를 만날 때마다 클라이언트에게 데이터를 즉시 전송합니다.
    """
    
    # 1. 초기 연결 이벤트 전송
    start_event = StreamingTokenResponse(...)
    yield f"data: {start_event.model_dump_json()}\n\n"  # ← 즉시 전송!
    
    # 2. 무한 루프로 실시간 이벤트 처리
    while session_id in self.sessions:
        try:
            # 큐에서 이벤트 대기 (1초 타임아웃)
            event = await asyncio.wait_for(
                self.session_queues[session_id].get(), 
                timeout=1.0
            )
            
            # 이벤트를 SSE 형식으로 즉시 전송
            yield f"data: {event.model_dump_json()}\n\n"  # ← 즉시 전송!
            
        except asyncio.TimeoutError:
            # 타임아웃시 heartbeat 전송
            heartbeat = {"event_type": "heartbeat", ...}
            yield f"data: {json.dumps(heartbeat)}\n\n"  # ← 즉시 전송!
```

## 🔗 **VirtualWebSocket의 역할**

```python
class VirtualWebSocket:
    """
    STTService는 원래 WebSocket을 기대하지만,
    HTTP 스트리밍에서는 WebSocket이 없으므로
    가짜 WebSocket을 만들어서 큐로 데이터를 전달합니다.
    """
    
    async def send_text(self, message: str):
        # Deepgram 결과를 받아서
        data = json.loads(message)
        
        if data.get("type") == "transcript_interim":
            # StreamingTokenResponse 객체로 변환
            event = StreamingTokenResponse(
                event_type="token",
                data={"text": data.get("text", ""), ...}
            )
            
            # 큐에 넣기 → stream_results에서 yield로 전송
            await self.event_queue.put(event)
```

## 📡 **Server-Sent Events (SSE) 형식**

클라이언트가 받는 실제 데이터:
```
data: {"event_type": "token", "data": {"text": "안녕", "confidence": 0.8}, "timestamp": 1704067200.123, "session_id": "sess_abc123"}

data: {"event_type": "token", "data": {"text": "안녕하", "confidence": 0.85}, "timestamp": 1704067200.456, "session_id": "sess_abc123"}

data: {"event_type": "final", "data": {"text": "안녕하세요", "confidence": 0.95}, "timestamp": 1704067200.789, "session_id": "sess_abc123"}

data: {"event_type": "heartbeat", "data": {"status": "alive"}, "timestamp": 1704067201.123, "session_id": "sess_abc123"}
```

## ⚡ **실시간 처리 흐름**

```
1. 클라이언트 오디오 업로드
   ↓
2. Deepgram API로 전송
   ↓
3. Deepgram 실시간 응답
   ↓
4. VirtualWebSocket.send_text() 호출
   ↓
5. 큐에 이벤트 추가
   ↓
6. stream_results()에서 큐 감지
   ↓
7. yield로 즉시 클라이언트 전송
   ↓
8. 클라이언트 EventSource.onmessage 트리거
```

## 🎪 **FastAPI StreamingResponse의 마법**

```python
return StreamingResponse(
    generate_stream(),           # AsyncGenerator 함수
    media_type="text/event-stream",
    headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }
)
```

**StreamingResponse가 하는 일:**
1. `generate_stream()` 함수를 호출
2. `yield`가 나올 때마다 즉시 HTTP 응답으로 전송
3. 연결을 계속 유지 (keep-alive)
4. 클라이언트는 실시간으로 데이터 수신

## 🔄 **비동기 큐의 역할**

```python
# 각 세션마다 독립적인 큐
self.session_queues[session_id] = asyncio.Queue()

# 생산자: VirtualWebSocket
await self.event_queue.put(event)

# 소비자: stream_results
event = await self.session_queues[session_id].get()
yield f"data: {event.model_dump_json()}\n\n"
```

이렇게 해서 **멀티 세션**, **실시간 처리**, **비동기 스트리밍**이 모두 가능해집니다! 🎉 