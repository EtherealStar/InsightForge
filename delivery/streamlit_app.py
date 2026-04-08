"""
Streamlit UI — 独立进程
启动方式：streamlit run delivery/streamlit_app.py
数据通过 SQLite 文件与 scheduler 进程共享
"""
import os
import sys
import glob
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path so that `core`, `services`, etc. are importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from core.config import AppConfig
from core.factory import (
    create_article_store,
    create_vector_store,
    create_llm_client,
    create_embedding_client,
)
from services.query_service import QueryService
from services.brief_service import BriefService


# ─────────────────── 页面配置 ───────────────────
st.set_page_config(
    page_title="Logos — AI 新闻分析助手",
    page_icon="📰",
    layout="wide",
)


# ─────────────────── 初始化 ───────────────────
@st.cache_resource
def init_services():
    """初始化所有服务（缓存单例）"""
    config = AppConfig()
    article_store = create_article_store(config)
    vector_store = create_vector_store(config)
    llm_client = create_llm_client(config)
    embedding_client = create_embedding_client(config)

    query_service = QueryService(
        article_store, vector_store, llm_client, embedding_client
    )
    brief_service = BriefService(
        article_store, llm_client, config.output_path
    )
    return config, article_store, query_service, brief_service


config, article_store, query_service, brief_service = init_services()


# ─────────────────── 侧边栏 ───────────────────
with st.sidebar:
    st.title("📰 Logos")
    st.caption("个人 AI 新闻分析助手")
    st.divider()

    # 数据库统计
    st.subheader("📊 数据概览")
    try:
        stats = article_store.get_stats()
        col1, col2 = st.columns(2)
        col1.metric("文章总数", stats["total"])
        col2.metric("已向量化", stats["embedded"])
        col1.metric("今日新增", stats["today_new"])
        col2.metric("来源数", len(stats["sources"]))
        if stats["sources"]:
            st.caption(f"来源: {', '.join(stats['sources'][:5])}")
    except Exception as e:
        st.warning(f"获取统计失败: {e}")

    st.divider()

    # LLM 配置显示
    st.subheader("⚙️ 系统状态")
    st.text(f"LLM: {config.llm_provider}")
    st.text(f"模型: {config.llm_model or '未配置'}")

    # 来源筛选器
    st.divider()
    st.subheader("🔍 筛选")
    try:
        all_sources = stats.get("sources", [])
    except Exception:
        all_sources = []
    selected_sources = st.multiselect(
        "来源筛选",
        options=all_sources,
        default=all_sources,
        key="source_filter",
    )

    # 语言筛选
    selected_language = st.selectbox(
        "语言筛选",
        options=["全部", "中文", "英文"],
        index=0,
        key="language_filter",
    )


# ─────────────────── 主内容区 ───────────────────
tab_chat, tab_brief = st.tabs(["💬 对话查询", "📋 今日简报"])

# ═══════════════════ Tab 1: 对话查询 ═══════════════════
with tab_chat:
    st.header("💬 新闻智能问答")
    st.caption("基于已收录的新闻库进行 RAG 检索增强回答")

    # 对话历史
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 显示历史消息
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # 用户输入
    if prompt := st.chat_input("请输入你的问题，例如：今天有什么重要新闻？"):
        # 显示用户消息
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 助手回答（streaming）
        with st.chat_message("assistant"):
            try:
                response = st.write_stream(
                    query_service.answer_stream(prompt)
                )
                st.session_state.messages.append(
                    {"role": "assistant", "content": response}
                )
            except Exception as e:
                error_msg = f"❌ 回答生成失败: {e}"
                st.error(error_msg)
                st.session_state.messages.append(
                    {"role": "assistant", "content": error_msg}
                )

# ═══════════════════ Tab 2: 今日简报 ═══════════════════
with tab_brief:
    st.header("📋 每日新闻简报")

    col_btn1, col_btn2 = st.columns([1, 5])
    with col_btn1:
        refresh = st.button("🔄 立即生成", key="refresh_brief")

    if refresh:
        with st.spinner("正在生成日报..."):
            try:
                brief = brief_service.generate(hours=24)
                st.success(
                    f"✅ 日报已生成 — {brief.article_count} 篇文章, "
                    f"{brief.generated_at.strftime('%H:%M:%S')}"
                )
            except Exception as e:
                st.error(f"❌ 日报生成失败: {e}")

    # 读取最新日报文件
    brief_files = sorted(
        glob.glob(os.path.join(config.output_path, "daily_brief_*.md")),
        reverse=True,
    )

    if brief_files:
        latest_file = brief_files[0]
        mod_time = datetime.fromtimestamp(
            os.path.getmtime(latest_file)
        ).strftime("%Y-%m-%d %H:%M:%S")
        st.caption(f"📄 最新日报: {os.path.basename(latest_file)} | 生成时间: {mod_time}")
        st.divider()

        with open(latest_file, "r", encoding="utf-8") as f:
            st.markdown(f.read())
    else:
        st.info("📭 尚无日报。点击「立即生成」按钮生成第一份日报。")
