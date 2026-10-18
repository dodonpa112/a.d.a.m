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

# Récupération sécurisée de la clé API Groq
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
    ("Eu", "Je"), ("Você", "Vous"), ("Tu", "Tu"), ("Ele", "Il"),
    ("Ela", "Elle"), ("Nós", "Nous"), ("Eles", "Eux / Ils"), ("Elas", "Elles"),
    ("Me / Mim", "Moi"), ("Se", "Se / Soi"), ("Meu / Minha", "Mon / Ma / Miens"), ("Seu / Sua", "Ton / Sa / Son"),
    ("Ser", "Être"), ("Estar", "Être"), ("Ter", "Avoir"), ("Fazer", "Faire"),
    ("Ir", "Aller"), ("Poder", "Pouvoir"), ("Querer", "Vouloir"), ("Saber", "Savoir"),
    ("Ver", "Voir"), ("Dizer", "Dire"), ("Dar", "Donner"), ("Falar", "Parler"),
    ("Vir", "Venir"), ("Ter de / Ter que", "Devoir"),
    ("O", "Le"), ("A", "La"), ("Os", "Les"), ("As", "Les"),
    ("Um", "Un"), ("Uma", "Une"), ("Este / Esta", "Ce / Cette"), ("Esse / Essa", "Ce / Cette"),
    ("E", "Et"), ("Mas", "Mais"), ("Ou", "Ou"), ("Porque", "Parce que"),
    ("Se", "Si"), ("Como", "Comme"), ("Que", "Que"), ("Então", "Alors / Donc"),
    ("Também", "Aussi"), ("Portanto", "Par conséquent / Donc"),
    ("De", "De"), ("Em", "Dans / En / Sur"), ("Para", "Pour / Vers"), ("Por", "Par"),
    ("Com", "Avec"), ("Sem", "Sans"), ("Pelo / Pela", "Par le / Par la"), ("Sobre", "Sur / À propos de"), ("Até", "Jusqu'à"),
    ("O quê?", "Quoi ?"), ("Quem?", "Qui ?"), ("Onde?", "Où ?"), ("Quando?", "Quand ?"),
    ("Por que?", "Pourquoi ?"), ("Como?", "Comment ?"), ("Quanto?", "Combien ?"),
    ("Coisa", "Chose"), ("Tempo", "Temps"), ("Ano", "Année"), ("Dia", "Jour"),
    ("Homem", "Homme"), ("Mulher", "Femme"), ("Pessoa", "Personne"), ("Vida", "Vie"),
    ("Mundo", "Monde"), ("Casa", "Maison"), ("Trabalho", "Travail"), ("Lugar", "Lieu / Endroit"),
    ("Bom / Boa", "Bon / Bonne"), ("Mau / Má ou Ruim", "Mauvais / Mauvaise"), ("Grande", "Grand / Grande"), ("Pequeno / Pequena", "Petit / Petite"),
    ("Novo / Nova", "Nouveau / Neuf / Jeune"), ("Velho / Velha", "Vieux / Vieille"), ("Outro / Outra", "Autre"), ("Mesmo / Mesma", "Même"),
    ("Primeiro / Primeira", "Premier / Première"), ("Último / Última", "Dernier / Dernière"), ("Fácil", "Facile"), ("Difícil", "Difficile"),
    ("Não", "Non"), ("Sim", "Oui"), ("Muito", "Très / Beaucoup"), ("Pouco", "Peu"),
    ("Mais", "Plus"), ("Menos", "Moins"), ("Agora", "Maintenant"), ("Hoje", "Aujourd'hui"),
    ("Já", "Déjà"), ("Sempre", "Toujours"), ("Nunca", "Jamais"), ("Aqui", "Ici"),
    ("Ali / Lá", "Là-bas / Là"), ("Bem", "Bien"), ("Mal", "Mal"), ("Talvez", "Peut-être")
]

# --- MISE EN CACHE DE LA BDD ---
@st.cache_resource
def init_db():
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
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

def read_memory(topic: str = "all") -> str:
    memories = load_memories()
    if not memories:
        return "Aucune mémoire enregistrée."
    return json.dumps(memories, separators=(',', ':'))

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
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=headers, timeout=5)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        results = [s.get_text(strip=True) for s in soup.find_all('a', class_='result__snippet', limit=2) if s.get_text(strip=True)]
        
        final_text = " | ".join(results)[:500] 
        return final_text if final_text else "Aucun résultat pertinent trouvé."
    except Exception as e:
        return f"Erreur recherche web : {e}"

def get_canvas_assignments() -> str:
    token = os.environ.get("CANVAS_API_TOKEN")
    try:
        if not token:
            token = st.secrets.get("CANVAS_API_TOKEN", "")
    except Exception:
        pass
        
    base_url = os.environ.get("CANVAS_BASE_URL", "https://ehb.instructure.com")
    if not token:
        return "Le token d'accès Canvas n'est pas configuré dans les secrets."
        
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(f"{base_url}/api/v1/users/self/upcoming_events", headers=headers, timeout=10)
        if response.status_code == 200:
            events = response.json()
            event_list = [f"- {e.get('title')} (Date limite : {e.get('end_at')})" for e in events]
            return "Voici vos prochaines échéances sur Canvas :\n" + "\n".join(event_list) if event_list else "Aucun devoir urgent trouvé sur Canvas."
        else:
            return f"Erreur lors de la récupération des devoirs Canvas (Code {response.status_code})."
    except Exception as e:
        return f"Erreur Canvas : {e}"

def control_pc(app_name: str) -> str:
    bridge_url = os.environ.get("PC_BRIDGE_URL")
    try:
        if not bridge_url:
            bridge_url = st.secrets.get("PC_BRIDGE_URL", "")
    except Exception:
        pass
        
    if not bridge_url:
        return "Le pont de connexion vers le PC (PC_BRIDGE_URL) n'est pas configuré dans les secrets."
        
    try:
        response = requests.post(f"{bridge_url}/execute", json={"app_name": app_name}, timeout=5)
        if response.status_code == 200:
            return f"Ordre de lancement pour '{app_name}' exécuté avec succès sur votre PC."
        else:
            return "Impossible de joindre le PC (vérifiez si le script local et Ngrok sont actifs)."
    except Exception as e:
        return f"Erreur de communication avec le PC : {e}"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_memory",
            "description": "Consulte la mémoire locale pour retrouver des informations sur l'utilisateur (planning, préférences, notes personnelles).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
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
    },
    {
        "type": "function",
        "function": {
            "name": "get_canvas_assignments",
            "description": "Récupère les devoirs, échéances et tâches à rendre sur la plateforme Canvas de l'EhB.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_pc",
            "description": "Lance une application spécifique sur le PC de l'utilisateur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Le nom exact de l'exécutable Windows (ex: 'notepad' pour le bloc-notes, 'chrome', 'calc', 'spotify', 'winword'). Ne mettez jamais l'extension .exe."
                    }
                },
                "required": ["app_name"]
            }
        }
    }
]

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

st.title("A.D.A.M.")
st.markdown("à votre service")
st.markdown("---")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Salutations Mr. Paulo Cristo"}
    ]

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
    
    db_prog = check_daily_portuguese_status()
    is_completed_today = (db_prog and db_prog[3] == 1)
    
    handled_locally = False
    reply = ""

    if user_clean == "estou pronto":
        if is_completed_today:
            reply = "Tu as déjà validé ta session de portugais du jour. Reviens demain après minuit pour de nouveaux mots, irmãozinho !"
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
            
            reply = f"Parfait ! C'est parti pour {limit_val} mots. Traduis ce mot en **français** : **{st.session_state.pt_current_word}**"
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
                reply = f"Nouveau mot en français : **{st.session_state.pt_current_word}**. Quelle est sa traduction ?"
        else:
            current_trans = st.session_state.pt_current_translation
            valid_options = [t.strip() for t in current_trans.split('/')]
            is_correct = any(v in user_clean for v in valid_options)
            
            if is_correct:
                st.session_state.pt_done_count += 1
                if st.session_state.pt_done_count >= st.session_state.pt_limit:
                    st.session_state.pt_state = "COMPLETED"
                    save_portuguese_progress(st.session_state.pt_limit, st.session_state.pt_done_count, st.session_state.pt_used_indices, 1)
                    reply = "C'est exact ! Et voilà, tu as atteint la fin pour aujourd'hui. Boa, irmãozinho!"
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
                        st.session_state.pt_state = "COMPLETED"
                        save_portuguese_progress(st.session_state.pt_limit, st.session_state.pt_done_count, st.session_state.pt_used_indices, 1)
                        reply = "✅ C'est juste ! Il n'y a plus de mots disponibles. Boa, irmãozinho!"
            else:
                reply = f"❌ Faux ! La traduction française de **{st.session_state.pt_current_word}** n'est pas correcte. Réessaie com le bon mot."
        handled_locally = True

    # --- TRAITEMENT GÉNÉRAL VIA L'IA ---
    if handled_locally:
        with st.chat_message("assistant", avatar="🛡️"):
            st.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
    else:
        system_prompt = (
            "Tu es A.D.A.M. (J.A.R.V.I.S style), assistant de Manu Paulo Cristo à Bruxelles. "
            "Règles: 1. Utilise tes outils pour t'informer si besoin (read_memory, search_web, get_canvas_assignments, control_pc). "
            "2. Ne charge pas d'informations au hasard. 3. Sois concis. 4. Enregistre les faits importants via save_memory."
        )

        formatted_messages = [{"role": "system", "content": system_prompt}]
        
        recent_messages = st.session_state.messages[-6:]
        for m in recent_messages:
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
                                
                            if tool_call.function.name == "read_memory":
                                tool_output = read_memory()
                            elif tool_call.function.name == "save_memory":
                                tool_output = save_memory(args.get("key", "note"), args.get("value", ""))
                            elif tool_call.function.name == "search_web":
                                tool_output = search_web(args.get("query", user_input))
                            elif tool_call.function.name == "get_canvas_assignments":
                                tool_output = get_canvas_assignments()
                            elif tool_call.function.name == "control_pc":
                                tool_output = control_pc(args.get("app_name", ""))
                            else:
                                tool_output = "Action exécutée."
                                
                            formatted_messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": str(tool_output)
                            })
                            
                        # --- CORRECTION DE L'ERREUR 400 ---
                        final_response = client.chat.completions.create(
                            model="openai/gpt-oss-120b",
                            messages=formatted_messages,
                            tools=TOOLS,
                            tool_choice="none" # Empêche l'IA de relancer un outil en boucle
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
