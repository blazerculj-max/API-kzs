import streamlit as st
import websocket
import json
import pandas as pd
import threading
from streamlit_autorefresh import st_autorefresh

# --- KONFIGURACIJA ---
st.set_page_config(page_title="KZS Live Advanced Stats", layout="wide")

# Avtomatsko osveževanje vmesnika vsakih 5 sekund
st_autorefresh(interval=5000, key="datarefresh")

st.title("🏀 KZS Live Analytics")
st.markdown("Spremljanje slovenske košarkarske lige v realnem času.")

# --- SHRAMBA PODATKOV (Session State) ---
if 'db' not in st.session_state:
    # Ustvarimo tabelo za hrambo vseh dogodkov
    st.session_state.db = pd.DataFrame(columns=['vreme', 'igralec', 'ekipa', 'akcija', 'tocke'])

if 'ws_active' not in st.session_state:
    st.session_state.ws_active = False

# --- LOGIKA ZA OBDELAVO DOGODKOV ---
def process_kzs_message(msg):
    """Pretvori surovo sporočilo KZS v vrstico za našo tabelo."""
    try:
        # Pozor: Struktura JSON-a se lahko razlikuje glede na tip dogodka (met, favl, skok)
        # Tukaj implementiraš svojo logiko mapiranja
        new_row = {
            'vreme': msg.get('clock', '00:00'),
            'igralec': msg.get('playerName', 'Neznano'),
            'ekipa': msg.get('teamName', '-'),
            'akcija': msg.get('actionType', 'dogodek'),
            'tocke': int(msg.get('points', 0))
        }
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
