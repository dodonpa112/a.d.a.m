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

# Récupération sécurisée de la clé API (compatible avec les secrets Streamlit Cloud ou fichier .env)
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

# Initialisation de la base de données SQLite pour la persistance cloud
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
    # 1. Charger le fichier JSON statique de base (profil, routines)
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
            
    # 2. Charger les souvenirs dynamiques enregistrés via le chat
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
    """Effectue une recherche web générale en temps réel (actualités, transports, faits, etc.)."""
    try:
        url = f"https://api.duckduckgo.com/?q={requests.utils.quote(query)}&format=json"
        res = requests.get(url).json()
        
        abstract = res.get("AbstractText")
        if abstract:
            return abstract
            
        # Si pas d'extrait direct, on parcourt les sujets associés
        related = res.get("RelatedTopics", [])
        for topic in related:
            if "Text" in topic:
                return topic["Text"]
                
        return f"Résultats de recherche en ligne pour : '{query}'. (Consultez les sources web pour plus de détails)."
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
                    "key": {"type": "string", "description": "Le titre ou la clé de l'information (ex: 'rendez_vous_medecin', 'reveil')"},
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
            "description": "Recherche n'importe quelle information en temps réel sur Internet (actualités, transports à Bruxelles, culture, faits récents, etc.).",
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
        "Si l'utilisateur te demande de retenir quelque chose (comme un réveil ou un rendez-vous), utilise l'outil `save_memory`. "
        "Si l'utilisateur pose une question nécessitant des données actualisées, des faits récents, ou des recherches de transport/itinéraire, "
        "utilise l'outil `search_web`."
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
                        elif tool_call.function.name == "search_web":
                            search_result = search_web(args.get("query"))
                            reply = f"Voici les informations trouvées sur le web :\n\n{search_result}"
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
