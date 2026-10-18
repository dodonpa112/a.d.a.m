import streamlit as st
import json
import os
import sqlite3
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="A.D.A.M.",
    page_icon="🛡️",
    layout="centered"
)

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

DB_FILE = "adam_system.db"
MEMORY_FILE = "memory.json"

# --- LISTE OFFICIELLE DE VOCABULAIRE PORTUGAIS ---
PORTUGUESE_VOCAB = [
    ("Eu", "I"), ("Você", "You"), ("Tu", "You"), ("Ele", "He / It"),
    ("Ela", "She / It"), ("Nós", "We"), ("Eles", "They"), ("Elas", "They"),
    ("Me / Mim", "Me"), ("Se", "Oneself"), ("Meu / Minha", "My / Mine"), ("Seu / Sua", "Your / His / Her"),
    ("Ser", "To be"), ("Estar", "To be"), ("Ter", "To have"), ("Fazer", "To do / To make"),
    ("Ir", "To go"), ("Poder", "Can / To be able to"), ("Querer", "To want"), ("Saber", "To know"),
    ("Ver", "To see"), ("Dizer", "To say / To tell"), ("Dar", "To give"), ("Falar", "To speak / To talk"),
    ("Vir", "To come"), ("Ter de / Ter que", "To have to"),
    ("O", "The"), ("A", "The"), ("Os", "The"), ("As", "The"),
    ("Um", "A / An / One"), ("Uma", "A / An / One"), ("Este / Esta", "This"), ("Esse / Essa", "That"),
    ("E", "And"), ("Mas", "But"), ("Ou", "Or"), ("Porque", "Because"),
    ("Se", "If"), ("Como", "As / Like / How"), ("Que", "That / Which / Who"), ("Então", "Then / So"),
    ("Também", "Also / Too"), ("Portanto", "Therefore / So"),
    ("De", "Of / From"), ("Em", "In / On / At"), ("Para", "To / For"), ("Por", "By / Through / For"),
    ("Com", "With"), ("Sem", "Without"), ("Pelo / Pela", "By the / Through the"), ("Sobre", "On / About / Over"), ("Até", "Until / Up to"),
    ("O quê?", "What?"), ("Quem?", "Who?"), ("Onde?", "Where?"), ("Quando?", "When?"),
    ("Por que?", "Why?"), ("Como?", "How?"), ("Quanto?", "How much? / How many?"),
    ("Coisa", "Thing"), ("Tempo", "Time / Weather"), ("Ano", "Year"), ("Dia", "Day"),
    ("Homem", "Man"), ("Mulher", "Woman"), ("Pessoa", "Person"), ("Vida", "Life"),
    ("Mundo", "World"), ("Casa", "House / Home"), ("Trabalho", "Work / Job"), ("Lugar", "Place"),
    ("Bom / Boa", "Good"), ("Mau / Má ou Ruim", "Bad"), ("Grande", "Big / Great"), ("Pequeno / Pequena", "Small"),
    ("Novo / Nova", "New / Young"), ("Velho / Velha", "Old"), ("Outro / Outra", "Other / Another"), ("Mesmo / Mesma", "Same"),
    ("Primeiro / Primeira", "First"), ("Último / Última", "Last"), ("Fácil", "Easy"), ("Difícil", "Difficult"),
    ("Não", "No / Not"), ("Sim", "Yes"), ("Muito", "Very / Much"), ("Pouco", "Little / Few"),
    ("Mais", "More"), ("Menos", "Less"), ("Agora", "Now"), ("Hoje", "Today"),
    ("Já", "Already / Now"), ("Sempre", "Always"), ("Nunca", "Never"), ("Aqui", "Here"),
    ("Ali / Lá", "There"), ("Bem", "Well"), ("Mal", "Badly"), ("Talvez", "Maybe")
]

# --- INITIALISATION DE LA BASE DE DONNÉES ---
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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portuguese_progress (
                date TEXT PRIMARY KEY,
                limit_count INTEGER,
                current_index INTEGER,
                used_words TEXT,
                completed INTEGER
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erreur DB init : {e}")

init_db()

if "pt_state" not in st.session_state:
    st.session_state.pt_state = "IDLE"
    st.session_state.pt_limit = 0
    st.session_state.pt_done_count = 0
    st.session_state.pt_used_indices = []
    st.session_state.pt_current_word = None
    st.session_state.pt_current_translation = None

def check_daily_portuguese_status():
    today_str = str(date.today())
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT limit_count, current_index, used_words, completed FROM portuguese_progress WHERE date = ?", (today_str,))
        row = cursor.fetchone()
        conn.close()
        return row
    except Exception:
        return None

def save_portuguese_progress(limit, index, used, completed):
    today_str = str(date.today())
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO portuguese_progress (date, limit_count, current_index, used_words, completed)
            VALUES (?, ?, ?, ?, ?)
        """, (today_str, limit, index, json.dumps(used), int(completed)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erreur save progress : {e}")

def load_memories():
    memories = {
        "user_name": "Manu Paulo Cristo",
        "institution": "Erasmushogeschool Brussel (EhB) - Campus Kaai",
        "program": "System and Network Management",
        "residence": "Molenbeek-Saint-Jean / Bruxelles",
        "daily_routine": {"wake_up_time": "07:00 AM", "fitness": "Musculation upper/lower split"}
    }
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                memories.update(json.load(f))
        except Exception:
            pass
            
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM memories")
        for k, v in cursor.fetchall():
            memories[k] = v
        conn.close()
    except Exception:
        pass
    return memories

def save_memory(key: str, value: str) -> str:
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO memories (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()
        return f"Enregistré : {key} -> {value}"
    except Exception as e:
        return f"Erreur : {e}"

def search_web(query: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=headers, timeout=10)
        if response.status_code != 200:
            return "Erreur de connexion au service de recherche."
        soup = BeautifulSoup(response.text, 'html.parser')
        results = [s.get_text(strip=True) for s in soup.find_all('a', class_='result__snippet', limit=4) if s.get_text(strip=True)]
        return "\n\n".join(results) if results else "Aucun résultat pertinent trouvé."
    except Exception as e:
        return f"Erreur recherche web : {e}"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Enregistre un fait permanent, calories, protéines, planning ou rendez-vous.",
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
            "description": "Recherche météo actuelle/future, itinéraires de transports en commun avec arrêts et horaires en temps réel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
                "required": ["query"]
            }
        }
    }
]

# --- DESIGN CSS PERSONNALISÉ ---
st.markdown("""
    <style>
    .stApp {
        background-color: #000000;
        color: #ffffff;
    }
    h1 {
        color: #ffffff;
        font-family: 'Inter', sans-serif;
        font-weight: 700;
        text-align: center;
    }
    p {
        text-align: center;
        color: #9ca3af;
    }
    .stChatInput input {
        background-color: #111111 !important;
        color: #ffffff !important;
        border-radius: 8px !important;
        border: 1px solid #333333 !important;
    }
    </style>
""", unsafe_allow_html=True)

# En-tête personnalisé
st.title("A.D.A.M.")
st.markdown("à votre service")
st.markdown("---")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Salutations Mr. Paulo Cristo"}
    ]

# Affichage sécurisé de l'historique sans provoquer d'erreur d'avatar fichier
for msg in st.session_state.messages:
    if msg["role"] == "user":
        with st.chat_message("user", avatar="👤"):
            st.markdown(msg["content"])
    elif msg["role"] == "assistant":
        with st.chat_message("assistant", avatar="🛡️"):
            st.markdown(msg["content"])

if user_input := st.chat_input("Envoyez un message à A.D.A.M..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar="👤"):
        st.markdown(user_input)

    user_clean = user_input.strip().lower()
    
    # --- LOGIQUE PORTUGAISE ---
    db_prog = check_daily_portuguese_status()
    if db_prog and db_prog[3] == 1 and st.session_state.pt_state == "IDLE":
        st.session_state.pt_state = "COMPLETED"
    
    handled_locally = False
    reply = ""

    if user_clean == "estou pronto":
        if db_prog and db_prog[3] == 1:
            reply = "Tu as déjà terminé ta session de portugais pour aujourd'hui. Reviens demain après minuit !"
            st.session_state.pt_state = "COMPLETED"
        else:
            reply = "Quantas palavras hoje?"
            st.session_state.pt_state = "WAITING_LIMIT"
        handled_locally = True

    elif st.session_state.pt_state == "WAITING_LIMIT":
        if user_clean.isdigit():
            limit_val = int(user_clean)
            st.session_state.pt_limit = limit_val
            st.session_state.pt_done_count = 0
            st.session_state.pt_used_indices = []
            
            import random
            idx = random.randint(0, len(PORTUGUESE_VOCAB) - 1)
            st.session_state.pt_used_indices.append(idx)
            st.session_state.pt_current_word = PORTUGUESE_VOCAB[idx][0]
            st.session_state.pt_current_translation = PORTUGUESE_VOCAB[idx][1].lower()
            
            st.session_state.pt_state = "LEARNING"
            save_portuguese_progress(limit_val, 0, st.session_state.pt_used_indices, 0)
            
            reply = f"Parfait ! C'est parti pour {limit_val} mots. Traduis ce mot en français : **{st.session_state.pt_current_word}**"
        else:
            reply = "Veuillez entrer un chiffre valide pour définir la limite (ex: 5)."
        handled_locally = True

    elif st.session_state.pt_state == "LEARNING":
        if user_clean in ["mot suivant", "suivant", "next"]:
            import random
            available = [i for i in range(len(PORTUGUESE_VOCAB)) if i not in st.session_state.pt_used_indices]
            if not available or st.session_state.pt_done_count >= st.session_state.pt_limit:
                st.session_state.pt_state = "COMPLETED"
                save_portuguese_progress(st.session_state.pt_limit, st.session_state.pt_done_count, st.session_state.pt_used_indices, 1)
                reply = "Boa, irmãozinho!"
            else:
                idx = random.choice(available)
                st.session_state.pt_used_indices.append(idx)
                st.session_state.pt_current_word = PORTUGUESE_VOCAB[idx][0]
                st.session_state.pt_current_translation = PORTUGUESE_VOCAB[idx][1].lower()
                reply = f"Nouveau mot : **{st.session_state.pt_current_word}**. Quelle est sa traduction ?"
        else:
            current_trans = st.session_state.pt_current_translation
            valid_options = [t.strip() for t in current_trans.split('/')]
            is_correct = any(v in user_clean for v in valid_options)
            
            if is_correct:
                st.session_state.pt_done_count += 1
                if st.session_state.pt_done_count >= st.session_state.pt_limit:
                    st.session_state.pt_state = "COMPLETED"
                    save_portuguese_progress(st.session_state.pt_limit, st.session_state.pt_done_count, st.session_state.pt_used_indices, 1)
                    reply = "C'est exact ! Et voilà, tu as terminé pour aujourd'hui. Boa, irmãozinho!"
                else:
                    import random
                    available = [i for i in range(len(PORTUGUESE_VOCAB)) if i not in st.session_state.pt_used_indices]
                    if available:
                        idx = random.choice(available)
                        st.session_state.pt_used_indices.append(idx)
                        st.session_state.pt_current_word = PORTUGUESE_VOCAB[idx][0]
                        st.session_state.pt_current_translation = PORTUGUESE_VOCAB[idx][1].lower()
                        reply = f"✅ C'est juste ! Tape **mot suivant** pour continuer."
                    else:
                        reply = "✅ C'est juste, et il n'y a plus de mots disponibles !"
            else:
                reply = f"❌ Faux ! La traduction de **{st.session_state.pt_current_word}** n'est pas correcte ou comporte une faute. Réessaie avec le bon mot et la bonne orthographe."
        handled_locally = True

    elif st.session_state.pt_state == "COMPLETED":
        reply = "Tu as déjà validé ta session de portugais du jour. Reviens demain après minuit pour de nouveaux mots, irmãozinho !"
        handled_locally = True

    # --- TRAITEMENT GÉNÉRAL VIA L'IA ---
    if handled_locally:
        with st.chat_message("assistant", avatar="🛡️"):
            st.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
    else:
        memories = load_memories()
        system_prompt = (
            "Tu es A.D.A.M., un assistant personnel ultra-intelligent, analytique et de style J.A.R.V.I.S., basé à Bruxelles. "
            "Tu assistes Manu Paulo Cristo dans ses études (EhB Campus Kaai), ses plannings, ses calculs de nutrition, "
            "ses prévisions météo détaillées et ses recherches d'itinéraires précis de transports en commun (STIB, bus, tram, train). "
            "Règles strictes : "
            "1. Ne renvoie jamais l'utilisateur vers un site externe : utilise l'outil `search_web` pour trouver les horaires, trams, météo ou données en direct. "
            "2. Enregistre automatiquement toute information utile via `save_memory`."
        )
        if memories:
            system_prompt += f"\n\nDONNÉES ET MÉMOIRES DE L'UTILISATEUR :\n{json.dumps(memories, indent=2)}"

        formatted_messages = [{"role": "system", "content": system_prompt}]
        for m in st.session_state.messages:
            if m["role"] in ["user", "assistant"]:
                formatted_messages.append({"role": m["role"], "content": m["content"]})

        with st.chat_message("assistant", avatar="🛡️"):
            with st.spinner("Analyse tactique en cours..."):
                try:
                    response = client.chat.completions.create(
                        model="openai/gpt-oss-120b",
                        messages=formatted_messages,
                        tools=TOOLS,
                        tool_choice="auto"
                    )
                    msg = response.choices[0].message
                    
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        formatted_messages.append(msg)
                        for tool_call in msg.tool_calls:
                            try:
                                args = json.loads(tool_call.function.arguments)
                            except Exception:
                                args = {}
                                
                            if tool_call.function.name == "save_memory":
                                tool_output = save_memory(args.get("key", "note"), args.get("value", ""))
                            elif tool_call.function.name == "search_web":
                                tool_output = search_web(args.get("query", user_input))
                            else:
                                tool_output = "Action exécutée."
                                
                            formatted_messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": str(tool_output)
                            })
                            
                        final_response = client.chat.completions.create(
                            model="openai/gpt-oss-120b",
                            messages=formatted_messages
                        )
                        reply = final_response.choices[0].message.content
                    else:
                        reply = msg.content if msg.content else "Opération terminée, sir."
                        
                    st.markdown(reply)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                except Exception as e:
                    reply = f"Erreur de liaison neuronale : {e}"
                    st.error(reply)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
