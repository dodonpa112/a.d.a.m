import streamlit as st
import json
import os
import sqlite3
import random
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

# --- CONFIGURATION SÉCURISÉE DES SECRETS ---
def get_secret(key: str, default: str = "") -> str:
    val = os.environ.get(key)
    if not val:
        try:
            val = st.secrets.get(key, default)
        except Exception:
            val = default
    return str(val).strip()

api_key = get_secret("GROQ_API_KEY")
client = OpenAI(
    api_key=api_key if api_key else "missing_key",
    base_url="https://api.groq.com/openai/v1"
)

# Liste de modèles par ordre de priorité (Bascule automatique si un modèle n'existe plus)
FALLBACK_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.1-8b-instant"
]

def call_llm(messages, tools=None, tool_choice=None, temperature=0.2):
    """Appelle Groq en testant les modèles de secours si le modèle principal est indisponible."""
    last_error = None
    for model_name in FALLBACK_MODELS:
        try:
            kwargs = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature
            }
            if tools is not None:
                kwargs["tools"] = tools
            if tool_choice is not None:
                kwargs["tool_choice"] = tool_choice
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            if "404" in err_str or "model_not_found" in err_str or "decommissioned" in err_str or "not exist" in err_str:
                continue
            raise e
    raise last_error

DB_FILE = "adam_system.db"
MEMORY_FILE = "memory.json"

# --- LISTE OFFICIELLE DE VOCABULAIRE PORTUGAIS (100% FRANÇAIS) ---
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

# --- INITIALISATION DE LA BASE DE DONNÉES SQLite (AVEC CACHE & LOCK-SAFE) ---
@st.cache_resource
def init_db():
    try:
        with sqlite3.connect(DB_FILE, timeout=10, check_same_thread=False) as conn:
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
    except Exception as e:
        print(f"Erreur DB init : {e}")

init_db()

# --- ÉTAT DE SESSION PORTUGAIS ---
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
        with sqlite3.connect(DB_FILE, timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT limit_count, current_index, used_words, completed FROM portuguese_progress WHERE date = ?", (today_str,))
            return cursor.fetchone()
    except Exception:
        return None

def save_portuguese_progress(limit, index, used, completed):
    today_str = str(date.today())
    try:
        with sqlite3.connect(DB_FILE, timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO portuguese_progress (date, limit_count, current_index, used_words, completed)
                VALUES (?, ?, ?, ?, ?)
            """, (today_str, limit, index, json.dumps(used), int(completed)))
            conn.commit()
    except Exception as e:
        print(f"Erreur save progress : {e}")

# --- GESTION DE LA MÉMOIRE ET DES OUTILS ---
def load_memories():
    memories = {
        "user_name": "Manu Paulo Cristo",
        "institution": "Erasmushogeschool Brussel (EhB) - Campus Kaai",
        "program": "System and Network Management",
        "residence": "Bruxelles",
        "campus_kaai": "Nijverheidskaai 170, 1070 Anderlecht",
        "daily_routine": {"wake_up_time": "07:00 AM", "fitness": "Musculation upper/lower split"}
    }
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                memories.update(json.load(f))
        except Exception:
            pass
            
    try:
        with sqlite3.connect(DB_FILE, timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM memories")
            for k, v in cursor.fetchall():
                memories[k] = v
    except Exception:
        pass
    return memories

def read_memory() -> str:
    memories = load_memories()
    if not memories:
        return "Aucune mémoire enregistrée."
    return json.dumps(memories, ensure_ascii=False, separators=(',', ':'))

def save_memory(key: str, value: str) -> str:
    if not key or not value:
        return "Erreur : clé ou valeur manquante."
    try:
        with sqlite3.connect(DB_FILE, timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO memories (key, value) VALUES (?, ?)", (str(key).strip(), str(value).strip()))
            conn.commit()
        return f"Enregistré en mémoire : {key} = {value}"
    except Exception as e:
        return f"Erreur sauvegarde mémoire : {e}"

def search_web(query: str) -> str:
    if not query:
        return "Requête de recherche vide."
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        response = requests.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=headers, timeout=6)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        results = [s.get_text(strip=True) for s in soup.find_all('a', class_='result__snippet', limit=3) if s.get_text(strip=True)]
        
        final_text = " | ".join(results)[:700]
        return final_text if final_text else "Aucun résultat web trouvé."
    except Exception as e:
        return f"Service web indisponible ({e})."

def get_route(origin: str, destination: str) -> str:
    """Calcule un itinéraire réel via la nouvelle Google Routes API."""
    api_key = get_secret("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return "Erreur : La clé API Google Maps (GOOGLE_MAPS_API_KEY) n'est pas configurée dans les secrets Streamlit."
    
    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.legs.steps"
    }
    payload = {
        "origin": {"address": origin},
        "destination": {"address": destination},
        "travelMode": "TRANSIT",
        "languageCode": "fr"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=8)
        data = response.json()
        
        if "routes" in data and len(data["routes"]) > 0:
            route = data["routes"][0]
            duration_sec = int(route.get("duration", "0s").replace("s", ""))
            duration_min = round(duration_sec / 60)
            distance_m = route.get("distanceMeters", 0)
            
            summary = f"**Itinéraire officiel (Routes API) de {origin} vers {destination}**\n"
            summary += f"⏱️ Durée estimée : environ **{duration_min} minutes** (Distance : {distance_m} m)\n"
            return summary
        else:
            return f"Impossible de calculer l'itinéraire via la Routes API. Réponse : {data}"
    except Exception as e:
        return f"Erreur de connexion au service cartographique : {e}"

def get_canvas_assignments() -> str:
    token = get_secret("CANVAS_API_TOKEN")
    base_url = get_secret("CANVAS_BASE_URL", "https://ehb.instructure.com").rstrip('/')
    
    if not token:
        return "Le token Canvas (CANVAS_API_TOKEN) n'est pas configuré dans les secrets Streamlit."
        
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r_events = requests.get(f"{base_url}/api/v1/users/self/upcoming_events", headers=headers, timeout=8)
        r_todo = requests.get(f"{base_url}/api/v1/users/self/todo", headers=headers, timeout=8)
        
        items = []
        if r_events.status_code == 200:
            for e in r_events.json()[:5]:
                title = e.get('title', 'Sans titre')
                date_end = e.get('end_at') or e.get('start_at') or 'Date non spécifiée'
                items.append(f"- [Événement] {title} (Échéance : {date_end})")
                
        if r_todo.status_code == 200:
            for t in r_todo.json()[:5]:
                assignment = t.get('assignment', {})
                title = assignment.get('name', 'Tâche')
                due = assignment.get('due_at', 'Sans date')
                items.append(f"- [Devoir] {title} (Pour le : {due})")
                
        if r_events.status_code != 200 and r_todo.status_code != 200:
            return f"Erreur API Canvas (Code HTTP {r_events.status_code})."
            
        return "Échéances Canvas :\n" + "\n".join(items) if items else "Aucun devoir ou événement à venir sur Canvas."
    except Exception as e:
        return f"Erreur Canvas : {e}"

def control_pc(app_name: str = "", action: str = "", target: str = "") -> str:
    raw_url = get_secret("PC_BRIDGE_URL")
    if not raw_url:
        return "Erreur : PC_BRIDGE_URL n'est pas configuré dans les secrets Streamlit."
        
    bridge_url = raw_url.split("->")[0].strip().rstrip('/')
    final_app = (app_name or target or action).strip().lower()
    if not final_app:
        return "Erreur : Aucun nom d'application fourni."

    headers = {
        "Content-Type": "application/json",
        "ngrok-skip-browser-warning": "true"
    }
    
    try:
        response = requests.post(
            f"{bridge_url}/execute",
            json={"app_name": final_app, "target": final_app, "action": "open"},
            headers=headers,
            timeout=6
        )
        if response.status_code == 200:
            return f"Succès : Commande d'ouverture pour '{final_app}' exécutée sur le PC."
        else:
            return f"Erreur PC (Code {response.status_code}) : {response.text}"
    except Exception as e:
        return f"Impossible de joindre le PC (Vérifiez adam_bridge.py et Ngrok) : {e}"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_memory",
            "description": "Consulte la mémoire locale pour retrouver l'adresse de domicile, le planning, la routine ou les notes personnelles.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Enregistre une information permanente (adresse, calories, protéines, planning, rendez-vous, préférences).",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Nom de la clé (ex: 'adresse_domicile')"},
                    "value": {"type": "string", "description": "Valeur à enregistrer"}
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_route",
            "description": "Calcule un itinéraire réel et officiel entre une adresse de départ et une destination (comme 'Nijverheidskaai 170, Anderlecht' pour Campus Kaai) en transport en commun.",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "L'adresse ou le lieu de départ exact (ex: 'Rue des Palais 116, Schaerbeek')"},
                    "destination": {"type": "string", "description": "L'adresse ou le lieu d'arrivée exact (ex: 'Nijverheidskaai 170, Anderlecht')"}
                },
                "required": ["origin", "destination"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Recherche sur le web des informations générales d'actualité.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Mots-clés de recherche"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_canvas_assignments",
            "description": "Récupère les devoirs et échéances sur Canvas de l'EhB.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_pc",
            "description": "Lance une application sur le PC Windows de l'utilisateur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Nom exact de l'exécutable Windows sans .exe (ex: 'notepad', 'calc', 'chrome')."
                    }
                },
                "required": ["app_name"]
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

# --- MOTEUR D'EXÉCUTION D'OUTILS ---
def execute_tool_call(tool_call, fallback_query=""):
    name = tool_call.function.name
    try:
        args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
        if not isinstance(args, dict):
            args = {}
    except Exception:
        args = {}

    if name == "read_memory":
        return read_memory()
    elif name == "save_memory":
        return save_memory(args.get("key", "note"), args.get("value", ""))
    elif name == "get_route":
        return get_route(args.get("origin", ""), args.get("destination", ""))
    elif name == "search_web":
        return search_web(args.get("query", fallback_query))
    elif name == "get_canvas_assignments":
        return get_canvas_assignments()
    elif name == "control_pc":
        return control_pc(
            app_name=args.get("app_name", ""),
            action=args.get("action", ""),
            target=args.get("target", "")
        )
    return "Outil inconnu."

# --- GESTION DES ENTRÉES UTILISATEUR ---
if user_input := st.chat_input("Envoyez un message à A.D.A.M..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar="👤"):
        st.markdown(user_input)

    user_clean = user_input.strip().lower()
    
    # --- 1. LOGIQUE PORTUGAISE 100% LOCALE ---
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
        if user_clean.isdigit() and int(user_clean) > 0:
            limit_val = int(user_clean)
            st.session_state.pt_limit = limit_val
            st.session_state.pt_done_count = 0
            st.session_state.pt_used_indices = []
            
            idx = random.randint(0, len(PORTUGUESE_VOCAB) - 1)
            st.session_state.pt_used_indices.append(idx)
            st.session_state.pt_current_word = PORTUGUESE_VOCAB[idx][0]
            st.session_state.pt_current_translation = PORTUGUESE_VOCAB[idx][1].lower()
            
            st.session_state.pt_state = "LEARNING"
            save_portuguese_progress(limit_val, 0, st.session_state.pt_used_indices, 0)
            
            reply = f"Parfait ! C'est parti pour {limit_val} mots. Traduis ce mot en **français** : **{st.session_state.pt_current_word}**"
        else:
            reply = "Veuillez entrer un chiffre valide supérieur à 0 (ex: 5)."
        handled_locally = True

    elif st.session_state.pt_state == "LEARNING":
        if user_clean in ["stop", "quitter", "annuler", "exit"]:
            st.session_state.pt_state = "IDLE"
            reply = "Session de portugais interrompue, sir."
        elif user_clean in ["mot suivant", "suivant", "next"]:
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
            is_correct = any(v == user_clean or v in user_clean.split() for v in valid_options)
            
            if is_correct:
                st.session_state.pt_done_count += 1
                if st.session_state.pt_done_count >= st.session_state.pt_limit:
                    st.session_state.pt_state = "COMPLETED"
                    save_portuguese_progress(st.session_state.pt_limit, st.session_state.pt_done_count, st.session_state.pt_used_indices, 1)
                    reply = "C'est exact ! Tu as atteint la fin pour aujourd'hui. Boa, irmãozinho!"
                else:
                    reply = "✅ C'est juste ! Tape **mot suivant** pour continuer."
            else:
                reply = f"❌ Faux ! La traduction de **{st.session_state.pt_current_word}** n'est pas correcte. Réessaie."
        handled_locally = True

    # --- 2. TRAITEMENT GÉNÉRAL VIA L'IA ---
    if handled_locally:
        with st.chat_message("assistant", avatar="🛡️"):
            st.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
    else:
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        system_prompt = (
            f"Tu es A.D.A.M. (style J.A.R.V.I.S.), l'assistant personnel de Manu Paulo Cristo à Bruxelles (Étudiant EhB Campus Kaai). "
            f"Date et heure : {now_str}. "
            "Règles : "
            "1. Pour tout calcul d'itinéraire officiel, utilise TOUJOURS l'outil `get_route` en récupérant d'abord ton adresse en mémoire via `read_memory` si besoin (Campus Kaai = Nijverheidskaai 170, Anderlecht). "
            "2. Enregistre tout fait important avec `save_memory`. "
            "3. Pour ouvrir une application PC, appelle `control_pc`. "
            "4. Sois précis et concis."
        )

        formatted_messages = [{"role": "system", "content": system_prompt}]
        for m in st.session_state.messages[-6:]:
            if m["role"] in ["user", "assistant"] and m.get("content"):
                formatted_messages.append({"role": m["role"], "content": m["content"]})

        with st.chat_message("assistant", avatar="🛡️"):
            with st.spinner("Analyse tactique en cours..."):
                reply = ""
                try:
                    for step in range(3):
                        response = call_llm(
                            messages=formatted_messages,
                            tools=TOOLS,
                            tool_choice="auto",
                            temperature=0.2
                        )
                        msg = response.choices[0].message

                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            assistant_msg = {
                                "role": "assistant",
                                "content": msg.content or "",
                                "tool_calls": [
                                    {
                                        "id": tc.id,
                                        "type": "function",
                                        "function": {
                                            "name": tc.function.name,
                                            "arguments": tc.function.arguments
                                        }
                                    } for tc in msg.tool_calls
                                ]
                            }
                            formatted_messages.append(assistant_msg)

                            for tool_call in msg.tool_calls:
                                tool_output = execute_tool_call(tool_call, fallback_query=user_input)
                                formatted_messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": str(tool_output)
                                })
                        else:
                            reply = msg.content or "Opération effectuée, sir."
                            break

                    if not reply:
                        final_res = call_llm(messages=formatted_messages, temperature=0.2)
                        reply = final_res.choices[0].message.content or "Opération terminée, sir."

                except Exception as e:
                    try:
                        mem_context = read_memory()
                        fallback_messages = [
                            {"role": "system", "content": f"{system_prompt}\nMémoire : {mem_context}"},
                            {"role": "user", "content": user_input}
                        ]
                        fallback_res = call_llm(messages=fallback_messages, temperature=0.3)
                        reply = fallback_res.choices[0].message.content
                    except Exception as fatal_e:
                        reply = f"Erreur de liaison neuronale : {fatal_e}"
                        st.error(reply)

                if reply:
                    st.markdown(reply)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
