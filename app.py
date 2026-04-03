import streamlit as st
import websocket
import json
import pandas as pd
import threading
import requests
from streamlit_autorefresh import st_autorefresh

# --- KONFIGURACIJA STRANI ---
st.set_page_config(page_title="KZS Live Advanced Stats", layout="wide", page_icon="🏀")

# Avtomatsko osveževanje vmesnika na 5 sekund, da vidimo nove podatke iz ozadja
st_autorefresh(interval=5000, key="datarefresh")

# --- FUNKCIJA ZA ISKANJE TEKEM (Auto-Discovery) ---
def get_active_matches():
    """Poskuša pridobiti seznam trenutnih tekem s KZS."""
    try:
        # KZS uporablja ta interni API za seznam tekem
        res = requests.get("https://zapisniki.kzs.si/api/v1/matches/active", timeout=5)
        data = res.json()
        matches = {f"{m['homeTeam']['name']} vs {m['awayTeam']['name']}": m['id'] for m in data}
        return matches
    except:
        # Če API ne vrne podatkov (npr. ni tekem), vrnemo prazno
        return {}

# --- SHRAMBA PODATKOV (Session State) ---
if 'db' not in st.session_state:
    st.session_state.db = pd.DataFrame(columns=['vreme', 'ekipa', 'igralec', 'akcija', 'tocke'])

if 'ws_active' not in st.session_state:
    st.session_state.ws_active = False

# --- LOGIKA ZA WEBSOCKET ---
def run_websocket(match_id):
    def on_message(ws, message):
        data = json.loads(message)
        if "message" in data:
            msg = data["message"]
            # Mapiranje KZS JSON polj v našo tabelo
            # OPOMBA: Ključe (npr. 'score', 'player') prilagodi glede na dejanski izpis v živo
            new_event = {
                'vreme': msg.get('clock', '-'),
                'ekipa': msg.get('teamName', '-'),
                'igralec': msg.get('playerName', 'Ekipa'),
                'akcija': msg.get('actionType', 'dogodek'),
                'tocke': int(msg.get('points', 0)) if msg.get('points') else 0
            }
            # Dodajanje v DataFrame
            st.session_state.db = pd.concat([st.session_state.db, pd.DataFrame([new_event])], ignore_index=True)

    def on_open(ws):
        sub_payload = {
            "command": "subscribe",
            "identifier": json.dumps({"channel": "ScoreChannel", "matchId": match_id})
        }
        ws.send(json.dumps(sub_payload))

    ws = websocket.WebSocketApp(
        "wss://zapisniki.kzs.si/cable",
        on_message=on_message,
        on_open=on_open
    )
    ws.run_forever()

# --- UPORABNIŠKI VMESNIK (UI) ---
st.title("🏀 KZS Advanced Live Stats")

# Sidebar za izbiro tekme
st.sidebar.header("Nadzorna plošča")
available_matches = get_active_matches()

if available_matches:
    selected_name = st.sidebar.selectbox("Izberi aktivno tekmo:", list(available_matches.keys()))
    m_id = available_matches[selected_name]
else:
    st.sidebar.warning("Ni zaznanih aktivnih tekem.")
    m_id = st.sidebar.text_input("Ročni vnos Match ID (npr. 123456):")

if st.sidebar.button("Poveži se v živo"):
    if m_id and not st.session_state.ws_active:
        thread = threading.Thread(target=run_websocket, args=(m_id,), daemon=True)
        thread.start()
        st.session_state.ws_active = True
        st.sidebar.success(f"Povezano na ID: {m_id}")

# --- DASHBOARD PRIKAZ ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Play-by-Play (V živo)")
    if not st.session_state.db.empty:
        # Prikažemo zadnjih 15 dogodkov (novejši zgoraj)
        st.table(st.session_state.db.iloc[::-1].head(15))
    else:
        st.info("Čakam na podatke... Izberi tekmo in klikni 'Poveži se'.")

with col2:
    st.subheader("Hitra Analitika")
    if not st.session_state.db.empty:
        # Seštevek točk po ekipah
        team_stats = st.session_state.db.groupby('ekipa')['tocke'].sum().reset_index()
        st.bar_chart(team_stats.set_index('ekipa'))
        
        # Najboljši strelci
        st.write("Najboljši strelci:")
        player_stats = st.session_state.db.groupby('igralec')['tocke'].sum().sort_values(ascending=False)
        st.dataframe(player_stats)

# Gumb za reset
if st.sidebar.button("Ponovi / Počisti"):
    st.session_state.db = pd.DataFrame(columns=['vreme', 'ekipa', 'igralec', 'akcija', 'tocke'])
    st.rerun()        }
        return new_row
    except Exception as e:
        return None

# --- WEBSOCKET FUNKCIJA ---
def run_v_ozadju(match_id):
    def on_message(ws, message):
        data = json.loads(message)
        if "message" in data:
            raw_event = data["message"]
            processed = process_kzs_message(raw_event)
            if processed:
                # Varno dodajanje v DataFrame (Streamlit session_state)
                st.session_state.db = pd.concat([st.session_state.db, pd.DataFrame([processed])], ignore_index=True)

    def on_error(ws, error):
        print(f"WS Napaka: {error}")

    def on_open(ws):
        # Naročnina na kanal ScoreChannel
        subscribe_msg = {
            "command": "subscribe",
            "identifier": json.dumps({"channel": "ScoreChannel", "matchId": match_id})
        }
        ws.send(json.dumps(subscribe_msg))

    ws = websocket.WebSocketApp(
        "wss://zapisniki.kzs.si/cable",
        on_open=on_open,
        on_message=on_message,
        on_error=on_error
    )
    ws.run_forever()

# --- UPORABNIŠKI VMESNIK (Sidebar) ---
st.sidebar.header("Nastavitve povezave")
m_id = st.sidebar.text_input("Vnesi Match ID (iz URL-ja KZS)", placeholder="npr. 123456")

if st.sidebar.button("Zaženi Live Stream"):
    if m_id and not st.session_state.ws_active:
        thread = threading.Thread(target=run_v_ozadju, args=(m_id,), daemon=True)
        thread.start()
        st.session_state.ws_active = True
        st.sidebar.success(f"Poslušam tekmo: {m_id}")
    elif st.session_state.ws_active:
        st.sidebar.warning("Povezava že teče.")

# --- PRIKAZ PODATKOV (Dashboard) ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Zadnji dogodki na tekmi")
    if not st.session_state.db.empty:
        # Obrnemo tabelo, da so najnovejši dogodki zgoraj
        st.dataframe(st.session_state.db.iloc[::-1], use_container_width=True)
    else:
        st.info("Čakam na prve dogodke s tekme...")

with col2:
    st.subheader("Analitika igralcev")
    if not st.session_state.db.empty:
        # Preprost graf točk po igralcih
        stats = st.session_state.db.groupby('igralec')['tocke'].sum().reset_index()
        st.bar_chart(stats.set_index('igralec'))
        
        # Izračun napredne metrike (Primer: Število akcij na igralca)
        st.write("Število vseh dogodkov:")
        st.write(st.session_state.db['igralec'].value_counts())

# --- GUMB ZA PONASTAVITEV ---
if st.sidebar.button("Počisti podatke"):
    st.session_state.db = pd.DataFrame(columns=['vreme', 'igralec', 'ekipa', 'akcija', 'tocke'])
    st.rerun()
