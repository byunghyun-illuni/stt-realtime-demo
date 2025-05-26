# 🎤 실시간 STT API 클라이언트 가이드

## 📋 개요

이 API는 **실시간 음성 인식 서비스**를 제공합니다. 음성을 업로드하면 실시간으로 텍스트 결과를 받을 수 있습니다.

**핵심 특징:**
- ⚡ **실시간 처리**: 음성을 말하는 동안 실시간으로 텍스트 변환
- 🌊 **HTTP 스트리밍**: 표준 HTTP 기술 사용 (WebSocket 불필요)
- 🔄 **토큰 단위**: 단어별로 실시간 결과 + 최종 완성된 문장
- 🌍 **다국어 지원**: 한국어, 영어 등

## 🚀 빠른 시작 (3단계)

### 1단계: 세션 생성
```javascript
const response = await fetch('http://localhost:8001/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        config: {
            language: 'ko',           // 한국어
            interim_results: true     // 실시간 중간 결과 받기
        }
    })
});

const session = await response.json();
console.log('세션 생성됨:', session.session_id);
// 결과: { session_id: "sess_abc123", stream_url: "/sessions/sess_abc123/stream", ... }
```

### 2단계: 실시간 결과 받기 (Server-Sent Events)
```javascript
const eventSource = new EventSource(`http://localhost:8001/sessions/${session.session_id}/stream`);

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    switch(data.event_type) {
        case 'token':
            // 실시간 중간 결과 (타이핑 중인 텍스트)
            console.log('실시간:', data.data.text);
            updateRealtimeText(data.data.text);
            break;
            
        case 'final':
            // 최종 확정된 결과
            console.log('최종:', data.data.text);
            addFinalResult(data.data.text, data.data.confidence);
            break;
            
        case 'heartbeat':
            // 연결 유지 신호 (무시해도 됨)
            break;
    }
};
```

### 3단계: 오디오 업로드
```javascript
// PCM16 오디오 데이터를 Base64로 인코딩
const audioBase64 = btoa(String.fromCharCode(...new Uint8Array(audioBuffer)));

await fetch(`http://localhost:8001/sessions/${session.session_id}/audio`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        audio_data: audioBase64,
        chunk_id: 'chunk_001'  // 선택사항
    })
});
```

## 📱 완전한 예제 코드

### HTML + JavaScript 예제
```html
<!DOCTYPE html>
<html>
<head>
    <title>실시간 STT 테스트</title>
</head>
<body>
    <h1>🎤 실시간 음성 인식</h1>
    
    <button id="startBtn">🔴 녹음 시작</button>
    <button id="stopBtn" disabled>⏹️ 녹음 중지</button>
    
    <div id="realtime" style="background: #f0f0f0; padding: 20px; margin: 10px 0;">
        실시간 결과가 여기에 표시됩니다...
    </div>
    
    <div id="results"></div>

    <script>
        let sessionId = null;
        let eventSource = null;
        let mediaRecorder = null;
        let isRecording = false;

        // 1. 세션 생성
        async function createSession() {
            const response = await fetch('http://localhost:8001/sessions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    config: { language: 'ko', interim_results: true }
                })
            });
            
            const session = await response.json();
            sessionId = session.session_id;
            console.log('✅ 세션 생성:', sessionId);
            
            // 2. 실시간 스트리밍 연결
            startStreaming();
        }

        // 2. 실시간 결과 받기
        function startStreaming() {
            eventSource = new EventSource(`http://localhost:8001/sessions/${sessionId}/stream`);
            
            eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                
                if (data.event_type === 'token') {
                    // 실시간 중간 결과
                    document.getElementById('realtime').innerHTML = 
                        `⚡ ${data.data.text}<span style="animation: blink 1s infinite;">|</span>`;
                        
                } else if (data.event_type === 'final') {
                    // 최종 결과
                    const resultsDiv = document.getElementById('results');
                    resultsDiv.innerHTML += `
                        <div style="border: 1px solid #ccc; padding: 10px; margin: 5px 0;">
                            <strong>✅ ${data.data.text}</strong>
                            <small style="color: #666;"> (신뢰도: ${data.data.confidence.toFixed(2)})</small>
                        </div>
                    `;
                    
                    // 실시간 영역 초기화
                    document.getElementById('realtime').innerHTML = '다음 음성을 기다리는 중...';
                }
            };
            
            eventSource.onerror = (error) => {
                console.error('❌ 스트리밍 오류:', error);
            };
        }

        // 3. 녹음 시작
        async function startRecording() {
            if (!sessionId) await createSession();
            
            const stream = await navigator.mediaDevices.getUserMedia({ 
                audio: { 
                    sampleRate: 16000,
                    channelCount: 1 
                } 
            });
            
            mediaRecorder = new MediaRecorder(stream);
            const audioChunks = [];
            
            mediaRecorder.ondataavailable = (event) => {
                audioChunks.push(event.data);
            };
            
            mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                const arrayBuffer = await audioBlob.arrayBuffer();
                const audioBase64 = btoa(String.fromCharCode(...new Uint8Array(arrayBuffer)));
                
                // 오디오 업로드
                await fetch(`http://localhost:8001/sessions/${sessionId}/audio`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ audio_data: audioBase64 })
                });
            };
            
            mediaRecorder.start();
            isRecording = true;
            
            document.getElementById('startBtn').disabled = true;
            document.getElementById('stopBtn').disabled = false;
        }

        // 4. 녹음 중지
        function stopRecording() {
            if (mediaRecorder && isRecording) {
                mediaRecorder.stop();
                isRecording = false;
                
                document.getElementById('startBtn').disabled = false;
                document.getElementById('stopBtn').disabled = true;
            }
        }

        // 5. 세션 종료
        async function closeSession() {
            if (sessionId) {
                await fetch(`http://localhost:8001/sessions/${sessionId}`, {
                    method: 'DELETE'
                });
                
                if (eventSource) {
                    eventSource.close();
                }
                
                sessionId = null;
                console.log('✅ 세션 종료');
            }
        }

        // 이벤트 리스너
        document.getElementById('startBtn').onclick = startRecording;
        document.getElementById('stopBtn').onclick = stopRecording;
        window.onbeforeunload = closeSession;
    </script>
    
    <style>
        @keyframes blink { 0%, 50% { opacity: 1; } 51%, 100% { opacity: 0; } }
    </style>
</body>
</html>
```

## 🔧 API 엔드포인트 상세

### 1. 세션 생성
```http
POST /sessions
Content-Type: application/json

{
  "config": {
    "language": "ko",           // 언어 코드 (ko, en, ja, zh 등)
    "interim_results": true,    // 실시간 중간 결과 받기
    "model": "nova-2"          // STT 모델 (기본값)
  }
}
```

**응답:**
```json
{
  "session_id": "sess_abc123",
  "stream_url": "/sessions/sess_abc123/stream",
  "upload_url": "/sessions/sess_abc123/audio",
  "config": { ... }
}
```

### 2. 실시간 스트리밍 (Server-Sent Events)
```http
GET /sessions/{session_id}/stream
Accept: text/event-stream
```

**받는 이벤트 타입:**
- `token`: 실시간 중간 결과
- `final`: 최종 확정 결과  
- `speech_start`: 음성 감지 시작
- `speech_end`: 발화 종료
- `heartbeat`: 연결 유지 신호

### 3. 오디오 업로드
```http
POST /sessions/{session_id}/audio
Content-Type: application/json

{
  "audio_data": "base64_encoded_pcm16_data",
  "chunk_id": "chunk_001",     // 선택사항
  "timestamp": 1704067200.123  // 선택사항
}
```

### 4. 세션 종료
```http
DELETE /sessions/{session_id}
```

## 🎯 오디오 포맷 요구사항

- **포맷**: PCM16 (16-bit Linear PCM)
- **샘플링 레이트**: 16kHz 권장
- **채널**: 모노 (1채널)
- **인코딩**: Base64

## 💡 사용 팁

### 1. 실시간 vs 최종 결과 구분
```javascript
eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.event_type === 'token') {
        // 실시간 결과 - 계속 변경됨 (덮어쓰기)
        realtimeDiv.textContent = data.data.text;
        
    } else if (data.event_type === 'final') {
        // 최종 결과 - 확정됨 (추가하기)
        finalResults.push(data.data.text);
    }
};
```

### 2. 오디오 청크 단위 업로드
```javascript
// 작은 청크로 나누어 업로드 (권장: 1초 단위)
const chunkSize = 16000; // 1초 = 16000 samples
for (let i = 0; i < audioData.length; i += chunkSize) {
    const chunk = audioData.slice(i, i + chunkSize);
    await uploadAudioChunk(chunk, `chunk_${i}`);
}
```

### 3. 에러 처리
```javascript
eventSource.onerror = (error) => {
    console.error('스트리밍 연결 오류:', error);
    // 재연결 로직
    setTimeout(() => {
        startStreaming();
    }, 1000);
};
```

## 🔍 문제 해결

### Q: 실시간 결과가 안 나와요
A: 다음을 확인하세요:
1. `interim_results: true` 설정 확인
2. 오디오 포맷이 PCM16인지 확인
3. 브라우저 콘솔에서 에러 메시지 확인

### Q: 음성 인식 정확도가 낮아요
A: 다음을 시도하세요:
1. 마이크와 입 사이 거리 조절
2. 배경 소음 최소화
3. 명확한 발음으로 말하기

### Q: 연결이 자주 끊어져요
A: `heartbeat` 이벤트를 확인하고 재연결 로직을 구현하세요.

## 📞 지원

- **API 문서**: http://localhost:8001/docs
- **서버 상태**: http://localhost:8001/health
- **문의**: byunghyun@illuni.com 