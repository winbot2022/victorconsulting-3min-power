# app.py
import os
import json
import random
import traceback
import urllib.request
import urllib.error
import streamlit as st

# =========================
# 基本設定（保存なし／画面表示のみ）
# =========================
st.set_page_config(page_title="3分・元気が出る名言診断", page_icon="🌤", layout="centered")
st.title("🌤 3分・元気が出る名言診断")
st.caption("30問からランダムに10問。回答は保存しません。POWERを押すと、その場で名言が表示されます。")

# ============== 環境変数（任意） ==============
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini").strip() or "gpt-4o-mini"
# エラーイベント送信先（任意。設定があればPOSTします）
EVENTS_WEBHOOK_URL = os.getenv("EVENTS_WEBHOOK_URL", "").strip()

# =========================
# 便利: エラーイベント送信（任意）
# =========================
def send_error_event(code: str, detail: str = ""):
    """
    既存の「eventsとして、エラーコードだけ受け取る」仕様を最小維持。
    EVENTS_WEBHOOK_URL が設定されている時のみ JSON POST。未設定なら何もしません。
    JSON 例: {"event":"error","code":"OPENAI_CALL_FAILED","detail":"..."}
    """
    if not EVENTS_WEBHOOK_URL:
        return
    payload = {"event": "error", "code": code, "detail": detail}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        EVENTS_WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            _ = resp.read()
    except Exception:
        # ここでさらに例外を投げない（画面側は静かに継続）
        pass

# =========================
# 質問バンク（30問）: axis = act/conn/acc, polarity = pos/neg
# =========================
CHOICES = {"はい": 2, "どちらでも": 1, "いいえ": 0}
DEFAULT_INDEX = 1
HIGH_THRESH = 60  # 0～100のサブスコアで高い判定

QUESTIONS_BANK = [
    # --- 活力・挑戦（act）10問 ---
    ("朝、起きたとき『今日はやってみよう』と思えることが多いですか？", "act", "pos"),
    ("やるべきことに手をつけるまでの時間は短いほうですか？", "act", "pos"),
    ("最近、新しいことに少しでも興味がわきますか？", "act", "pos"),
    ("うまくいかなくても、また試してみようと思えますか？", "act", "pos"),
    ("先延ばしが増えていると感じますか？", "act", "neg"),
    ("今日は小さな一歩でも進めそうだと感じますか？", "act", "pos"),
    ("目標を立てるのが少しおっくうだと感じますか？", "act", "neg"),
    ("『まずはやってみる』と思える瞬間がありますか？", "act", "pos"),
    ("最近、気力のバッテリーが切れがちだと感じますか？", "act", "neg"),
    ("完璧でなくても動き出せるほうですか？", "act", "pos"),
    # --- つながり・他者（conn）10問 ---
    ("最近、誰かに『ありがとう』と言えましたか？", "conn", "pos"),
    ("困ったら人に頼ってもよいと感じますか？", "conn", "pos"),
    ("一人で抱え込みがちだと感じますか？", "conn", "neg"),
    ("だれかの役に立てたと思える出来事がありましたか？", "conn", "pos"),
    ("会話や雑談の機会が減っていると感じますか？", "conn", "neg"),
    ("弱さを見せても大丈夫だと思える相手がいますか？", "conn", "pos"),
    ("最近、孤立感を覚えることが多いですか？", "conn", "neg"),
    ("ちいさな親切を受け取れた（または渡せた）と感じますか？", "conn", "pos"),
    ("助けを求めるのが苦手だと感じますか？", "conn", "neg"),
    ("人と一緒にやると元気が出やすいと感じますか？", "conn", "pos"),
    # --- 自己受容・安らぎ（acc）10問 ---
    ("『いまは少し休んでもいい』と思えますか？", "acc", "pos"),
    ("最近、自分を責める回数が増えていますか？", "acc", "neg"),
    ("自然や空模様を見て『きれいだな』と感じることがありますか？", "acc", "pos"),
    ("うまくできない自分を許せない、と感じることが多いですか？", "acc", "neg"),
    ("深呼吸すると少し楽になる気がしますか？", "acc", "pos"),
    ("焦りや不安で頭がいっぱいになりがちですか？", "acc", "neg"),
    ("『今日は今日でいい』と思える瞬間がありますか？", "acc", "pos"),
    ("休むことに罪悪感を覚えますか？", "acc", "neg"),
    ("小さな喜びを見つける余裕が少しありますか？", "acc", "pos"),
    ("完璧でない自分を受け入れられそうですか？", "acc", "pos"),
]

# =========================
# 名言カタログ（タイプ別）
# =========================
QUOTE_CATALOG = {
    "RESTART": [
        ("夜明け前がいちばん暗い。", "英語のことわざ"),
        ("休むことも、仕事のうち。", "レオナルド・ダ・ヴィンチ"),
        ("ゆっくりでいい。止まらなければ、必ず着く。", "孔子『論語』意"),
        ("嵐のあとは、道が見える。", "匿名"),
        ("小さな前進は、偉大な停滞より価値がある。", "匿名"),
        ("倒れても、上を向いて倒れなさい。", "チャールズ・チャップリン意"),
    ],
    "CHALLENGE": [
        ("行動こそ、恐れを越える唯一の方法。", "匿名"),
        ("できると思えばできる。思わなければできない。", "ヘンリー・フォード"),
        ("道は歩く者にだけ姿を見せる。", "匿名"),
        ("失敗は、より賢く再挑戦するための授業料。", "ヘンリー・フォード意"),
        ("最初の一歩が、いちばん道を変える。", "匿名"),
        ("やってみなければ、何も始まらない。", "アリストテレス意"),
    ],
    "CALM": [
        ("花は咲く時を、自分で知っている。", "匿名"),
        ("今日は今日を、十分に生きればいい。", "セネカ意"),
        ("木は急がない。それでも、ちゃんと伸びている。", "匿名"),
        ("心を静めることは、次の力を集めること。", "老子意"),
        ("呼吸を整えよ。道はそれからでいい。", "禅語意"),
        ("波が静まれば、水面は空を映す。", "匿名"),
    ],
}
TYPE_LABELS = {
    "RESTART": "再起の光（やさしい背中押し）",
    "CHALLENGE": "挑戦の炎（行動の一押し）",
    "CALM": "静かな充電（受容と整え）",
}

# =========================
# スコアリング
# =========================
def score_item(raw_score: int, polarity: str) -> int:
    # pos: そのまま（0-2）、neg: 逆転（2-raw）
    return raw_score if polarity == "pos" else (2 - raw_score)

def to_percent(subscores) -> int:
    # subscoresは0-2の合計（設問数×0..2） → 0-100へ
    max_total = len(subscores) * 2
    total = sum(subscores)
    if max_total == 0:
        return 0
    return int(round(total / max_total * 100))

def pick_type(act, conn, acc) -> str:
    # 単純・頑健：高い軸があればそちら、拮抗/全体低めならRESTART
    if act >= HIGH_THRESH and act >= acc and act >= conn:
        return "CHALLENGE"
    if acc >= HIGH_THRESH and acc >= act and acc >= conn:
        return "CALM"
    return "RESTART"

# =========================
# OpenAIで最適名言を選ぶ（キーなし→ローカル代替）
# =========================
def select_quote_with_ai(summary, candidates):
    """
    summary: {"act": int, "conn": int, "acc": int, "type": str, "answers":[{q,axis,polarity,choice,score}]}
    candidates: [{"text": "...", "source": "..."}]  # 3件程度
    return: {"text": "...", "source": "...", "comment": "..."}  # commentは短い補足
    """
    if not OPENAI_API_KEY:
        # ローカル代替（最初の候補＋タイプに応じた短評）
        base = {
            "RESTART": "いまは息を整えて、小さな一歩を。ゆっくりでも進めば必ず変わります。",
            "CHALLENGE": "考えるよりまず一歩。小さく動くほど、恐れは小さくなります。",
            "CALM": "休むことは前進の準備。深呼吸から、静かな力が戻ってきます。",
        }[summary["type"]]
        return {"text": candidates[0]["text"], "source": candidates[0]["source"], "comment": base}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        sys = (
            "あなたは短い励ましに長けた編集者です。ユーザーの回答傾向（act/conn/accスコアとタイプ）を読み、"
            "提示された候補の中から“いま最も刺さる”名言を厳選してください。"
            "出力はJSONのみ。キーは text, source, comment。commentは80〜120字の日本語で、"
            "優しく具体的な一歩を促す短評にしてください。余計な文は出さないでください。"
        )
        usr = {"summary": summary, "candidates": candidates}
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": json.dumps(usr, ensure_ascii=False)}
            ],
            temperature=0.4,
            max_tokens=300,
        )
        content = resp.choices[0].message.content.strip()
        data = json.loads(content)
        if not all(k in data for k in ("text", "source", "comment")):
            raise ValueError("Invalid AI response schema")
        return data
    except Exception as e:
        # 失敗時はイベント送信＋フォールバック
        send_error_event("OPENAI_CALL_FAILED", f"{type(e).__name__}: {e}")
        base = {
            "RESTART": "いまは息を整えて、小さな一歩を。ゆっくりでも進めば必ず変わります。",
            "CHALLENGE": "考えるよりまず一歩。小さく動くほど、恐れは小さくなります。",
            "CALM": "休むことは前進の準備。深呼吸から、静かな力が戻ってきます.",
        }[summary["type"]]
        return {"text": candidates[0]["text"], "source": candidates[0]["source"], "comment": base}

# =========================
# ランダム10問の選出（セッション固定）
# =========================
if "question_indices" not in st.session_state:
    st.session_state.question_indices = random.sample(range(len(QUESTIONS_BANK)), 10)

indices = st.session_state.question_indices

with st.form("diagnosis"):
    st.subheader("質問（ランダム10問）")
    answers = []  # (text, axis, polarity, choice_label, scored_value)
    for i, idx in enumerate(indices, start=1):
        qtext, axis, polarity = QUESTIONS_BANK[idx]
        choice = st.radio(
            f"Q{i}. {qtext}",
            list(CHOICES.keys()),
            horizontal=True,
            index=DEFAULT_INDEX
        )
        raw = CHOICES[choice]
        scored = score_item(raw, polarity)
        answers.append((qtext, axis, polarity, choice, scored))

    # ========== POWER ボタン ==========
    # ⏻ (power symbol) / "POWER"
    submitted = st.form_submit_button("⏻  POWER", use_container_width=True)

if submitted:
    try:
        # サブスコア算出（今回の10問に対して）
        act_scores = [a[4] for a in answers if a[1] == "act"]
        conn_scores = [a[4] for a in answers if a[1] == "conn"]
        acc_scores = [a[4] for a in answers if a[1] == "acc"]

        act = to_percent(act_scores)
        conn = to_percent(conn_scores)
        acc = to_percent(acc_scores)

        user_type = pick_type(act, conn, acc)

        # 候補（タイプ毎にシャッフル→上位3件）
        cands = QUOTE_CATALOG[user_type][:]
        random.shuffle(cands)
        top_candidates = [{"text": t, "source": s} for (t, s) in cands[:3]]

        summary = {
            "act": act, "conn": conn, "acc": acc, "type": user_type,
            "answers": [{"q": a[0], "axis": a[1], "polarity": a[2], "choice": a[3], "score": a[4]} for a in answers]
        }

        result = select_quote_with_ai(summary, top_candidates)

        st.success("診断が完了しました。データは保存していません。")
        with st.container(border=True):
            st.markdown(f"**タイプ**：{TYPE_LABELS[user_type]}")
            st.markdown(f"**あなたに贈る一言**：\n\n> **{result['text']}**\n\n— *{result['source']}*")
            st.markdown(f"**ひとこと解説**：{result['comment']}")

        with st.expander("サブスコアを見る（任意）"):
            st.write({
                "活力・挑戦（activation）": act,
                "つながり（connection）": conn,
                "自己受容（acceptance）": acc
            })

        st.caption("※本ツールは診断・医療行為ではありません。今日の気持ちに寄り添う“言葉の処方箋”です。")

    except Exception as e:
        # 画面にやさしく表示＋イベント送信
        err_detail = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        send_error_event("APP_RUNTIME_ERROR", err_detail)
        st.error("申し訳ありません。処理中にエラーが発生しました。もう一度お試しください。")













