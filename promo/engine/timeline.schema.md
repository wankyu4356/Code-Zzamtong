# timeline.json 스키마

영상 한 편을 "샷(shot)"의 나열로 기술한다. 샷은 배경(bg) 하나와 그 위에 얹는 텍스트, 카드, 플래시를 가진다.
모든 시간은 초 단위의 절대 시간이고, 모든 컷은 프레임 경계에 정확히 떨어진다.

```json
{
  "fps": 30, "width": 1920, "height": 1080, "duration": 10.0,
  "audio": "music.wav",
  "shots": [
    {
      "id": "s01", "start": 0.0, "end": 2.0,
      "bg": { "type": "black" },
      "texts": [ { "text": "아침에", "start": 0.0, "end": 0.5, "size": 220, "anim_in": "hit" } ],
      "cards": [],
      "flashes": []
    }
  ]
}
```

## 최상위

| 키 | 타입 | 설명 |
|---|---|---|
| fps | int | 프레임 레이트. 30 권장 |
| width, height | int(짝수) | 출력 해상도 |
| duration | number | 전체 길이(초). 마지막 샷의 end와 같아야 한다 |
| audio | string 또는 null | 오디오 파일 경로(wav 등). 영상 길이에 맞춰 자르거나 무음으로 채운다 |
| shots | array | 샷 목록. 시간순으로 [0, duration]을 빈틈이나 겹침 없이 채워야 한다 |

경로("audio", bg의 "src")는 절대 경로이거나 timeline.json이 있는 폴더 기준의 상대 경로다.

## 프레임 규칙

- 프레임 번호 = floor(초 * fps + 0.5). Python과 JS가 같은 식을 쓴다.
- 샷의 start_f = 이전 샷의 end_f (첫 샷은 0), end_f = round(end * fps). 샷 프레임 수 = end_f - start_f.
- 샷의 end는 프레임 경계에 있어야 한다 (30fps에서 0.5, 2.0, 4.1은 되고 0.333은 안 된다). 아니면 검증 에러.
- 따라서 footage.mp4의 세그먼트와 overlay PNG는 항상 같은 프레임 수를 가진다. 도구가 ffprobe로 재확인한다.
- 텍스트, 카드, 플래시의 시간도 절대 초다. 샷 범위 밖으로 걸쳐도 되지만 (컷을 넘어가는 자막) 보통은 샷 안에 둔다.
- 요소가 보이는 프레임: start_f <= f < end_f. end 프레임에서는 이미 사라져 있다.

## shot

| 키 | 타입 | 설명 |
|---|---|---|
| id | string | 고유 이름. 세그먼트 파일명과 --only-shot에 쓴다 |
| start, end | number | 초. end > start |
| bg | object | 배경 |
| texts | array | 텍스트 요소 (선택) |
| cards | array | 카드 요소 (선택) |
| flashes | array | 플래시 (선택) |

## bg

| 키 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| type | "black" \| "white" \| "color" \| "clip" \| "image" | 필수 | |
| color | string | | type이 color일 때 "#1a1a1a" 형식 |
| src | string | | clip/image 파일 경로 |
| punch | number | 1.0 | 정적 펀치인 배율. 1.3이면 30% 확대한 상태에서 시작 |
| fade_in, fade_out | int | 0 | 샷 시작·끝의 페이드 프레임 수. fade_color(black 기본, white)로 |
| anchor | [x, y] | [0.5, 0.5] | 크롭 기준점(확대된 프레임의 비율). [0.5, 0.2]면 위쪽을 남긴다 |
| in | number | 0 | 클립 인 포인트(초) |
| speed | number | 1.0 | 재생 속도. 2.0이면 두 배 빠르게. 소스가 speed * 샷길이 만큼 필요하다 |
| fit | "cover" | cover | 화면을 꽉 채우도록 확대 후 중앙 크롭. 현재 cover만 지원 |
| zoom | "in" \| "out" \| "none" | none | 샷 길이에 걸친 느린 줌 |
| zoom_amount | number | 0.06 | 줌 비율. 0.06이면 1.00에서 1.06까지 |
| grade | object | 전부 기본값 | contrast(1.0), saturation(1.0), brightness(0.0), gamma(1.0). ffmpeg eq 필터 |
| vignette | bool | false | 비네트 (ffmpeg vignette 기본 강도). 느린 편이다 |
| grain | number 0..1 | 0 | 필름 그레인. 0.05 ~ 0.15 정도가 자연스럽다 (ffmpeg noise alls = grain*100) |

클립이 필요한 길이보다 짧으면 마지막 프레임을 조용히 멈춰 두지 않고 에러를 낸다.

## texts[]

| 키 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| text | string | 필수 | "\n"으로 줄바꿈 |
| start, end | number | 필수 | 절대 초 |
| size | number | 200 | px |
| weight | number | 900 | Pretendard 100..900 |
| color | string | "#fff" | CSS 색 |
| x | "center" \| "left" \| "right" \| number | center | number면 왼쪽 여백 px. left/right는 96px 안전 여백 |
| y | "center" \| "top" \| "bottom" \| number | center | number면 위쪽 여백 px. top/bottom은 96px 안전 여백 |
| letter_spacing | number | -0.04 | em 단위 |
| line_height | number | 1.05 | |
| max_width | number | 1500 | px. 넘으면 단어 단위(keep-all)로 줄바꿈 |
| align | "center" \| "left" \| "right" | center | 여러 줄일 때 정렬 |
| shadow | bool | true | 0 2px 24px rgba(0,0,0,.55) 텍스트 그림자 |
| anim_in | "hit" \| "slam" \| "fade" \| "rise" \| "none" | hit | |
| anim_out | "cut" \| "fade" \| "none" | cut | |

텍스트와 이미지 공통 선택 키: `in_frames`(등장 프레임 수 덮어쓰기), `out_frames`(퇴장 페이드 프레임 수, 기본 5), `hit_scale`(hit·slam 시작 배율, 기본 1.10·1.7), `drift_scale`(보이는 동안 선형으로 커지는 느린 줌, 예 0.03).

## images (로고 등 이미지 레이어)

| 키 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| src | string | 필수 | PNG(투명 배경 권장) 경로. 절대 경로 또는 timeline.json 기준 상대 경로 |
| start, end | number | 필수 | 절대 초 |
| width | number | 900 | 표시 너비(px). 높이는 비율대로 |
| x, y | "center" \| "left" \| "right" \| "top" \| "bottom" \| px | center | 위치. 텍스트와 같은 규칙 |
| anim_in | hit \| slam \| fade \| rise \| none | fade | 등장 |
| anim_out | cut \| fade \| none | cut | 퇴장 |
| opacity | 0~1 | 1 | 최대 불투명도 |

흰색 로고에서 원본 색 로고로 바꾸려면 같은 위치에 두 개를 이어 붙인다 (앞 것은 anim_out cut, 뒤 것은 anim_in none 또는 fade).

## typing[] (리뷰를 실제로 치는 장면)

| 키 | 타입 | 설명 |
|---|---|---|
| text | string | 최종 문장 |
| start, end | number | 카드가 보이는 절대 초 |
| keys | number[] | 키 하나가 눌리는 절대 초. `engine/hangul.py`가 두벌식 키 순서를 만든다 |
| states | string[] | 키마다 화면에 보이는 문자열 (자모 조합 중간 상태 포함) |
| post_at | number | 등록 버튼이 눌리는 절대 초. 이후 커서가 사라지고 버튼이 파랗게 된다 |
| nick, chip, date | string | 카드 머리의 닉네임, 출처 칩, 날짜 |
| width, x, y, anim_in, anim_out, in_frames, out_frames | | 텍스트와 같은 규칙 (기본 1240px, 중앙, rise) |

## cards[]

| 키 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| type | "review" | 필수 | 어두운 반투명 라운드 카드: 별점 줄, 리뷰 본문(44px, 600, 최대 3줄), 출처(28px, 60%) |
| start, end | number | 필수 | |
| stars | int 0..5 | 5 | 채워진 별 개수 |
| text | string | 필수 | 리뷰 본문 |
| source | string | "" | 예: "네이버 방문자 리뷰" |
| width | number | 1100 | px |
| x, y | | center | texts와 같은 규칙 |
| anim_in | | rise | texts와 같은 종류 |
| anim_out | | cut | |

## flashes[]

| 키 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| at | number | 필수 | 시작 초 |
| frames | int | 2 | 지속 프레임 수 |
| color | string | "#fff" | |
| opacity | number 0..1 | 0.9 | |

플래시는 모든 텍스트와 카드 위에 그려진다. "slam" 텍스트와 같은 프레임에 두면 컷 어택이 강해진다.

## 애니메이션 (30fps 기준 프레임 수, lf = 시작 후 경과 프레임)

기하(스케일, 위치) 램프는 p = lf / n 으로 계산해서 프레임 0에 시작값이 그대로 보이고 프레임 n에 끝값에 닿는다.
불투명도 램프는 p = (lf + 1) / n 으로 계산해서 프레임 0이 1/n, 프레임 n-1이 1이다 (완전히 투명한 프레임을 낭비하지 않는다).
ease-out cubic: e = 1 - (1 - p)^3.

| anim_in | 동작 |
|---|---|
| hit | 스케일 1.10에서 1.00으로 4프레임 ease-out. 블러 1px에서 0으로 같은 곡선. 불투명도 1 |
| slam | 스케일 1.7에서 1.0으로 3프레임 ease-out, 불투명도 0에서 1로 2프레임. 플래시와 짝 |
| fade | 불투명도 0에서 1로 8프레임, y 오프셋 12px에서 0으로 선형 |
| rise | 불투명도 0에서 1로 6프레임, y 오프셋 40px에서 0으로 ease-out |
| none | 정적 |

| anim_out | 동작 |
|---|---|
| cut | end 프레임에서 바로 사라진다 |
| fade | 끝나기 전 5프레임 동안 불투명도 1.0, 0.8, 0.6, 0.4, 0.2 |
| none | cut과 같다 |

## 검증

`timeline.py`의 load()가 다음을 확인하고 위반 항목을 모두 모아 한 번에 에러로 낸다.

- fps 양의 정수, width/height 양의 짝수, duration > 0
- 첫 샷 start = 0, 각 샷 start = 이전 샷 end (오차 1e-6), 마지막 end = duration
- 샷 end가 프레임 경계 위에 있음, 샷 길이가 1프레임 이상, id 중복 없음
- bg.type, zoom, fit, speed > 0, in >= 0, grain 0..1, grade 키와 숫자 여부, src/audio 파일 존재
- texts/cards/flashes의 필수 키와 anim 이름, stars 범위, frames >= 1
