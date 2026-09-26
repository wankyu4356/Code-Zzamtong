"""
두벌식 한글 타이핑 시뮬레이터.
keystrokes(text)  -> 실제 키 입력 순서 (자모 단위. ㅘ는 ㅗ,ㅏ 두 번. 쌍자음은 한 번)
states(text)      -> 키를 하나씩 누를 때마다 화면에 보이는 문자열 목록 (입력기의 중간 조합 포함. 예: 지, 진, 짅, 진자)
"""
CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
V_COMB = {("ㅗ", "ㅏ"): "ㅘ", ("ㅗ", "ㅐ"): "ㅙ", ("ㅗ", "ㅣ"): "ㅚ", ("ㅜ", "ㅓ"): "ㅝ", ("ㅜ", "ㅔ"): "ㅞ", ("ㅜ", "ㅣ"): "ㅟ", ("ㅡ", "ㅣ"): "ㅢ"}
J_COMB = {("ㄱ", "ㅅ"): "ㄳ", ("ㄴ", "ㅈ"): "ㄵ", ("ㄴ", "ㅎ"): "ㄶ", ("ㄹ", "ㄱ"): "ㄺ", ("ㄹ", "ㅁ"): "ㄻ", ("ㄹ", "ㅂ"): "ㄼ",
          ("ㄹ", "ㅅ"): "ㄽ", ("ㄹ", "ㅌ"): "ㄾ", ("ㄹ", "ㅍ"): "ㄿ", ("ㄹ", "ㅎ"): "ㅀ", ("ㅂ", "ㅅ"): "ㅄ"}
V_SPLIT = {v: k for k, v in V_COMB.items()}
J_SPLIT = {v: k for k, v in J_COMB.items()}
VOWELS = set(JUNG)
CONS = set(CHO) | set(JONG.strip())


def _compose(cho, jung, jong):
    return chr(0xAC00 + CHO.index(cho) * 588 + JUNG.index(jung) * 28 + JONG.index(jong))


def keystrokes(text):
    keys = []
    for ch in text:
        o = ord(ch)
        if 0xAC00 <= o <= 0xD7A3:
            i = o - 0xAC00
            cho, jung, jong = CHO[i // 588], JUNG[(i % 588) // 28], JONG[i % 28]
            keys.append(cho)
            keys.extend(V_SPLIT.get(jung, (jung,)))
            if jong != " ":
                keys.extend(J_SPLIT.get(jong, (jong,)))
        else:
            keys.append(ch)
    return keys


class _IME:
    def __init__(self):
        self.out = []
        self.cho = None
        self.jung = None
        self.jong = None

    def _flush(self):
        if self.cho and self.jung:
            self.out.append(_compose(self.cho, self.jung, self.jong or " "))
        elif self.cho:
            self.out.append(self.cho)
        elif self.jung:
            self.out.append(self.jung)
        self.cho = self.jung = self.jong = None

    def key(self, k):
        if k in VOWELS:
            if self.cho and self.jung is None:
                self.jung = k
            elif self.cho and self.jung and self.jong is None and (self.jung, k) in V_COMB:
                self.jung = V_COMB[(self.jung, k)]
            elif self.cho and self.jung and self.jong:
                # 받침을 다음 글자의 초성으로 넘긴다 (짅 + ㅏ -> 진자)
                if self.jong in J_SPLIT:
                    keep, move = J_SPLIT[self.jong]
                    self.jong = keep
                else:
                    move = self.jong
                    self.jong = None
                self._flush()
                self.cho, self.jung = move, k
            else:
                self._flush()
                self.jung = k
        elif k in CONS:
            if self.cho is None and self.jung is None:
                self.cho = k
            elif self.cho and self.jung is None:
                self._flush()
                self.cho = k
            elif self.cho and self.jung and self.jong is None and k in JONG:
                self.jong = k
            elif self.cho and self.jung and self.jong and (self.jong, k) in J_COMB:
                self.jong = J_COMB[(self.jong, k)]
            else:
                self._flush()
                self.cho = k
        else:
            self._flush()
            self.out.append(k)

    def text(self):
        cur = ""
        if self.cho and self.jung:
            cur = _compose(self.cho, self.jung, self.jong or " ")
        elif self.cho:
            cur = self.cho
        elif self.jung:
            cur = self.jung
        return "".join(self.out) + cur


def states(text):
    ime = _IME()
    out = []
    for k in keystrokes(text):
        ime.key(k)
        out.append(ime.text())
    return out


if __name__ == "__main__":
    import sys
    t = sys.argv[1] if len(sys.argv) > 1 else "진작 올걸 그랬어요!"
    ks = keystrokes(t)
    print(len(ks), "keys:", " ".join(ks))
    for s in states(t):
        print(repr(s))
