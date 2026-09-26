# 배경음악 제작 (프로시저럴 신스)

외부 샘플이나 라이브러리 음원 없이 numpy로 소리를 직접 합성한다. 저작권 문제가 없고,
영상의 박자(120 BPM, 1박 0.5초)에 임팩트 시점을 정확히 맞출 수 있다.

## 파일

| 파일 | 역할 |
|---|---|
| `synth.py` | 악기와 효과. 킥, 서브베이스, 클랩, 하이햇, 임팩트(쾅), 라이저, 다운리프터, 패드, 플럭, 벨, 틱 |
| `compose.py` | `score.json`을 읽어 구간별 패턴과 이벤트를 배치하고 믹스·마스터링해 wav로 출력 |
| `score_sketch.json` | 구성안 확정 전 방향 확인용 스케치 스코어 (46초) |

## 실행

```bash
pip install numpy soundfile pedalboard
python3 compose.py score_sketch.json out.wav
```

## score.json 형식

```json
{
  "bpm": 120, "duration": 46.0, "key_root": "D",
  "sections": [ {"start": 0, "end": 8, "pattern": "pulse"} ],
  "events":   [ {"t": 0.0, "type": "impact", "gain": 1.0} ]
}
```

- `pattern`: `silence`, `pulse`(서브 한 방과 아주 작은 햇), `build`(패드와 16분 햇, 마지막 두 마디 킥 예고), `drop`(킥 4박, 클랩 2·4박, 서브, 패드, 플럭), `groove`(드롭에서 클랩·플럭을 뺀 것), `outro`(패드 꼬리)
- `events`: `impact`(긴 쾅), `impact_short`(짧은 쾅, 연타용), `tick`(글자 등장용 클릭), `riser`(len초 상승), `downlifter`, `bell`, `sub_hit`, `cut`(len초 완전 정적)

## 사운드 설계 원칙

- 조성은 D단조, 진행은 i, i, VI, VII. 애플 티저처럼 절제된 전자음 위주
- 킥마다 패드·플럭·서브가 눌리는 사이드체인으로 펌핑감을 만든다
- 임팩트는 저역 붐과 2.6kHz 이하로 깎은 노이즈 폭발. 고역을 열어두면 싸구려 느낌이 나서 막았다
- 마스터 목표: 통합 라우드니스 약 -13.5 LUFS, 피크 -1 dBFS. 유튜브·인스타 업로드 기준에 맞춘다
