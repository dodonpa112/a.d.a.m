import streamlit as st
import json
import os
import sqlite3
import requests
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
    memories = {}
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                memories = json.load(f)
        except Exception:
            pass
            
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

def search_web(query: str) -> str:
    """Utilise une recherche en ligne pour trouver des horaires de tram ou des infos en temps réel."""
    try:
        # Recherche rapide via une API publique ou DuckDuckGo instant answer
        url = f"https://api.duckduckgo.com/?q={query}&format=json"
        res = requests.get(url).json()
        abstract = res.get("AbstractText")
        if abstract:
            return abstract
        # Fallback de recherche textuelle
        return f"Recherche effectuée pour : {query}. Consultez les applications de transport (STIB/NMBS) pour les horaires exacts en direct."
    except Exception as e:
        return f"Erreur lors de la recherche transport : {e}"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Enregistre un fait permanent, un réveil ou un rendez-vous.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"}
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Recherche des informations en temps réel sur les transports, les trams ou les trajets à Bruxelles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "La requête de transport ou d'itinéraire (ex: horaires tram Bruxelles, trajet vers Campus Kaai)"}
                },
                "required": ["query"]
            }
        }
    }
]

st.title("🛡️ Pocket A.D.A.M.")
st.caption("Votre centre de commande personnel, routines et transports.")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Systèmes en ligne, sir. Que souhaitez-vous vérifier ou planifier ?"}
    ]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if user_input := st.chat_input("Envoyez un message à A.D.A.M..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    memories = load_memories()
    system_prompt = (
        "Tu es Pocket A.D.A.M., un assistant personnel intelligent et fidèle de style J.A.R.V.I.S., basé à Bruxelles. "
        "Tu as accès aux horaires de l'EhB (Campus Kaai), aux routines de l'utilisateur, et tu peux utiliser l'outil `search_web` "
        "pour trouver des informations sur les transports en commun (STIB, trams, bus, trains) ou des estimations de trajets si on te le demande."
    )
    if memories:
        system_prompt += f"\n\nMÉMOIRES ET EMPLOI DU TEMPS DE L'UTILISATEUR :\n{json.dumps(memories, indent=2)}"

    formatted_messages = [{"role": "system", "content": system_prompt}]
    for msg in st.session_state.messages:
        formatted_messages.append({"role": msg["role"], "content": msg["content"]})

    with st.chat_message("assistant"):
        with st.spinner("Analyse en cours..."):
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
                        args = json.loads(tool_call.function.arguments)
                        if tool_call.function.name == "save_memory":
                            save_memory(args.get("key"), args.get("value"))
                            reply = f"C'est noté. J'ai enregistré : {args.get('key')} — {args.get('value')}."
                        elif tool_call.function.name == "search_web":
                            search_result = search_web(args.get("query"))
                            reply = f"Voici les informations de trajet trouvées :\n\n{search_result}"
                        else:
                            reply = "Action exécutée."
                        
                        st.markdown(reply)
                        st.session_state.messages.append({"role": "assistant", "content": reply})
                else:
                    reply = msg.content
                    st.markdown(reply)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
            except Exception as e:
                st.error(f"Erreur de liaison neuronale : {e}")
