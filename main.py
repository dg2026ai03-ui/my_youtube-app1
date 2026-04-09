import streamlit as st
import pandas as pd
import re
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

# ============================================
# 스타일 적용
# ============================================
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        color: #FF0000;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.1rem;
        text-align: center;
        color: #666;
        margin-bottom: 2rem;
    }
    .comment-box {
        background-color: #f9f9f9;
        border-left: 4px solid #FF0000;
        padding: 15px;
        margin: 10px 0;
        border-radius: 5px;
    }
    .comment-author {
        font-weight: bold;
        color: #333;
        font-size: 0.95rem;
    }
    .comment-text {
        color: #555;
        margin-top: 5px;
        font-size: 0.9rem;
    }
    .comment-meta {
        color: #999;
        font-size: 0.8rem;
        margin-top: 5px;
    }
    .stat-card {
        background: linear-gradient(135deg, #FF0000, #CC0000);
        color: white;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# YouTube API 키 가져오기
# ============================================
def get_api_key():
    """Streamlit secrets 또는 사이드바 입력에서 API 키를 가져옵니다."""
    # 1순위: Streamlit secrets에서 가져오기
    try:
        api_key = st.secrets["YOUTUBE_API_KEY"]
        if api_key:
            return api_key
    except (KeyError, FileNotFoundError):
        pass

    # 2순위: 사이드바에서 직접 입력
    st.sidebar.markdown("### 🔑 API 키 설정")
    st.sidebar.markdown(
        "YouTube Data API v3 키를 입력하세요.\n\n"
        "[API 키 발급 방법 안내](https://console.cloud.google.com/apis/library/youtube.googleapis.com)"
    )
    api_key = st.sidebar.text_input(
        "YouTube API Key",
        type="password",
        placeholder="AIza..."
    )
    return api_key


# ============================================
# 유튜브 비디오 ID 추출
# ============================================
def extract_video_id(url):
    """다양한 유튜브 URL 형식에서 비디오 ID를 추출합니다."""
    patterns = [
        # 표준 URL: https://www.youtube.com/watch?v=VIDEO_ID
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
        # 짧은 URL: https://youtu.be/VIDEO_ID
        r'(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})',
        # 임베드 URL: https://www.youtube.com/embed/VIDEO_ID
        r'(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        # Shorts URL: https://www.youtube.com/shorts/VIDEO_ID
        r'(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})',
        # 비디오 ID만 입력한 경우
        r'^([a-zA-Z0-9_-]{11})$',
    ]

    for pattern in patterns:
        match = re.search(pattern, url.strip())
        if match:
            return match.group(1)
    return None


# ============================================
# 비디오 정보 가져오기
# ============================================
def get_video_info(youtube, video_id):
    """비디오의 기본 정보를 가져옵니다."""
    try:
        request = youtube.videos().list(
            part="snippet,statistics",
            id=video_id
        )
        response = request.execute()

        if response["items"]:
            item = response["items"][0]
            snippet = item["snippet"]
            stats = item["statistics"]

            return {
                "title": snippet.get("title", "제목 없음"),
                "channel": snippet.get("channelTitle", "채널명 없음"),
                "published": snippet.get("publishedAt", "")[:10],
                "description": snippet.get("description", "")[:300],
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "comment_count": int(stats.get("commentCount", 0)),
            }
        return None
    except HttpError as e:
        st.error(f"비디오 정보를 가져오는 중 오류 발생: {e}")
        return None


# ============================================
# 댓글 가져오기
# ============================================
def get_comments(youtube, video_id, max_comments=100, order="relevance"):
    """유튜브 비디오의 댓글을 가져옵니다."""
    comments = []
    next_page_token = None

    try:
        while len(comments) < max_comments:
            request = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=min(100, max_comments - len(comments)),
                order=order,
                pageToken=next_page_token,
                textFormat="plainText"
            )
            response = request.execute()

            for item in response.get("items", []):
                snippet = item["snippet"]["topLevelComment"]["snippet"]
                comment_data = {
                    "작성자": snippet.get("authorDisplayName", "익명"),
                    "댓글": snippet.get("textDisplay", ""),
                    "좋아요": snippet.get("likeCount", 0),
                    "작성일": snippet.get("publishedAt", "")[:10],
                    "수정일": snippet.get("updatedAt", "")[:10],
                    "답글수": item["snippet"].get("totalReplyCount", 0),
                }
                comments.append(comment_data)

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        return comments

    except HttpError as e:
        error_reason = e.error_details[0]["reason"] if e.error_details else "unknown"
        if error_reason == "commentsDisabled":
            st.warning("⚠️ 이 동영상은 댓글이 비활성화되어 있습니다.")
        elif error_reason == "forbidden":
            st.error("🚫 API 키에 YouTube Data API v3 접근 권한이 없습니다.")
        else:
            st.error(f"❌ 댓글을 가져오는 중 오류 발생: {e}")
        return []


# ============================================
# 메인 앱
# ============================================
def main():
    # 헤더
    st.markdown('<div class="main-header">🎬 유튜브 댓글 수집기</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">유튜브 영상 링크를 입력하면 댓글을 수집하고 분석합니다</div>', unsafe_allow_html=True)

    # API 키 가져오기
    api_key = get_api_key()

    if not api_key:
        st.info(
            "👈 사이드바에서 YouTube Data API v3 키를 입력해주세요.\n\n"
            "**API 키 발급 방법:**\n"
            "1. [Google Cloud Console](https://console.cloud.google.com/) 접속\n"
            "2. 새 프로젝트 생성\n"
            "3. 'YouTube Data API v3' 검색 후 사용 설정\n"
            "4. 사용자 인증 정보 → API 키 만들기"
        )
        return

    # YouTube API 클라이언트 생성
    try:
        youtube = build("youtube", "v3", developerKey=api_key)
    except Exception as e:
        st.error(f"YouTube API 연결 실패: {e}")
        return

    # ── 입력 영역 ──
    st.markdown("---")
    col_input, col_btn = st.columns([4, 1])

    with col_input:
        url = st.text_input(
            "🔗 유튜브 링크 입력",
            placeholder="https://www.youtube.com/watch?v=... 또는 https://youtu.be/...",
            label_visibility="collapsed"
        )

    # ── 사이드바 옵션 ──
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚙️ 수집 옵션")

    max_comments = st.sidebar.slider(
        "최대 댓글 수",
        min_value=10,
        max_value=500,
        value=100,
        step=10,
        help="한 번에 가져올 최대 댓글 수를 설정합니다."
    )

    order = st.sidebar.radio(
        "정렬 기준",
        options=["relevance", "time"],
        format_func=lambda x: "인기순 🔥" if x == "relevance" else "최신순 🕐",
        help="댓글 정렬 방식을 선택합니다."
    )

    with col_btn:
        search_clicked = st.button("🔍 댓글 수집", use_container_width=True, type="primary")

    # ── 댓글 수집 실행 ──
    if search_clicked and url:
        video_id = extract_video_id(url)

        if not video_id:
            st.error("❌ 올바른 유튜브 URL을 입력해주세요.")
            return

        # 비디오 정보 가져오기
        with st.spinner("📺 영상 정보를 불러오는 중..."):
            video_info = get_video_info(youtube, video_id)

        if video_info:
            # 비디오 정보 표시
            st.markdown("---")
            col_thumb, col_info = st.columns([1, 2])

            with col_thumb:
                if video_info["thumbnail"]:
                    st.image(video_info["thumbnail"], use_container_width=True)

            with col_info:
                st.markdown(f"### 📺 {video_info['title']}")
                st.markdown(f"**채널:** {video_info['channel']}")
                st.markdown(f"**업로드일:** {video_info['published']}")

                # 통계
                stat_col1, stat_col2, stat_col3 = st.columns(3)
                with stat_col1:
                    st.metric("👁️ 조회수", f"{video_info['view_count']:,}")
                with stat_col2:
                    st.metric("👍 좋아요", f"{video_info['like_count']:,}")
                with stat_col3:
                    st.metric("💬 댓글수", f"{video_info['comment_count']:,}")

        # 댓글 가져오기
        with st.spinner(f"💬 댓글을 수집하는 중... (최대 {max_comments}개)"):
            comments = get_comments(youtube, video_id, max_comments, order)

        if comments:
            df = pd.DataFrame(comments)

            st.markdown("---")
            st.markdown(f"### 💬 수집된 댓글 ({len(comments)}개)")

            # ── 탭으로 보기 방식 선택 ──
            tab1, tab2 = st.tabs(["📋 카드 보기", "📊 테이블 보기"])

            # 카드 보기
            with tab1:
                # 검색 필터
                search_term = st.text_input("🔍 댓글 내 검색", placeholder="키워드를 입력하세요...")

                filtered_df = df.copy()
                if search_term:
                    filtered_df = filtered_df[
                        filtered_df["댓글"].str.contains(search_term, case=False, na=False)
                    ]
                    st.info(f"'{search_term}' 검색 결과: {len(filtered_df)}개")

                # 댓글 카드 표시
                for idx, row in filtered_df.iterrows():
                    st.markdown(f"""
                    <div class="comment-box">
                        <div class="comment-author">👤 {row['작성자']}</div>
                        <div class="comment-text">{row['댓글']}</div>
                        <div class="comment-meta">
                            👍 {row['좋아요']} &nbsp;&nbsp;|&nbsp;&nbsp;
                            💬 답글 {row['답글수']}개 &nbsp;&nbsp;|&nbsp;&nbsp;
                            📅 {row['작성일']}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

            # 테이블 보기
            with tab2:
                st.dataframe(
                    df,
                    use_container_width=True,
                    height=500,
                    column_config={
                        "좋아요": st.column_config.NumberColumn("👍 좋아요", format="%d"),
                        "답글수": st.column_config.NumberColumn("💬 답글", format="%d"),
                    }
                )

            # ── 다운로드 버튼 ──
            st.markdown("---")
            col_dl1, col_dl2, col_dl3 = st.columns([1, 1, 2])

            with col_dl1:
                csv_data = df.to_csv(index=False, encoding="utf-8-sig")
                st.download_button(
                    label="📥 CSV 다운로드",
                    data=csv_data,
                    file_name=f"youtube_comments_{video_id}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

            with col_dl2:
                # Excel 다운로드 (선택적)
                try:
                    import io
                    buffer = io.BytesIO()
                    df.to_excel(buffer, index=False, engine="openpyxl")
                    st.download_button(
                        label="📥 Excel 다운로드",
                        data=buffer.getvalue(),
                        file_name=f"youtube_comments_{video_id}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet",
                        use_container_width=True
                    )
                except ImportError:
                    st.info("Excel 다운로드를 위해 openpyxl 패키지가 필요합니다.")

            # ── 간단한 통계 ──
            st.markdown("---")
            st.markdown("### 📊 간단한 댓글 통계")

            stat1, stat2, stat3, stat4 = st.columns(4)
            with stat1:
                st.metric("총 댓글 수", f"{len(df)}개")
            with stat2:
                avg_likes = df["좋아요"].mean()
                st.metric("평균 좋아요", f"{avg_likes:.1f}")
            with stat3:
                max_likes = df["좋아요"].max()
                st.metric("최다 좋아요", f"{max_likes}")
            with stat4:
                avg_length = df["댓글"].str.len().mean()
                st.metric("평균 글자수", f"{avg_length:.0f}자")

            # 좋아요 TOP 5
            st.markdown("#### 🏆 좋아요 TOP 5 댓글")
            top5 = df.nlargest(5, "좋아요")[["작성자", "댓글", "좋아요"]].reset_index(drop=True)
            top5.index = top5.index + 1
            st.dataframe(top5, use_container_width=True)

        elif url:
            st.warning("수집된 댓글이 없습니다.")

    elif search_clicked and not url:
        st.warning("⚠️ 유튜브 링크를 입력해주세요.")

    # ── 푸터 ──
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #999; font-size: 0.85rem;'>"
        "당곡고등학교 학습용 유튜브 댓글 수집기 | YouTube Data API v3 활용"
        "</div>",
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
