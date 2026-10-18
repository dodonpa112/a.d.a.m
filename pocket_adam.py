import streamlit as st
import json
import os
import sqlite3
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Pocket A.D.A.M.",
    page_icon="🛡️",
    layout="centered"
)

client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

MEMORY_FILE = "memory.json"
DB_FILE = "adam_dynamic_memory.db"

# Initialisation de la base de données SQLite pour les souvenirs dynamiques
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def load_memories():
    # 1. Charger le fichier JSON statique (emploi du temps, routines)
    memories = {}
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                memories = json.load(f)
        except Exception:
            pass
            
    # 2. Charger les ajouts dynamiques de la base de données SQLite
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM memories")
    dynamic_mems = cursor.fetchall()
    conn.close()
    
    if "dynamic_notes" not in memories:
        memories["dynamic_notes"] = {}
        
    for k, v in dynamic_mems:
        memories["dynamic_notes"][k] = v
        
    return memories

def save_memory(key: str, value: str) -> str:
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO memories (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()
        return f"Successfully saved: {key} -> {value}"
    except Exception as e:
        return f"Failed to save: {e}"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Saves a permanent fact, wake-up event, appointment, or detail about the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "The category or title (e.g. 'wake_up_today', 'appointment_dentist')"},
                    "value": {"type": "string", "description": "The details of the event or time"}
                },
                "required": ["key", "value"]
            }
        }
    }
]

st.title("🛡️ Pocket A.D.A.M.")
st.caption("Your personal command center, routines, and memory banks.")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Systems online. What do you need to check or update, sir?"}
    ]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if user_input := st.chat_input("Message Pocket A.D.A.M..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    memories = load_memories()
    system_parser_prompt = (
        "You are Pocket A.D.A.M., a smart, concise, and loyal J.A.R.V.I.S.-style personal assistant. "
        "You have full awareness of the user's schedule, routines, academics, and habits. "
        "If the user says things like 'I just woke up' or gives you an appointment/event, ALWAYS use the `save_memory` tool to record it."
    )
    if memories:
        system_parser_prompt += f"\n\nLOADED USER MEMORIES/SCHEDULE:\n{json.dumps(memories, indent=2)}"

    formatted_messages = [{"role": "system", "content": system_parser_prompt}]
    for msg in st.session_state.messages:
        formatted_messages.append({"role": msg["role"], "content": msg["content"]})

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                response = client.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=formatted_messages,
                    tools=TOOLS,
                    tool_choice="auto"
                )
                
                msg = response.choices[0].message
                
                if msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        if tool_call.function.name == "save_memory":
                            args = json.loads(tool_call.function.arguments)
                            res = save_memory(args.get("key"), args.get("value"))
                            reply = f"Noted. I've recorded that: {args.get('key')} — {args.get('value')}."
                            st.markdown(reply)
                            st.session_state.messages.append({"role": "assistant", "content": reply})
                else:
                    reply = msg.content
                    st.markdown(reply)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
            except Exception as e:
                st.error(f"Neural link error: {e}")
