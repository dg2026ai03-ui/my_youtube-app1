import streamlit as st
import pandas as pd
import re
import io
import plotly.express as px
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ============================================
# 페이지 설정
# ============================================
st.set_page_config(
    page_title="유튜브 댓글 수집기",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 유튜브 댓글 수집기")
st.caption("유튜브 영상 링크를 입력하면 댓글을 수집하고 분석합니다")

# ============================================
# API 키 설정
# ============================================
api_key = ""
try:
    api_key = st.secrets["YOUTUBE_API_KEY"]
except Exception:
    pass

if not api_key:
    st.sidebar.markdown("### 🔑 API 키 설정")
    api_key = st.sidebar.text_input(
        "YouTube API Key",
        type="password",
        placeholder="AIza..."
    )

if not api_key:
    st.info(
        "👈 사이드바에서 YouTube API 키를 입력해주세요.\n\n"
        "**발급 방법:**\n"
        "1. [Google Cloud Console](https://console.cloud.google.com/) 접속\n"
        "2. 프로젝트 생성 → YouTube Data API v3 사용 설정\n"
        "3. 사용자 인증 정보 → API 키 만들기"
    )
    st.stop()

# ============================================
# YouTube 클라이언트
# ============================================
youtube = build("youtube", "v3", developerKey=api_key)

# ============================================
# 사이드바 옵션
# ============================================
st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ 수집 옵션")
max_comments = st.sidebar.slider("최대 댓글 수", 10, 500, 100, 10)
order = st.sidebar.radio(
    "정렬 기준",
    ["relevance", "time"],
    format_func=lambda x: "인기순 🔥" if x == "relevance" else "최신순 🕐"
)
include_replies = st.sidebar.checkbox("답글(대댓글)도 수집", value=False)

# ============================================
# 함수 정의
# ============================================
def extract_video_id(url):
    patterns = [
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for pattern in patterns:
        match = re.search(pattern, url.strip())
        if match:
            return match.group(1)
    return None


def get_video_info(video_id):
    try:
        response = youtube.videos().list(
            part="snippet,statistics",
            id=video_id
        ).execute()
        if response.get("items"):
            item = response["items"][0]
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            thumbs = snippet.get("thumbnails", {})
            thumb = thumbs.get("high", thumbs.get("medium", thumbs.get("default", {})))
            return {
                "title": snippet.get("title", ""),
                "channel": snippet.get("channelTitle", ""),
                "published": snippet.get("publishedAt", "")[:10],
                "thumbnail": thumb.get("url", ""),
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
            }
    except Exception:
        pass
    return None


def get_comments(video_id):
    results = []
    next_token = None
    try:
        while len(results) < max_comments:
            part = "snippet,replies" if include_replies else "snippet"
            response = youtube.commentThreads().list(
                part=part,
                videoId=video_id,
                maxResults=min(100, max_comments - len(results)),
                order=order,
                pageToken=next_token,
                textFormat="plainText"
            ).execute()

            for item in response.get("items", []):
                top = item["snippet"]["topLevelComment"]["snippet"]
                results.append({
                    "작성자": top.get("authorDisplayName", ""),
                    "댓글": top.get("textDisplay", ""),
                    "좋아요": int(top.get("likeCount", 0)),
                    "작성일": top.get("publishedAt", "")[:10],
                    "답글수": int(item["snippet"].get("totalReplyCount", 0)),
                    "유형": "댓글",
                })

                if include_replies and "replies" in item:
                    for reply in item["replies"].get("comments", []):
                        rs = reply.get("snippet", {})
                        results.append({
                            "작성자": rs.get("authorDisplayName", ""),
                            "댓글": rs.get("textDisplay", ""),
                            "좋아요": int(rs.get("likeCount", 0)),
                            "작성일": rs.get("publishedAt", "")[:10],
                            "답글수": 0,
                            "유형": "답글",
                        })

            next_token = response.get("nextPageToken")
            if not next_token:
                break

    except HttpError as e:
        if "commentsDisabled" in str(e):
            st.warning("⚠️ 댓글이 비활성화된 영상입니다.")
        else:
            st.error(f"오류: {e}")
    return results


def simple_sentiment(text):
    pos = ["좋아", "최고", "대박", "감동", "멋지", "훌륭", "사랑", "추천", "완벽",
           "굿", "짱", "재밌", "웃기", "힐링", "감사", "응원", "화이팅", "레전드",
           "good", "great", "best", "love", "amazing", "awesome", "nice"]
    neg = ["싫어", "별로", "최악", "실망", "짜증", "지루", "노잼", "쓰레기",
           "나쁘", "혐오", "bad", "worst", "hate", "terrible", "boring", "ugly"]
    t = text.lower()
    p = sum(1 for w in pos if w in t)
    n = sum(1 for w in neg if w in t)
    if p > n:
        return "긍정 😊"
    elif n > p:
        return "부정 😠"
    return "중립 😐"


# ============================================
# 메인 UI
# ============================================
st.markdown("---")
url = st.text_input(
    "🔗 유튜브 링크",
    placeholder="https://www.youtube.com/watch?v=..."
)

if st.button("🔍 댓글 수집 시작", type="primary", use_container_width=True):

    if not url:
        st.warning("링크를 입력해주세요.")
        st.stop()

    video_id = extract_video_id(url)
    if not video_id:
        st.error("올바른 유튜브 URL이 아닙니다.")
        st.stop()

    # ── 영상 정보 ──
    with st.spinner("영상 정보 로딩..."):
        info = get_video_info(video_id)

    if info:
        st.markdown("---")
        c1, c2 = st.columns([1, 2])
        with c1:
            if info["thumbnail"]:
                st.image(info["thumbnail"], use_container_width=True)
        with c2:
            st.subheader(info["title"])
            st.write(f"**{info['channel']}** · {info['published']}")
            m1, m2, m3 = st.columns(3)
            m1.metric("👁️ 조회수", f"{info['views']:,}")
            m2.metric("👍 좋아요", f"{info['likes']:,}")
            m3.metric("💬 댓글", f"{info['comments']:,}")

    # ── 댓글 수집 ──
    with st.spinner(f"댓글 수집 중... (최대 {max_comments}개)"):
        comments = get_comments(video_id)

    if not comments:
        st.warning("수집된 댓글이 없습니다.")
        st.stop()

    df = pd.DataFrame(comments)
    df["감성"] = df["댓글"].apply(simple_sentiment)
    df["글자수"] = df["댓글"].str.len()

    comment_count = len(df[df["유형"] == "댓글"])
    reply_count = len(df[df["유형"] == "답글"])
    st.success(f"✅ 총 {len(df)}개 수집 완료! (댓글 {comment_count}개 + 답글 {reply_count}개)")

    # ── 탭 구성 ──
    tab1, tab2, tab3, tab4 = st.tabs([
        "💬 댓글 보기", "📊 통계", "😊 감성 분석", "📥 다운로드"
    ])

    # ── TAB 1: 댓글 보기 ──
    with tab1:
        search = st.text_input("🔍 댓글 검색", placeholder="키워드...", key="s1")
        filtered = df.copy()
        if search:
            filtered = filtered[filtered["댓글"].str.contains(search, case=False, na=False)]
            st.info(f"검색 결과: {len(filtered)}개")

        sort_col = st.selectbox(
            "정렬",
            ["기본순", "좋아요 높은순", "최신순", "글자수 긴순"]
        )
        if sort_col == "좋아요 높은순":
            filtered = filtered.sort_values("좋아요", ascending=False)
        elif sort_col == "최신순":
            filtered = filtered.sort_values("작성일", ascending=False)
        elif sort_col == "글자수 긴순":
            filtered = filtered.sort_values("글자수", ascending=False)

        st.dataframe(
            filtered[["유형", "작성자", "댓글", "좋아요", "감성", "작성일"]],
            use_container_width=True,
            height=500
        )

    # ── TAB 2: 통계 ──
    with tab2:
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("총 수집", f"{len(df)}개")
        s2.metric("평균 좋아요", f"{df['좋아요'].mean():.1f}")
        s3.metric("최다 좋아요", f"{df['좋아요'].max()}")
        s4.metric("평균 글자수", f"{df['글자수'].mean():.0f}자")

        st.markdown("---")

        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown("#### 👍 좋아요 분포")
            fig1 = px.histogram(df, x="좋아요", nbins=30, color_discrete_sequence=["#FF0000"])
            fig1.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig1, use_container_width=True)

        with col_b:
            st.markdown("#### 📝 글자수 분포")
            fig2 = px.histogram(df, x="글자수", nbins=30, color_discrete_sequence=["#0066ff"])
            fig2.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("---")

        col_c, col_d = st.columns(2)

        with col_c:
            st.markdown("#### 📅 날짜별 댓글 수")
            date_counts = df.groupby("작성일").size().reset_index(name="댓글수")
            date_counts = date_counts.sort_values("작성일")
            fig3 = px.line(date_counts, x="작성일", y="댓글수", color_discrete_sequence=["#FF0000"])
            fig3.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig3, use_container_width=True)

        with col_d:
            st.markdown("#### 🏆 활발한 댓글러 TOP 10")
            top_users = df["작성자"].value_counts().head(10).reset_index()
            top_users.columns = ["작성자", "댓글수"]
            fig4 = px.bar(top_users, x="댓글수", y="작성자", orientation="h",
                          color_discrete_sequence=["#ff6348"])
            fig4.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20), yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig4, use_container_width=True)

        st.markdown("---")
        st.markdown("#### 🏆 좋아요 TOP 10 댓글")
        top10 = df.nlargest(10, "좋아요")[["작성자", "댓글", "좋아요", "작성일"]].reset_index(drop=True)
        top10.index = top10.index + 1
        st.dataframe(top10, use_container_width=True)

    # ── TAB 3: 감성 분석 ──
    with tab3:
        st.markdown("#### 😊 감성 분석 결과")

        sentiment_counts = df["감성"].value_counts().reset_index()
        sentiment_counts.columns = ["감성", "개수"]

        col_e, col_f = st.columns(2)

        with col_e:
            fig5 = px.pie(
                sentiment_counts, names="감성", values="개수",
                color="감성",
                color_discrete_map={
                    "긍정 😊": "#00b894",
                    "부정 😠": "#d63031",
                    "중립 😐": "#b2bec3"
                }
            )
            fig5.update_layout(height=350)
            st.plotly_chart(fig5, use_container_width=True)

        with col_f:
            for _, row in sentiment_counts.iterrows():
                pct = row["개수"] / len(df) * 100
                st.write(f"**{row['감성']}**: {row['개수']}개 ({pct:.1f}%)")
            st.markdown("---")
            st.markdown("**감성별 평균 좋아요**")
            sentiment_likes = df.groupby("감성")["좋아요"].mean().reset_index()
            sentiment_likes.columns = ["감성", "평균 좋아요"]
            st.dataframe(sentiment_likes, use_container_width=True)

        st.markdown("---")

        st.markdown("#### 감성별 댓글 보기")
        sel = st.selectbox("감성 선택", ["긍정 😊", "부정 😠", "중립 😐"], key="sent_sel")
        sent_df = df[df["감성"] == sel][["작성자", "댓글", "좋아요"]].head(20)
        st.dataframe(sent_df, use_container_width=True)

    # ── TAB 4: 다운로드 ──
    with tab4:
        st.markdown("#### 📥 데이터 다운로드")

        dl1, dl2 = st.columns(2)

        with dl1:
            csv = df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                "📥 CSV 다운로드",
                data=csv,
                file_name=f"comments_{video_id}.csv",
                mime="text/csv",
                use_container_width=True
            )

        with dl2:
            buf = io.BytesIO()
            df.to_excel(buf, index=False, engine="openpyxl")
            buf.seek(0)
            st.download_button(
                "📥 Excel 다운로드",
                data=buf.getvalue(),
                file_name=f"comments_{video_id}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        st.markdown("---")
        st.markdown("#### 📋 전체 데이터 미리보기")
        st.dataframe(df, use_container_width=True, height=400)

st.markdown("---")
st.caption("당곡고등학교 학습용 유튜브 댓글 수집기 | YouTube Data API v3")
