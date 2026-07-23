"""College Timetable AI Chatbot — Streamlit app."""
import logging
from pathlib import Path
import streamlit as st
import pandas as pd
from timetable import TimetableStore
from chatbot import TimetableChatbot, detect_ollama, DEFAULT_MODEL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Timetable Assistant", page_icon="📅", layout="wide")

if "toast_msg" in st.session_state:
    st.toast(st.session_state.toast_msg)
    del st.session_state.toast_msg

def get_store():
    store = st.session_state.get("timetable_store")
    if store is None or not hasattr(store, "find_entries"):
        st.session_state.timetable_store = TimetableStore()
    return st.session_state.timetable_store


def get_bot() -> TimetableChatbot:
    model = st.session_state.get("ollama_model", DEFAULT_MODEL)
    return TimetableChatbot(get_store(), model=model)


store = get_store()

# Init status once per session
if "ai_status" not in st.session_state:
    st.session_state.ai_status = get_bot().get_status()

# --- Sidebar ---
with st.sidebar:
    st.title("📅 Timetable")
    st.caption("Filter & customize your view")

    view_mode = st.radio("View", ["Chat", "Grid", "List", "Edit"], horizontal=True)

    st.divider()

    # ── AI Model status ───────────────────────────────────────────────────
    st.subheader("🤖 AI Model")
    status = st.session_state.ai_status
    
    if status["active_provider"] == "ollama":
        models = status["ollama"]["models"] or [DEFAULT_MODEL]
        default_idx = next((i for i, m in enumerate(models) if "llama3.1" in m or m == DEFAULT_MODEL), 0)
        selected = st.selectbox("Model", models, index=default_idx, key="ollama_model", help="Switch between installed Ollama models")
        st.success(f"🟢 Ollama connected · {selected}")
    elif status["active_provider"] == "groq":
        st.success("🟢 Groq connected (Cloud)")
    else:
        st.warning("🟡 AI offline — using basic keyword matching for now")
        st.caption("Still fully usable for queries and edits, just less flexible with phrasing. "
                   "(Add GROQ_API_KEY to secrets or install [Ollama](https://ollama.com) locally for full AI.)")

    if st.button("🔁 Refresh AI status"):
        bot = get_bot()
        bot.refresh_status()
        st.session_state.ai_status = bot.get_status()
        st.rerun()

    st.divider()

    # ── Filters ─────────────────────────────────────────────────────────
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
if st.session_state.ai_status["active_provider"] != "offline":
    provider = st.session_state.ai_status["active_provider"]
    model_name = st.session_state.get("ollama_model", DEFAULT_MODEL) if provider == "ollama" else "Groq Cloud"
    st.markdown(f"Powered by **{model_name}** — ask anything in plain English.")
else:
    st.markdown("Ask questions in plain English about your timetable. *(Connect Ollama or Groq for full AI support.)*")

# --- Main content ---
if view_mode == "Chat":
    col_chat, col_preview = st.columns([1.2, 1])

    with col_chat:
        st.subheader("💬 Chat")
        if "messages" not in st.session_state:
            st.session_state.messages = [{
                "role": "assistant",
                "content": (
                    "Hi! I can **query** and **edit** your timetable.\n\n"
                    "Try asking naturally:\n"
                    "- *What labs does CE2 have on Friday?*\n"
                    "- *Who teaches IT1 on Monday morning?*\n"
                    "- *Show me Dr. Sharma's full schedule*\n"
                    "- *Add a Theory class for AD1 on Tuesday at 11am, subject OS, professor Dr. Mehta, room AC301*\n"
                    "- *Delete id 42*"
                ),
            }]

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if "pending_confirmation" not in st.session_state:
            st.session_state.pending_confirmation = None

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
                        reply, pending = get_bot().chat(
                            prompt, history, st.session_state.pending_confirmation
                        )
                        st.session_state.pending_confirmation = pending
                    except Exception:
                        logger.exception("Chat handling failed for prompt: %r", prompt)
                        reply = (
                            "Sorry, I ran into a problem processing that. "
                            "Please try rephrasing your question, or use the Edit tab instead."
                        )
                        st.session_state.pending_confirmation = None
                st.markdown(reply)
            st.session_state.messages.append({"role": "assistant", "content": reply})

        if st.button("Clear chat"):
            st.session_state.messages = []
            st.session_state.pending_confirmation = None
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
                    try:
                        store.add_entry(professor=professor, day=day, time_slot=time_slot,
                            division=division, subject=subject, room=room, type=class_type)
                        store.save()
                        st.session_state.toast_msg = "✅ Entry successfully added to the database!"
                        st.rerun()
                    except PermissionError:
                        st.error("❌ Cannot save changes! Please close the timetable CSV file in Excel or other programs and try again.")
                else:
                    st.error("Fill all required fields.")

    with tab_edit:
        records = store.query(division=division_filter, day=day_filter, limit=None)
        
        if records:
            labels = [f"{r['day']} {r['time_slot']} | {r['division']} | {r['subject']}" for r in records]
            idx = st.selectbox("Search and select entry to edit", range(len(labels)), format_func=lambda i: labels[i], key="edit_sel")
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
                        try:
                            store.update_entry(int(ids.iloc[0]), professor=new_prof, day=new_day,
                                time_slot=new_slot, division=new_div, subject=new_subj, room=new_room, type=new_type)
                            store.save()
                            st.session_state.toast_msg = "✏️ Entry successfully updated!"
                            st.rerun()
                        except PermissionError:
                            st.error("❌ Cannot save changes! Please close the timetable CSV file in Excel or other programs and try again.")
        else:
            st.info("No entries found. Try adjusting your sidebar filters.")

    with tab_del:
        records = store.query(division=division_filter, day=day_filter, limit=None)
        
        if records:
            labels = [f"{r['day']} {r['time_slot']} | {r['division']} | {r['subject']}" for r in records]
            idx = st.selectbox("Search and select entry to delete", range(len(labels)), format_func=lambda i: labels[i], key="del_sel")
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
                    try:
                        store.save()
                        st.session_state.toast_msg = "🗑️ Entry successfully deleted from the database!"
                        st.rerun()
                    except PermissionError:
                        st.error("❌ Cannot save changes! Please close the timetable CSV file in Excel or other programs and try again.")
        else:
            st.info("No entries found.")
