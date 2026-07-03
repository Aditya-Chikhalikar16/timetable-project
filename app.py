"""College Timetable AI Chatbot — Streamlit app."""
import os
from pathlib import Path
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from timetable import TimetableStore
from chatbot import TimetableChatbot, detect_provider

load_dotenv(Path(__file__).parent / ".env")

st.set_page_config(page_title="Timetable Assistant", page_icon="📅", layout="wide")

def get_store():
    store = st.session_state.get("timetable_store")
    if store is None or not hasattr(store, "find_entries"):
        st.session_state.timetable_store = TimetableStore()
    return st.session_state.timetable_store

def apply_ai_settings():
    """Apply sidebar API keys to environment for this session."""
    if st.session_state.get("gemini_key"):
        os.environ["GEMINI_API_KEY"] = st.session_state["gemini_key"]
    if st.session_state.get("openai_key"):
        os.environ["OPENAI_API_KEY"] = st.session_state["openai_key"]
    os.environ["LLM_PROVIDER"] = st.session_state.get("llm_provider", "auto")

def get_bot() -> TimetableChatbot:
    apply_ai_settings()
    provider = st.session_state.get("llm_provider", "auto")
    if provider == "auto":
        resolved = detect_provider()
    else:
        resolved = provider if provider in ("openai", "gemini") else detect_provider()
    return TimetableChatbot(get_store(), provider=resolved)

# Init session defaults from .env
if "gemini_key" not in st.session_state:
    st.session_state.gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
if "openai_key" not in st.session_state:
    st.session_state.openai_key = os.getenv("OPENAI_API_KEY") or ""
if "llm_provider" not in st.session_state:
    st.session_state.llm_provider = os.getenv("LLM_PROVIDER", "auto")

store = get_store()

# --- Sidebar ---
with st.sidebar:
    st.title("📅 Timetable")
    st.caption("Filter & customize your view")

    view_mode = st.radio("View", ["Chat", "Grid", "List", "Edit"], horizontal=True)

    st.divider()
    st.subheader("🤖 AI Settings")
    st.session_state.llm_provider = st.selectbox(
        "Provider",
        ["auto", "gemini", "openai"],
        index=["auto", "gemini", "openai"].index(st.session_state.llm_provider)
        if st.session_state.llm_provider in ("auto", "gemini", "openai") else 0,
        format_func=lambda x: {"auto": "Auto (prefer Gemini)", "gemini": "Google Gemini", "openai": "OpenAI GPT"}[x],
    )
    st.session_state.gemini_key = st.text_input(
        "Gemini API key",
        value=st.session_state.gemini_key,
        type="password",
        help="Free key at aistudio.google.com/apikey",
    )
    st.session_state.openai_key = st.text_input(
        "OpenAI API key",
        value=st.session_state.openai_key,
        type="password",
        help="Key from platform.openai.com",
    )

    bot = get_bot()
    mode = bot.provider_label()
    if bot.provider:
        st.success(f"🟢 {mode}")
    else:
        st.warning(f"🟡 {mode}")

    st.divider()
    st.subheader("Filters")
    sel_division = st.selectbox("Division", ["All"] + store.divisions, index=0)
    sel_day = st.selectbox("Day", ["All"] + store.days, index=0)
    sel_type = st.selectbox("Class type", ["All"] + store.types, index=0)
    search = st.text_input("Search subject / professor / room")

    division_filter = None if sel_division == "All" else sel_division
    day_filter = None if sel_day == "All" else sel_day
    type_filter = None if sel_type == "All" else sel_type

    if st.button("🔄 Reload data"):
        if "timetable_store" in st.session_state:
            del st.session_state.timetable_store
        st.cache_resource.clear()
        st.rerun()

# --- Header ---
st.title("🎓 College Timetable Assistant")
st.markdown("Ask questions in plain English — powered by Gemini or GPT.")

# --- Main content ---
if view_mode == "Chat":
    col_chat, col_preview = st.columns([1.2, 1])

    with col_chat:
        st.subheader("💬 Chat")
        if "messages" not in st.session_state:
            st.session_state.messages = [{
                "role": "assistant",
                "content": (
                    "Hi! I can **query** and **edit** your timetable (works without API key):\n\n"
                    "**Find:** *Find CE2 Friday labs*\n"
                    "**Add:** *Add class AD1 Monday 10:00 am - 11:00 am, subject AP, professor Dr. X, room AC 301*\n"
                    "**Update:** *Update id 93 room to AC 401*\n"
                    "**Delete:** *Delete id 113*\n"
                    "**Replace:** *Replace CE2 BET with AP*"
                ),
            }]

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if prompt := st.chat_input("Ask about your timetable..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            history = [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages[:-1]
                if m["role"] in ("user", "assistant")
            ]
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    try:
                        reply = get_bot().chat(prompt, history)
                    except Exception as exc:
                        reply = (
                            f"Sorry, something went wrong: {exc}\n\n"
                            "Try restarting the app. Gemini now uses REST (no cygrpc DLL needed)."
                        )
                st.markdown(reply)
            st.session_state.messages.append({"role": "assistant", "content": reply})

        if st.button("Clear chat"):
            st.session_state.messages = []
            st.rerun()

    with col_preview:
        st.subheader("📋 Quick view")
        div = division_filter or (store.divisions[0] if store.divisions else None)
        if div:
            st.caption(f"Grid: {div}")
            grid = store.pivot_grid(div)
            st.dataframe(grid.replace("", "—"), use_container_width=True, height=400)
        else:
            st.info("Select a division in the sidebar to see the grid.")

elif view_mode == "Grid":
    st.subheader("📊 Weekly Grid")
    div = division_filter or st.selectbox("Pick division for grid", store.divisions, key="grid_div")
    if div:
        grid = store.pivot_grid(div)
        st.dataframe(grid.replace("", "—"), use_container_width=True, height=500)
        st.caption(f"Showing {div} — {len(store.get_division_schedule(div))} classes")

elif view_mode == "List":
    st.subheader("📃 Class List")
    records = store.query(division=division_filter, day=day_filter, class_type=type_filter, limit=200)
    if search:
        s = search.lower()
        records = [r for r in records if s in str(r).lower()]
    if records:
        st.dataframe(pd.DataFrame(records), use_container_width=True, hide_index=True)
        st.caption(f"{len(records)} classes shown")
    else:
        st.warning("No classes match your filters.")

elif view_mode == "Edit":
    st.subheader("✏️ Edit Timetable")
    st.caption("Add, update, or remove entries. Changes save to the CSV file.")
    tab_add, tab_edit, tab_del = st.tabs(["Add entry", "Edit entry", "Delete entry"])

    with tab_add:
        with st.form("add_form"):
            c1, c2 = st.columns(2)
            professor = c1.text_input("Professor")
            day = c2.selectbox("Day", store.days, key="add_day")
            c3, c4 = st.columns(2)
            time_slot = c3.text_input("Time slot", placeholder="10:00 am - 11:00 am")
            division = c4.selectbox("Division", store.divisions, key="add_div")
            c5, c6 = st.columns(2)
            subject = c5.text_input("Subject")
            room = c6.text_input("Room")
            class_type = st.selectbox("Type", store.types, key="add_type")
            if st.form_submit_button("Add class"):
                if professor and day and time_slot and division and subject:
                    store.add_entry(professor=professor, day=day, time_slot=time_slot,
                        division=division, subject=subject, room=room, type=class_type)
                    store.save()
                    st.success("Entry added!")
                    st.rerun()
                else:
                    st.error("Fill all required fields.")

    with tab_edit:
        records = store.query(division=division_filter, day=day_filter, limit=50)
        if records:
            labels = [f"{r['day']} {r['time_slot']} | {r['division']} | {r['subject']}" for r in records]
            idx = st.selectbox("Select entry", range(len(labels)), format_func=lambda i: labels[i])
            entry = records[idx]
            with st.form("edit_form"):
                new_prof = st.text_input("Professor", value=entry["professor"])
                new_day = st.selectbox("Day", store.days, index=store.days.index(entry["day"]) if entry["day"] in store.days else 0)
                new_slot = st.text_input("Time", value=entry["time_slot"])
                new_div = st.text_input("Division", value=entry["division"])
                new_subj = st.text_input("Subject", value=entry["subject"])
                new_room = st.text_input("Room", value=entry["room"])
                new_type = st.selectbox("Type", store.types, index=store.types.index(entry["type"]) if entry["type"] in store.types else 0)
                if st.form_submit_button("Save changes"):
                    mask = (
                        (store.df["professor"] == entry["professor"]) &
                        (store.df["day"] == entry["day"]) &
                        (store.df["time_slot"] == entry["time_slot"]) &
                        (store.df["division"] == entry["division"]) &
                        (store.df["subject"] == entry["subject"])
                    )
                    ids = store.df.loc[mask, "_id"]
                    if len(ids):
                        store.update_entry(int(ids.iloc[0]), professor=new_prof, day=new_day,
                            time_slot=new_slot, division=new_div, subject=new_subj, room=new_room, type=new_type)
                        store.save()
                        st.success("Updated!")
                        st.rerun()
        else:
            st.info("No entries to edit. Adjust sidebar filters.")

    with tab_del:
        records = store.query(division=division_filter, limit=30)
        if records:
            labels = [f"{r['day']} {r['time_slot']} | {r['division']} | {r['subject']}" for r in records]
            idx = st.selectbox("Entry to delete", range(len(labels)), format_func=lambda i: labels[i], key="del_sel")
            entry = records[idx]
            if st.button("Delete entry", type="primary"):
                mask = (
                    (store.df["professor"] == entry["professor"]) &
                    (store.df["day"] == entry["day"]) &
                    (store.df["time_slot"] == entry["time_slot"]) &
                    (store.df["division"] == entry["division"]) &
                    (store.df["subject"] == entry["subject"])
                )
                ids = store.df.loc[mask, "_id"]
                if len(ids) and store.delete_entry(int(ids.iloc[0])):
                    store.save()
                    st.success("Deleted!")
                    st.rerun()
        else:
            st.info("No entries to delete.")






