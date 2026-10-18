import streamlit as st
import json
import os
import sqlite3
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv

# Charger les variables d'environnement locales si présentes
load_dotenv()

# Configuration de la page Streamlit
st.set_page_config(
    page_title="Pocket A.D.A.M.",
    page_icon="🛡️",
    layout="centered"
)

# Récupération sécurisée de la clé API Groq
api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    try:
        api_key = st.secrets["GROQ_API_KEY"]
    except Exception:
        api_key = ""

# Initialisation du client OpenAI configuré pour l'API Groq
client = OpenAI(
    api_key=api_key,
    base_url="https://api.groq.com/openai/v1"
)

MEMORY_FILE = "memory.json"
DB_FILE = "adam_dynamic_memory.db"

# Initialisation sécurisée de la base de données SQLite (Persistance Cloud)
def init_db():
    try:
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
    except Exception as e:
        print(f"Erreur d'initialisation de la DB : {e}")

init_db()

def load_memories():
    """Charge le profil statique et fusionne avec les souvenirs dynamiques de la base SQLite."""
    memories = {
        "user_name": "Manu Paulo Cristo",
        "institution": "Erasmushogeschool Brussel (EhB) - Campus Kaai",
        "program": "System and Network Management",
        "residence": "Molenbeek-Saint-Jean / Schaerbeek / Bruxelles",
        "daily_routine": {
            "wake_up_time": "07:00 AM",
            "fitness": "Musculation upper/lower split"
        }
    }
    
    # Chargement optionnel du fichier JSON statique
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                file_data = json.load(f)
                memories.update(file_data)
        except Exception:
            pass
            
    # Chargement des souvenirs dynamiques (enregistrés via le chat)
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM memories")
        dynamic_mems = cursor.fetchall()
        conn.close()
        
        if "dynamic_notes" not in memories:
            memories["dynamic_notes"] = {}
            
        for k, v in dynamic_mems:
            memories["dynamic_notes"][k] = v
    except Exception:
        pass
        
    return memories

def save_memory(key: str, value: str) -> str:
    """Enregistre ou met à jour une information dans la base SQLite persistante."""
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
    """Effectue une recherche web réelle via DuckDuckGo et extrait les meilleurs extraits textuels."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return f"Erreur de connexion au moteur de recherche (Code {response.status_code})."
            
        soup = BeautifulSoup(response.text, 'html.parser')
        results = []
        
        for snippet in soup.find_all('a', class_='result__snippet', limit=4):
            text = snippet.get_text(strip=True)
            if text:
                results.append(text)
                
        if results:
            return "\n\n".join(results)
        else:
            return "Aucun détail textuel n'a pu être extrait pour cette recherche en ligne."
    except Exception as e:
        return f"Erreur lors de la recherche web : {e}"

# Définition rigoureuse des outils (Tools) disponibles pour le modèle
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Enregistre un fait permanent, un réveil, un événement ou un rendez-vous fourni par l'utilisateur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Le titre ou la clé de l'information (ex: 'rendez_vous', 'reveil')"},
                    "value": {"type": "string", "description": "Les détails précis de l'information ou de l'événement"}
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Recherche n'importe quelle information en temps réel sur Internet (actualités, transports, faits récents, culture, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "La question ou le sujet précis à rechercher sur le web"}
                },
                "required": ["query"]
            }
        }
    }
]

# Interface utilisateur Streamlit
st.title("🛡️ Pocket A.D.A.M.")
st.caption("Votre centre de commande personnel, intelligence tactique et mémoires cloud.")

# Initialisation de l'historique des messages dans la session Streamlit
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Systèmes en ligne, sir. Que souhaitez-vous vérifier, planifier ou analyser aujourd'hui ?"}
    ]

# Affichage de l'historique des échanges
for message in st.session_state.messages:
    if message["role"] in ["user", "assistant"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

# Entrée de chat utilisateur
if user_input := st.chat_input("Envoyez un message à A.D.A.M..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Chargement dynamique des mémoires et construction du prompt système
    memories = load_memories()
    system_prompt = (
        "Tu es Pocket A.D.A.M., un assistant personnel ultra-intelligent, analytique et fidèle de style J.A.R.V.I.S., basé à Bruxelles. "
        "Tu assistes Manu Paulo Cristo dans ses études (EhB Campus Kaai), ses routines et ses déplacements. "
        "Règles strictes : "
        "1. Si l'utilisateur te demande de retenir une information, un réveil ou un événement, utilise immédiatement l'outil `save_memory`. "
        "2. Si la question nécessite des données fraîches, des actualités, des faits récents (comme le président des USA en exercice) ou des itinéraires de transport, "
        "utilise obligatoirement l'outil `search_web` et synthétise les résultats pour fournir une réponse directe et précise. "
        "3. Ne renvoie jamais de liens bruts ou de messages d'erreur techniques : formule toujours des réponses polies, claires et structurées."
    )
    
    if memories:
        system_prompt += f"\n\nPROFIL ET MÉMOIRES ACTUELLES DE L'UTILISATEUR :\n{json.dumps(memories, indent=2)}"

    # Construction propre de la liste des messages pour l'API
    formatted_messages = [{"role": "system", "content": system_prompt}]
    for msg in st.session_state.messages:
        if msg["role"] in ["user", "assistant"]:
            formatted_messages.append({"role": msg["role"], "content": msg["content"]})

    with st.chat_message("assistant"):
        with st.spinner("Analyse neuronale en cours..."):
            try:
                # Premier appel à l'API Groq avec gestion des outils
                response = client.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=formatted_messages,
                    tools=TOOLS,
                    tool_choice="auto"
                )
                
                msg = response.choices[0].message
                
                # Gestion robuste des appels d'outils (Tool Calls)
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    # Ajout sécurisé du message de l'assistant contenant l'appel d'outil
                    formatted_messages.append(msg)
                    
                    for tool_call in msg.tool_calls:
                        try:
                            args = json.loads(tool_call.function.arguments)
                        except Exception:
                            args = {}
                            
                        if tool_call.function.name == "save_memory":
                            save_memory(args.get("key", "general"), args.get("value", ""))
                            tool_output = f"C'est enregistré avec succès, sir : {args.get('key')} — {args.get('value')}."
                        elif tool_call.function.name == "search_web":
                            tool_output = search_web(args.get("query", user_input))
                        else:
                            tool_output = "Action exécutée avec succès."
                        
                        # Injection réglementaire du résultat de l'outil avec le rôle "tool"
                        formatted_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": str(tool_output)
                        })
                    
                    # Deuxième appel de suivi pour que le modèle rédige la réponse finale vulgarisée
                    final_response = client.chat.completions.create(
                        model="openai/gpt-oss-120b",
                        messages=formatted_messages
                    )
                    reply = final_response.choices[0].message.content
                    st.markdown(reply)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                else:
                    reply = msg.content if msg.content else "Opération terminée, sir."
                    st.markdown(reply)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                    
            except Exception as e:
                error_msg = f"Erreur de liaison neuronale : {e}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
