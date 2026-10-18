import streamlit as st
import json
import os
import sqlite3
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Pocket A.D.A.M.",
    page_icon="🛡️",
    layout="centered"
)

# Récupération sécurisée de la clé API
api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    try:
        api_key = st.secrets["GROQ_API_KEY"]
    except Exception:
        api_key = ""

client = OpenAI(
    api_key=api_key,
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
    memories = {
        "user_name": "Manu Paulo Cristo",
        "institution": "Erasmushogeschool Brussel (EhB) - Campus Kaai",
        "program": "System and Network Management",
        "residence": "Molenbeek-Saint-Jean / Bruxelles",
        "daily_routine": {
            "wake_up_time": "07:00 AM",
            "fitness": "Musculation upper/lower split"
        }
    }
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                file_data = json.load(f)
                memories.update(file_data)
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
    """Effectue une recherche web réelle et extrait les extraits pertinents (snippets)."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return f"Erreur de connexion au moteur de recherche (Code {response.status_code})."
            
        soup = BeautifulSoup(response.text, 'html.parser')
        results = []
        
        # Extraction des snippets de résultats de recherche DuckDuckGo
        for snippet in soup.find_all('a', class_='result__snippet', limit=3):
            text = snippet.get_text(strip=True)
            if text:
                results.append(text)
                
        if results:
            return "\n\n".join(results)
        else:
            return "Aucun détail textuel n'a pu être extrait pour cette recherche."
    except Exception as e:
        return f"Erreur lors de la recherche web : {e}"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Enregistre un fait permanent, un réveil, un événement ou un rendez-vous fourni par l'utilisateur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Le titre ou la clé de l'information"},
                    "value": {"type": "string", "description": "Les détails de l'événement ou de l'information"}
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Recherche n'importe quelle information en temps réel sur Internet (actualités, transports, faits, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "La question ou le sujet à rechercher sur le web"}
                },
                "required": ["query"]
            }
        }
    }
]

st.title("🛡️ Pocket A.D.A.M.")
st.caption("Votre centre de commande personnel, routines et mémoires.")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Systèmes en ligne, sir. Que souhaitez-vous vérifier, planifier ou rechercher ?"}
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
        "Tu es Pocket A.D.A.M., un assistant personnel intelligent et polyvalent de style J.A.R.V.I.S., basé à Bruxelles. "
        "Tu as accès aux informations personnelles et aux routines de l'utilisateur. "
        "Si l'utilisateur te demande de retenir quelque chose, utilise l'outil `save_memory`. "
        "Si l'utilisateur pose une question nécessitant des données actualisées, des faits récents, ou des recherches, "
        "utilise obligatoirement l'outil `search_web` et synthétise les résultats pour lui répondre clairement."
    )
    if memories:
        system_prompt += f"\n\nPROFIL ET MÉMOIRES DE L'UTILISATEUR :\n{json.dumps(memories, indent=2)}"

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
                            reply = f"C'est noté, sir. J'ai enregistré : {args.get('key')} — {args.get('value')}."
                            st.markdown(reply)
                            st.session_state.messages.append({"role": "assistant", "content": reply})
                        elif tool_call.function.name == "search_web":
                            search_result = search_web(args.get("query"))
                            
                            # On renvoie les résultats au modèle pour qu'il rédige une belle réponse synthétique
                            followup_messages = formatted_messages + [
                                msg,
                                {
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": search_result
                                }
                            ]
                            
                            final_response = client.chat.completions.create(
                                model="openai/gpt-oss-120b",
                                messages=followup_messages
                            )
                            reply = final_response.choices[0].message.content
                            st.markdown(reply)
                            st.session_state.messages.append({"role": "assistant", "content": reply})
                else:
                    reply = msg.content
                    st.markdown(reply)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
            except Exception as e:
                st.error(f"Erreur de liaison neuronale : {e}")
