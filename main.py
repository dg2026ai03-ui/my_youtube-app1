import streamlit as st
import pandas as pd
import re
import io
import time
from collections import Counter
from datetime import datetime

import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import matplotlib.pyplot as plt
from wordcloud import WordCloud
import matplotlib.font_manager as fm

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ============================================
# 페이지 설정
# ============================================
st.set_page_config(
    page_title="유튜브 댓글 분석기 Pro",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# 세션 스테이트 초기화
# ============================================
if "bookmarked" not in st.session_state:
    st.session_state.bookmarked = set()
if "all_results" not in st.session_state:
    st.session_state.all_results = {}
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False

# ============================================
# 다크모드 스타일
# ============================================
def apply_theme():
    if st.session_state.dark_mode:
        st.markdown("""
        <style>
            .stApp { background-color: #1a1a2e; color: #e0e0e0; }
            .comment-box {
                background-color: #16213e;
                border-left: 4px solid #e94560;
                padding: 15px; margin: 10px 0; border-radius: 8px;
                color: #e0e0e0;
            }
            .comment-author { font-weight: bold; color: #e94560; }
            .comment-text { color: #c0c0c0; margin-top: 8px; line-height: 1.6; }
            .comment-meta { color: #888; font-size: 0.8rem; margin-top: 8px; }
            .stat-card {
                background: linear-gradient(135deg, #e94560, #0f3460);
                padding: 20px; border-radius: 12px; text-align: center; color: white;
            }
            .pos-tag { background-color: #00b894; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.75rem; }
            .neg-tag { background-color: #e94560; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.75rem; }
            .neu-tag { background-color: #636e72; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.75rem; }
            .header-gradient {
                background: linear-gradient(90deg, #e94560, #0f3460);
                -webkit-background-clip: text; -webkit-text-fill-color: transparent;
                font-size: 2.5rem; font-weight: 800; text-align: center; margin-bottom: 5px;
            }
        </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <style>
            .comment-box {
                background-color: #fafafa;
                border-left: 4px solid #FF0000;
                padding: 15px; margin: 10px 0; border-radius: 8px;
            }
            .comment-author { font-weight: bold; color: #333; }
            .comment-text { color: #555; margin-top: 8px; line-height: 1.6; }
            .comment-meta { color: #999; font-size: 0.8rem; margin-top: 8px; }
            .stat-card {
                background: linear-gradient(135deg, #FF0000, #CC0000);
                padding: 20px; border-radius: 12px; text-align: center; color: white;
            }
            .pos-tag { background-color: #00b894; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.75rem; }
            .neg-tag { background-color: #d63031; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.75rem; }
            .neu-tag { background-color: #b2bec3; color: #333; padding: 2px 8px; border-radius: 10px; font-size: 0.75rem; }
            .header-gradient {
                background: linear-gradient(90deg, #FF0000, #ff6348);
                -webkit-background-clip: text; -webkit-text-fill-color: transparent;
                font-size: 2.5rem; font-weight: 800; text-align: center; margin-bottom: 5px;
            }
        </style>
        """, unsafe_allow_html=True)

apply_theme()


# ============================================
# 유틸리티 함수들
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


def get_video_info(youtube, video_id):
    try:
        response = youtube.videos().list(
            part="snippet,statistics", id=video_id
        ).execute()

        if response.get("items"):
            item = response["items"][0]
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            thumbs = snippet.get("thumbnails", {})
            thumb_url = ""
            for key in ["high", "medium", "default"]:
                if key in thumbs:
                    thumb_url = thumbs[key].get("url", "")
                    break
            return {
                "title": snippet.get("title", "제목 없음"),
                "channel": snippet.get("channelTitle", "채널명 없음"),
                "published": snippet.get("publishedAt", "")[:10],
                "thumbnail": thumb_url,
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "comment_count": int(stats.get("commentCount", 0)),
            }
        return None
    except HttpError:
        return None


def get_comments(youtube, video_id, max_comments, order, include_replies=False, progress_bar=None):
    comments = []
    next_page_token = None
    page_count = 0

    try:
        while len(comments) < max_comments:
            response = youtube.commentThreads().list(
                part="snippet,replies" if include_replies else "snippet",
                videoId=video_id,
                maxResults=min(100, max_comments - len(comments)),
                order=order,
                pageToken=next_page_token,
                textFormat="plainText"
            ).execute()

            for item in response.get("items", []):
                top = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                comment_data = {
                    "작성자": top.get("authorDisplayName", "익명"),
                    "댓글": top.get("textDisplay", ""),
                    "좋아요": int(top.get("likeCount", 0)),
                    "작성일": top.get("publishedAt", "")[:10],
                    "작성시간": top.get("publishedAt", ""),
                    "답글수": int(item.get("snippet", {}).get("totalReplyCount", 0)),
                    "유형": "댓글",
                }
                comments.append(comment_data)

                # 답글 수집
                if include_replies and "replies" in item:
                    for reply_item in item["replies"].get("comments", []):
                        r_snippet = reply_item.get("snippet", {})
                        reply_data = {
                            "작성자": r_snippet.get("authorDisplayName", "익명"),
                            "댓글": r_snippet.get("textDisplay", ""),
                            "좋아요": int(r_snippet.get("likeCount", 0)),
                            "작성일": r_snippet.get("publishedAt", "")[:10],
                            "작성시간": r_snippet.get("publishedAt", ""),
                            "답글수": 0,
                            "유형": "↳ 답글",
                        }
                        comments.append(reply_data)

            page_count += 1
            if progress_bar:
                progress = min(len(comments) / max_comments, 1.0)
                progress_bar.progress(progress, text=f"수집 중... {len(comments)}개 완료")

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        return comments

    except HttpError as e:
        error_msg = str(e)
        if "commentsDisabled" in error_msg:
            st.warning("⚠️ 댓글이 비활성화된 영상입니다.")
        elif "forbidden" in error_msg:
            st.error("🚫 API 키 권한을 확인해주세요.")
        else:
            st.error(f"❌ 오류: {error_msg}")
        return []


# ============================================
# 감성 분석 (키워드 기반)
# ============================================
def analyze_sentiment(text):
    positive_words = [
        "좋아", "최고", "대박", "감동", "멋지", "훌륭", "사랑", "행복",
        "추천", "완벽", "굿", "짱", "잘했", "응원", "화이팅", "기대",
        "재밌", "재미있", "웃기", "힐링", "감사", "고마", "좋은",
        "예쁘", "멋있", "놀라", "신기", "amazing", "good", "great",
        "best", "love", "nice", "cool", "awesome", "fantastic",
        "beautiful", "perfect", "wonderful", "excellent", "brilliant",
        "ㅋㅋ", "ㅎㅎ", "👍", "❤️", "♥", "😍", "🔥", "👏",
        "존경", "리스펙", "respect", "인정", "레전드", "legend",
    ]
    negative_words = [
        "싫어", "별로", "최악", "실망", "짜증", "화나", "슬프",
        "지루", "노잼", "구독취소", "안봐", "쓰레기", "거짓",
        "나쁘", "못생", "역겹", "혐오", "bad", "worst", "hate",
        "terrible", "awful", "boring", "ugly", "stupid",
        "ㅡㅡ", "ㅠㅠ", "ㅜㅜ", "😡", "😤", "👎", "💢",
        "광고", "사기", "거짓말", "실망", "후회",
    ]

    text_lower = text.lower()
    pos_count = sum(1 for w in positive_words if w in text_lower)
    neg_count = sum(1 for w in negative_words if w in text_lower)

    if pos_count > neg_count:
        return "긍정 😊"
    elif neg_count > pos_count:
        return "부정 😠"
    else:
        return "중립 😐"


# ============================================
# 워드클라우드 생성
# ============================================
def generate_wordcloud(texts):
    combined = " ".join(texts)

    # 불용어 (의미 없는 단어 제거)
    stopwords = {
        "이", "그", "저", "것", "수", "등", "들", "및", "에", "를", "의",
        "가", "은", "는", "로", "으로", "에서", "와", "과", "도", "를",
        "을", "다", "하다", "있다", "되다", "이다", "않다", "한", "할",
        "하는", "합니다", "있는", "되는", "없는", "않는", "거", "좀",
        "너무", "진짜", "정말", "되게", "약간", "그냥", "근데", "하고",
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "shall", "can",
        "this", "that", "these", "those", "i", "you", "he", "she",
        "it", "we", "they", "me", "him", "her", "us", "them",
        "my", "your", "his", "its", "our", "their", "and", "but",
        "or", "not", "no", "so", "if", "of", "in", "to", "for",
        "with", "on", "at", "from", "by", "about", "as", "into",
        "ㅋㅋ", "ㅋㅋㅋ", "ㅋㅋㅋㅋ", "ㅎㅎ", "ㅎㅎㅎ",
        "ㅠㅠ", "ㅜㅜ", "ㅠ", "ㅜ",
    }

    try:
        # 한글 폰트 경로 시도 (클라우드 환경)
        font_paths = [
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
            "/usr/share/fonts/NanumGothic.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]

        font_path = None
        for fp in font_paths:
            try:
                if fm.FontProperties(fname=fp).get_name():
                    font_path = fp
                    break
            except Exception:
                continue

        wc_params = {
            "width": 800,
            "height": 400,
            "background_color": "#1a1a2e" if st.session_state.dark_mode else "white",
            "colormap": "magma" if st.session_state.dark_mode else "Reds",
            "max_words": 100,
            "stopwords": stopwords,
            "min_font_size": 10,
            "max_font_size": 80,
            "prefer_horizontal": 0.7,
        }

        if font_path:
            wc_params["font_path"] = font_path

        wc = WordCloud(**wc_params).generate(combined)

        fig, ax = plt.subplots(figsize=(12, 5))
        ax.imshow(wc, interpolation="bilinear")
        ax.axis("off")
        fig.patch.set_facecolor("#1a1a2e" if st.session_state.dark_mode else "white")
        plt.tight_layout(pad=0)
        return fig

    except Exception as e:
        st.warning(f"워드클라우드 생성 중 오류: {e}")
        return None


# ============================================
# 메인 앱
# ============================================
def main():
    # 헤더
    st.markdown('<div class="header-gradient">🎬 유튜브 댓글 분석기 Pro</div>', unsafe_allow_html=True)
    st.markdown(
        '<p style="text-align:center;color:#888;margin-bottom:2rem;">'
        '댓글 수집 · 감성 분석 · 워드클라우드 · 트렌드 분석</p>',
        unsafe_allow_html=True
    )

    # ── 사이드바 ──
    st.sidebar.markdown("## 🎬 유튜브 댓글 분석기")

    # 다크모드 토글
    st.sidebar.markdown("### 🌙 테마")
    dark = st.sidebar.toggle("다크 모드", value=st.session_state.dark_mode)
    if dark != st.session_state.dark_mode:
        st.session_state.dark_mode = dark
        st.rerun()

    # API 키
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔑 API 키")
    api_key = ""
    try:
        api_key = st.secrets["YOUTUBE_API_KEY"]
        st.sidebar.success("✅ API 키 연결됨 (secrets)")
    except Exception:
        api_key = st.sidebar.text_input("YouTube API Key", type="password", placeholder="AIza...")

    if not api_key:
        st.info(
            "👈 사이드바에서 YouTube Data API v3 키를 입력해주세요.\n\n"
            "**API 키 발급:**\n"
            "1. [Google Cloud Console](https://console.cloud.google.com/) 접속\n"
            "2. 프로젝트 생성 → YouTube Data API v3 사용 설정\n"
            "3. 사용자 인증 정보 → API 키 만들기"
        )
        st.stop()

    try:
        youtube = build("youtube", "v3", developerKey=api_key)
    except Exception as e:
        st.error(f"API 연결 실패: {e}")
        st.stop()

    # ── 수집 옵션 ──
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚙️ 수집 옵션")
    max_comments = st.sidebar.slider("최대 댓글 수", 10, 1000, 200, 10)
    order = st.sidebar.radio(
        "정렬", ["relevance", "time"],
        format_func=lambda x: "인기순 🔥" if x == "relevance" else "최신순 🕐"
    )
    include_replies = st.sidebar.checkbox("답글(대댓글)도 수집", value=True)

    # ── 모드 선택 ──
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📌 모드 선택")
    mode = st.sidebar.radio(
        "수집 모드",
        ["단일 영상 분석", "여러 영상 비교 (최대 5개)"],
        label_visibility="collapsed"
    )

    # ============================================
    # 단일 영상 분석 모드
    # ============================================
    if mode == "단일 영상 분석":
        st.markdown("---")
        url = st.text_input(
            "🔗 유튜브 링크를 붙여넣으세요",
            placeholder="https://www.youtube.com/watch?v=..."
        )
        search_clicked = st.button("🔍 댓글 수집 & 분석 시작", type="primary", use_container_width=True)

        if search_clicked:
            if not url:
                st.warning("⚠️ 링크를 입력해주세요.")
                st.stop()

            video_id = extract_video_id(url)
            if not video_id:
                st.error("❌ 올바른 유튜브 URL이 아닙니다.")
                st.stop()

            # 영상 정보
            with st.spinner("📺 영상 정보 로딩..."):
                video_info = get_video_info(youtube, video_id)

            if video_info:
                st.markdown("---")
                c1, c2 = st.columns([1, 2])
                with c1:
                    if video_info["thumbnail"]:
                        st.image(video_info["thumbnail"], use_container_width=True)
                with c2:
                    st.subheader(video_info["title"])
                    st.write(f"**채널:** {video_info['channel']} · **업로드:** {video_info['published']}")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("👁️ 조회수", f"{video_info['view_count']:,}")
                    m2.metric("👍 좋아요", f"{video_info['like_count']:,}")
                    m3.metric("💬 댓글수", f"{video_info['comment_count']:,}")

            # 댓글 수집
            st.markdown("---")
            progress_bar = st.progress(0, text="수집 준비 중...")
            comments = get_comments(youtube, video_id, max_comments, order, include_replies, progress_bar)
            progress_bar.empty()

            if not comments:
                st.warning("수집된 댓글이 없습니다.")
                st.stop()

            df = pd.DataFrame(comments)

            # 감성 분석 추가
            with st.spinner("🧠 감성 분석 중..."):
                df["감성"] = df["댓글"].apply(analyze_sentiment)
                df["글자수"] = df["댓글"].str.len()

            st.success(f"✅ 총 {len(df)}개 댓글 수집 완료! (댓글 {len(df[df['유형']=='댓글'])}개 + 답글 {len(df[df['유형']=='↳ 답글'])}개)")

            # 세션에 저장
            st.session_state.all_results[video_id] = {
                "info": video_info,
                "df": df
            }

            # ── 탭 구성 ──
            tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
                "💬 댓글 보기",
                "📊 통계 & 차트",
                "☁️ 워드클라우드",
                "😊 감성 분석",
                "📈 시간 트렌드",
                "🔖 북마크"
            ])

            # ── TAB 1: 댓글 보기 ──
            with tab1:
                st.subheader(f"💬 댓글 ({len(df)}개)")

                # 필터
                fc1, fc2, fc3 = st.columns([2, 1, 1])
                with fc1:
                    search_term = st.text_input("🔍 댓글 검색", placeholder="키워드 입력...", key="tab1_search")
                with fc2:
                    type_filter = st.selectbox("유형", ["전체", "댓글만", "답글만"])
                with fc3:
                    sentiment_filter = st.selectbox("감성", ["전체", "긍정 😊", "부정 😠", "중립 😐"])

                filtered = df.copy()
                if search_term:
                    filtered = filtered[filtered["댓글"].str.contains(search_term, case=False, na=False)]
                if type_filter == "댓글만":
                    filtered = filtered[filtered["유형"] == "댓글"]
                elif type_filter == "답글만":
                    filtered = filtered[filtered["유형"] == "↳ 답글"]
                if sentiment_filter != "전체":
                    filtered = filtered[filtered["감성"] == sentiment_filter]

                st.info(f"필터 결과: {len(filtered)}개")

                # 정렬 옵션
                sort_option = st.selectbox(
                    "정렬",
                    ["기본순", "좋아요 높은순", "좋아요 낮은순", "최신순", "오래된순", "글자수 긴순"],
                    key="sort_tab1"
                )
                sort_map = {
                    "좋아요 높은순": ("좋아요", False),
                    "좋아요 낮은순": ("좋아요", True),
                    "최신순": ("작성일", False),
                    "오래된순": ("작성일", True),
                    "글자수 긴순": ("글자수", False),
                }
                if sort_option in sort_map:
                    col_name, asc = sort_map[sort_option]
                    filtered = filtered.sort_values(col_name, ascending=asc)

                # 페이지네이션
                page_size = 20
                total_pages = max(1, (len(filtered) - 1) // page_size + 1)
                page = st.number_input("페이지", 1, total_pages, 1, key="page_tab1")
                start_idx = (page - 1) * page_size
                page_df = filtered.iloc[start_idx:start_idx + page_size]

                for idx, row in page_df.iterrows():
                    sentiment_class = "pos-tag" if "긍정" in row["감성"] else ("neg-tag" if "부정" in row["감성"] else "neu-tag")
                    type_icon = "💬" if row["유형"] == "댓글" else "↪️"

                    bookmark_key = f"bm_{idx}"
                    col_comment, col_bm = st.columns([20, 1])

                    with col_comment:
                        st.markdown(f"""
<div class="comment-box">
    <div class="comment-author">{type_icon} {row['작성자']}
        <span class="{sentiment_class}">{row['감성']}</span>
    </div>
    <div class="comment-text">{row['댓글']}</div>
    <div class="comment-meta">
        👍 {row['좋아요']} &nbsp;|&nbsp;
        💬 답글 {row['답글수']}개 &nbsp;|&nbsp;
        📅 {row['작성일']} &nbsp;|&nbsp;
        📝 {row['글자수']}자
    </div>
</div>
                        """, unsafe_allow_html=True)

                    with col_bm:
                        if st.button("🔖", key=bookmark_key, help="북마크"):
                            if idx in st.session_state.bookmarked:
                                st.session_state.bookmarked.discard(idx)
                            else:
                                st.session_state.bookmarked.add(idx)

                st.caption(f"페이지 {page} / {total_pages}")

            # ── TAB 2: 통계 & 차트 ──
            with tab2:
                st.subheader("📊 댓글 통계")

                s1, s2, s3, s4, s5 = st.columns(5)
                only_comments = df[df["유형"] == "댓글"]
                s1.metric("댓글 수", f"{len(only_comments)}개")
                s2.metric("답글 수", f"{len(df) - len(only_comments)}개")
                s3.metric("평균 좋아요", f"{df['좋아요'].mean():.1f}")
                s4.metric("최다 좋아요", f"{df['좋아요'].max()}")
                s5.metric("평균 글자수", f"{df['글자수'].mean():.0f}자")

                st.markdown("---")

                # 좋아요 분포
                col_chart1, col_chart2 = st.columns(2)

                with col_chart1:
                    st.markdown("#### 👍 좋아요 분포")
                    fig_likes = px.histogram(
                        df, x="좋아요", nbins=30,
                        color_discrete_sequence=["#e94560" if st.session_state.dark_mode else "#FF0000"],
                        template="plotly_dark" if st.session_state.dark_mode else "plotly_white"
                    )
                    fig_likes.update_layout(height=350, margin=dict(l=20, r=20, t=20, b=20))
                    
