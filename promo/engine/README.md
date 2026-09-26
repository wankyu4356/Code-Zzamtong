# promo/engine

병원 브랜드 필름용 작은 렌더링 엔진. 검은 화면 위에 큰 흰 타이포가 비트마다 떨어지고, 실사 푸티지 위에 단어 하나가 얹히는
애플 티저 식 컷 편집을 JSON 타임라인 하나로 만든다. 모든 컷은 프레임 경계에 정확히 맞고, 같은 입력이면 같은 결과가 나온다.

## 구조

```
timeline.json  ->  build_footage.py  ->  build/footage.mp4      (ffmpeg, 영상만, 정확한 프레임 수)
               ->  render_overlay.mjs ->  build/overlay/%05d.png (헤드리스 크로미움, 투명 PNG)
               ->  compose.py         ->  build/out.mp4          (footage + overlay + 오디오)
run.py 가 위 세 단계를 순서대로 실행한다.
```

- `timeline.py` 타임라인 로드와 검증, 프레임 계산 (다른 스크립트가 공유)
- `build_footage.py` 샷마다 ffmpeg를 한 번씩 돌려 세그먼트를 만들고 concat. 실패하면 해당 샷의 ffmpeg 명령을 그대로 출력한다
- `overlay.html` + `render_overlay.mjs` 그래픽 레이어. `window.render(frame)`은 프레임 번호만의 함수이고 CSS 트랜지션이나 rAF를 쓰지 않는다
- `compose.py` 합성과 최종 인코딩
- `timeline.schema.md` 타임라인 포맷 문서
- `examples/demo_timeline.json` 10초 데모

## 요구사항

- ffmpeg 6 (libx264, aac)
- Node 22 + Playwright (크로미움). 경로는 `render_overlay.mjs` 상단과 `CHROME_BIN` 환경변수로 바꿀 수 있다
- Python 3.11 (표준 라이브러리만 사용)
- 시스템 폰트 Pretendard, Noto Sans CJK KR

## 사용법

```bash
cd promo/engine

# 전체 파이프라인 (기본 빌드 폴더는 timeline.json 옆의 build/)
python3 run.py path/to/timeline.json --build /path/to/build

# 960x540 프리뷰도 같이
python3 run.py timeline.json --build build --preview

# 텍스트만 고쳤을 때: 푸티지 재사용
python3 run.py timeline.json --build build --skip-footage

# 푸티지만 고쳤을 때: 오버레이 재사용
python3 run.py timeline.json --build build --skip-overlay

# 단계별 실행
python3 build_footage.py timeline.json --build build
/opt/node22/bin/node render_overlay.mjs --timeline timeline.json --out build/overlay
/opt/node22/bin/node render_overlay.mjs --timeline timeline.json --out build/overlay --only-shot s03
/opt/node22/bin/node render_overlay.mjs --timeline timeline.json --out build/overlay --from 120 --to 149
python3 compose.py timeline.json --build build [--preview] [--out final.mp4]
```

`--from/--to`는 전역 프레임 번호이고 양 끝을 포함한다. 부분 렌더 뒤에는 PNG가 모두 있어야 compose가 진행된다 (빠진 프레임이 있으면 번호를 알려주고 멈춘다).

## 산출물

- `build/segments/<id>.mp4` 샷별 세그먼트 (crf 16)
- `build/footage.mp4` 1920x1080 30fps yuv420p, 오디오 없음
- `build/overlay/00000.png ...` 투명 PNG, 프레임당 하나
- `build/out.mp4` libx264 crf 17 preset slow, aac 256k, faststart
- `build/preview.mp4` (--preview) 960x540 crf 24

## 데모

`examples/demo_timeline.json`은 10.0초, 300프레임짜리 예제다. 클립은 ffmpeg 합성 영상(testsrc2, smptebars, gradients)이고
세션 스크래치 폴더를 상대 경로로 가리키는 대역이다. 실제 푸티지로 바꾸려면 `bg.src`만 교체하면 된다.

```bash
# 대역 클립 만들기 (원하는 폴더에서)
ffmpeg -f lavfi -i "testsrc2=s=1920x1080:r=30" -t 4 -c:v libx264 -crf 18 -pix_fmt yuv420p clip_a.mp4
ffmpeg -f lavfi -i "smptebars=s=1920x1080:r=30" -t 4 -c:v libx264 -crf 18 -pix_fmt yuv420p clip_b.mp4
ffmpeg -f lavfi -i "gradients=s=1920x1080:r=30:speed=0.08:nb_colors=4:seed=7" -t 4 -c:v libx264 -crf 18 -pix_fmt yuv420p clip_c.mp4
```

10초 데모 기준 시간: 푸티지 약 16초, 오버레이 약 6초, 최종 합성 약 16초 (preset slow), 프리뷰 약 7초.

## 알아둘 점

- 줌은 zoompan 대신 프레임 번호 n으로 구동하는 scale(eval=frame) + crop 조합을 쓴다. zoompan보다 두 배쯤 빠르고 중앙이 정확하다.
  크롭 오프셋은 정수 픽셀이라 아주 느린 줌에서는 1px 단위의 미세한 흔들림이 있을 수 있다.
- vignette 필터는 느리다 (1080p 기준 프레임당 20ms 정도). 필요한 샷에만 켠다.
- 오버레이는 프레임 상태가 직전 프레임과 같으면 스크린샷 대신 파일을 복사한다. 정지 자막이 대부분이라 실제 스크린샷은 전체의 1/4 정도다.
  스크린샷 하나는 약 55ms.
- 크로미움 페이지 안에서 `<video>`를 쓰지 않는다. 푸티지는 전부 ffmpeg가 다룬다.
- 오디오는 영상 길이에 맞춰 자르고, 짧으면 무음으로 채운다 (apad).
