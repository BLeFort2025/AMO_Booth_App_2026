"""
🤖 AI Research Assistant — page 14.

Chat-based natural language interface to query all 150+ datasets
in the dashboard. Powered by Google Gemini 2.5 Flash (free tier).
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
import pandas as pd

# ── path fix ──
_PROJECT = Path(__file__).resolve().parents[2]  # app/pages/ -> app/ -> project root
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

from app.ai_engine import (
    DataRegistry, GeminiAgent, SafeExecutor, RateLimiter, GeminiAPIError,
)

# ────────────────────────────────────────────────────────
#  Page config
# ────────────────────────────────────────────────────────
st.set_page_config(page_title="AI Research Assistant", page_icon="🤖", layout="wide")

from app.utils import inject_standalone_mode, show_data_freshness
inject_standalone_mode()
show_data_freshness()


# ────────────────────────────────────────────────────────
#  Starter questions
# ────────────────────────────────────────────────────────
STARTER_QUESTIONS = [
    "Which municipality has the highest farm tax rate?",
    "Which county has the most respondents who are 'Not at all confident' in the confidence survey?",
    "What is the average broadband download speed across Ontario counties?",
    "Compare Oxford and Wellington across all available census indicators",
    "Show the top 10 commodities by total farm receipts in the latest year",
    "What percentage of farmers under 35 plan to expand their operations?",
    "Which counties have both poor broadband and low farm confidence?",
    "Create a summary table of farm financial health indicators by municipality",
    "What are the most common insurance types among OFA members?",
    "Show population trends for the top 5 most populated rural census divisions",
]


@st.cache_resource(ttl=3600)
def get_registry():
    """Load and cache the data registry (scans all CSVs once)."""
    return DataRegistry()


def _get_api_key() -> str | None:
    """Try to get the Gemini API key from various sources."""
    # 1. Streamlit secrets (for cloud deployment)
    try:
        return st.secrets["GEMINI_API_KEY"]
    except (KeyError, FileNotFoundError):
        pass

    # 2. Environment variable
    import os
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key

    # 3. .env file in project root
    env_file = _PROJECT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.strip().startswith("GEMINI_API_KEY"):
                _, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                if val:
                    return val

    return None


def _show_setup_instructions():
    """Display setup instructions when no API key is found."""
    st.warning("🔑 **Gemini API key not configured** — Follow the steps below to get started.")

    st.markdown("""
    ### Setup Instructions (5 minutes, completely free)

    **Step 1: Get a free API key**
    1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
    2. Click **"Create API Key"**
    3. Select or create a Google Cloud project (free, no billing required)
    4. Copy the generated API key

    > **⚠️ Important:** This is Google AI Studio, which is **completely separate** from your
    > Gemini consumer subscription. No credit card is required, and you will **never be charged**.

    **Step 2: Add the key to the dashboard**

    Create a file called `.env` in the project root directory with:
    ```
    GEMINI_API_KEY=your_api_key_here
    ```

    **Or** set an environment variable:
    ```powershell
    $env:GEMINI_API_KEY = "your_api_key_here"
    ```

    **Step 3: Restart the Streamlit app**

    ---

    ### Free Tier Limits
    | Limit | Value |
    |-------|-------|
    | Requests per minute | 15 |
    | Requests per day | ~1,500 |
    | Cost | **$0 (free)** |

    The dashboard also enforces a **50 queries/day** hard cap as an extra safety measure.
    """)


def _render_results(execution_result: dict):
    """Display the results of code execution."""
    import hashlib
    error = execution_result.get("error")
    result = execution_result.get("result")
    chart = execution_result.get("chart")
    dfs = execution_result.get("dataframes", {})
    code = execution_result.get("code", "")

    # Unique key suffix to avoid duplicate widget IDs across chat messages
    _uid = hashlib.md5(code.encode()).hexdigest()[:8]

    if error:
        st.error(f"⚠️ The analysis encountered an error:\n```\n{error}\n```")
        with st.expander("🔍 View generated code", expanded=False):
            st.code(code, language="python")
        return

    # Show the chart first (if any)
    if chart is not None:
        try:
            st.altair_chart(chart, use_container_width=True)
            # Download buttons for charts
            col_png, col_html, _ = st.columns([1, 1, 4])
            with col_png:
                try:
                    import vlconvert as vlc
                    png_bytes = vlc.vegalite_to_png(chart.to_dict(), scale=2)
                    st.download_button(
                        "📥 Download PNG", png_bytes,
                        file_name="ai_chart.png", mime="image/png",
                        key=f"dl_png_{_uid}",
                    )
                except Exception:
                    pass  # vlconvert not installed — skip PNG
            with col_html:
                html_str = chart.to_html()
                st.download_button(
                    "📥 Download HTML", html_str.encode("utf-8"),
                    file_name="ai_chart.html", mime="text/html",
                    key=f"dl_html_{_uid}",
                )
        except Exception as e:
            st.warning(f"Chart rendering failed: {e}")

    # Show the result
    if result is not None:
        if isinstance(result, pd.DataFrame):
            st.dataframe(result, use_container_width=True, hide_index=True)
            csv = result.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Download as CSV", csv,
                             file_name="ai_research_result.csv", mime="text/csv",
                             key=f"dl_{_uid}")
        elif isinstance(result, dict):
            # Support {"text": "...", "df": DataFrame} format
            if "text" in result:
                st.markdown(str(result["text"]))
            if "df" in result and isinstance(result["df"], pd.DataFrame):
                st.dataframe(result["df"], use_container_width=True, hide_index=True)
                csv = result["df"].to_csv(index=False).encode("utf-8")
                st.download_button("📥 Download as CSV", csv,
                                 file_name="ai_research_result.csv", mime="text/csv",
                                 key=f"dl_dict_{_uid}")
        else:
            st.markdown(str(result))
    elif dfs:
        # Show any DataFrames that were created
        for name, df in list(dfs.items())[:3]:
            if name == "RESULT":
                continue
            st.markdown(f"**{name}**")
            st.dataframe(df.head(100), use_container_width=True, hide_index=True)
    elif chart is None:
        st.info("The analysis completed but produced no displayable result. "
                "Try rephrasing your question.")

    # Show the code
    with st.expander("🔍 View generated code", expanded=False):
        st.code(code, language="python")


# ────────────────────────────────────────────────────────
#  MAIN
# ────────────────────────────────────────────────────────
def main():
    st.title("🤖 AI Research Assistant")
    st.markdown(
        "Ask questions about **any dataset** in the dashboard using natural language. "
        "The AI generates analysis code that runs against your real data — "
        "**no hallucinated numbers, ever.**"
    )

    # Always load registry so sidebar shows dataset counts
    registry = get_registry()

    # ── Sidebar: dataset overview & starter questions (always visible) ──
    with st.sidebar:
        st.markdown("### 📊 Data Available")
        st.markdown(registry.summary)
        st.divider()

        st.markdown("### 📂 Dataset Catalog")
        by_cat: dict[str, list[str]] = {}
        for name, info in registry.datasets.items():
            by_cat.setdefault(info.category, []).append(name)
        for cat in sorted(by_cat):
            with st.expander(f"{cat} ({len(by_cat[cat])})", expanded=False):
                for n in sorted(by_cat[cat]):
                    st.caption(n)
        st.divider()

    api_key = _get_api_key()

    if not api_key:
        _show_setup_instructions()
        return

    # Initialize AI components (only when key is present)
    agent = GeminiAgent(api_key, registry)
    executor = SafeExecutor(registry)
    limiter = RateLimiter()

    # ── Sidebar: rate limit & starter questions ──
    with st.sidebar:
        allowed, remaining = limiter.check(st.session_state)
        st.metric("Queries Remaining Today", f"{remaining}")
        if remaining <= 5:
            st.warning(f"⚠️ Only {remaining} queries left today.")
        st.caption("Quota resets at 3:00 AM ET (midnight PT)")
        st.divider()

        st.markdown("### 💡 Try asking...")
        for i, q in enumerate(STARTER_QUESTIONS[:6]):
            if st.button(q, key=f"starter_{i}", use_container_width=True):
                st.session_state["_ai_pending_question"] = q
                st.rerun()

    # ── Initialize chat history ──
    if "_ai_messages" not in st.session_state:
        st.session_state["_ai_messages"] = []
    if "_ai_cache" not in st.session_state:
        st.session_state["_ai_cache"] = {}

    # ── Display conversation history ──
    for msg in st.session_state["_ai_messages"]:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                if "execution_result" in msg:
                    _render_results(msg["execution_result"])
                else:
                    st.markdown(msg["content"])
            else:
                st.markdown(msg["content"])

    # ── Handle pending starter question ──
    pending = st.session_state.pop("_ai_pending_question", None)

    # ── Chat input ──
    user_input = st.chat_input("Ask a question about the data...")

    question = pending or user_input

    if question:
        # Rate limit check
        allowed, remaining = limiter.check(st.session_state)
        if not allowed:
            st.error("🚫 Daily query limit reached. Try again tomorrow.")
            return

        # Add user message
        st.session_state["_ai_messages"].append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        # Generate and execute
        with st.chat_message("assistant"):
            with st.spinner("🧠 Analyzing your question..."):
                try:
                    # Check response cache first
                    import hashlib as _hl
                    cache_key = _hl.md5(question.strip().lower().encode()).hexdigest()
                    cached = st.session_state["_ai_cache"].get(cache_key)

                    if cached:
                        result = cached
                        st.info("📋 Returning cached result (no API call used)")
                    else:
                        # Build conversation context for multi-turn
                        conv_context = [
                            {"role": m["role"], "content": m["content"]}
                            for m in st.session_state["_ai_messages"][-6:]
                            if "content" in m
                        ]

                        code = agent.ask(question, conv_context)
                        result = executor.execute(code)

                    # ── Auto-retry on runtime errors (Fix #6) ──
                    if result.get("error") and not result.get("result"):
                        try:
                            with st.spinner("🔄 Adjusting approach..."):
                                fixed_code = agent.ask_fix(
                                    code, result["error"], conv_context
                                )
                                result = executor.execute(fixed_code)
                                limiter.increment(st.session_state)
                        except Exception:
                            pass  # keep original error result

                    # Cache successful results
                    if not result.get("error"):
                        st.session_state["_ai_cache"][cache_key] = result

                    _render_results(result)

                    # Save to history
                    st.session_state["_ai_messages"].append({
                        "role": "assistant",
                        "content": "Analysis complete.",
                        "execution_result": result,
                    })

                    # Increment rate limiter
                    limiter.increment(st.session_state)

                except GeminiAPIError as e:
                    # User-friendly message for transient API errors
                    friendly = str(e)
                    st.warning(f"⏳ {friendly}")
                    st.session_state["_ai_messages"].append({
                        "role": "assistant",
                        "content": friendly,
                    })

                except Exception as e:
                    # Parse common API error codes for friendlier messages
                    err_str = str(e)
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        friendly = ("⚠️ API rate limit reached. The free tier allows "
                                    "~250 requests per day and 15 per minute. "
                                    "Please wait a moment and try again.")
                    elif "503" in err_str or "UNAVAILABLE" in err_str:
                        friendly = ("⚠️ The AI service is temporarily busy. "
                                    "Please try again in a moment.")
                    else:
                        friendly = f"⚠️ Error communicating with Gemini: {err_str}"

                    st.error(friendly)
                    st.session_state["_ai_messages"].append({
                        "role": "assistant",
                        "content": friendly,
                    })


main()

from app.utils import global_footer
global_footer()
