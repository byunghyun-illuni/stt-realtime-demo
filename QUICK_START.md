# ⚡ 실시간 STT API - 5분 빠른 시작

## 🎯 한 줄 요약
음성을 업로드하면 실시간으로 텍스트가 나오는 API입니다.

## 🚀 3단계로 시작하기

### 1️⃣ 세션 만들기
```bash
curl -X POST http://localhost:8001/sessions \
  -H "Content-Type: application/json" \
  -d '{"config": {"language": "ko", "interim_results": true}}'
```
**결과:** `{"session_id": "sess_abc123", ...}`

### 2️⃣ 실시간 결과 받기
```javascript
const eventSource = new EventSource('http://localhost:8001/sessions/sess_abc123/stream');
eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.event_type === 'token') {
        console.log('실시간:', data.data.text);  // 타이핑 중인 텍스트
    } else if (data.event_type === 'final') {
        console.log('최종:', data.data.text);    // 완성된 문장
    }
};
```

### 3️⃣ 오디오 보내기
```javascript
// 오디오를 Base64로 변환해서 전송
const audioBase64 = btoa(String.fromCharCode(...audioBytes));
fetch('http://localhost:8001/sessions/sess_abc123/audio', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ audio_data: audioBase64 })
});
```

## 🎪 완전한 예제 (복사해서 바로 사용)

```html
<!DOCTYPE html>
<html>
<head><title>STT 테스트</title></head>
<body>
    <button onclick="start()">🔴 시작</button>
    <div id="result">결과가 여기에 나타납니다</div>
    
    <script>
        let sessionId, eventSource;
        
        async function start() {
            // 1. 세션 생성
            const session = await fetch('http://localhost:8001/sessions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ config: { language: 'ko' } })
            }).then(r => r.json());
            
            sessionId = session.session_id;
            
            // 2. 실시간 결과 받기
            eventSource = new EventSource(`http://localhost:8001/sessions/${sessionId}/stream`);
            eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.event_type === 'final') {
                    document.getElementById('result').innerHTML += `<p>✅ ${data.data.text}</p>`;
                }
            };
            
            // 3. 마이크 녹음 시작
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const recorder = new MediaRecorder(stream);
            
            recorder.ondataavailable = async (event) => {
                const audioBlob = event.data;
                const arrayBuffer = await audioBlob.arrayBuffer();
                const audioBase64 = btoa(String.fromCharCode(...new Uint8Array(arrayBuffer)));
                
                // 오디오 전송
                fetch(`http://localhost:8001/sessions/${sessionId}/audio`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ audio_data: audioBase64 })
                });
            };
            
            recorder.start(1000); // 1초마다 전송
        }
    </script>
</body>
</html>
```

## 📋 API 요약

| 동작 | 방법 | URL |
|------|------|-----|
| 세션 생성 | `POST` | `/sessions` |
| 실시간 결과 | `GET` (SSE) | `/sessions/{id}/stream` |
| 오디오 업로드 | `POST` | `/sessions/{id}/audio` |
| 세션 종료 | `DELETE` | `/sessions/{id}` |

## 🎯 핵심 포인트

1. **Server-Sent Events (SSE)** 사용 - WebSocket보다 간단
2. **실시간 + 최종** 두 가지 결과 타입
3. **Base64 PCM16** 오디오 포맷
4. **세션 기반** - 여러 클라이언트 동시 지원

## 🔧 오디오 포맷
- PCM16, 16kHz, 모노 채널
- Base64로 인코딩해서 전송

## 📞 도움말
- 상세 문서: [CLIENT_API_GUIDE.md](CLIENT_API_GUIDE.md)
- API 문서: http://localhost:8001/docs
- 문의: byunghyun@illuni.com 