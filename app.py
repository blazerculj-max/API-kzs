import streamlit as st
import websocket
import json
import pandas as pd
import threading
import requests
from streamlit_autorefresh import st_autorefresh

# --- KONFIGURACIJA STRANI ---
st.set_page_config(page_title="KZS Live Advanced Stats", layout="wide", page_icon="🏀")

# Avtomatsko osveževanje vmesnika na 5 sekund
st_autorefresh(interval=5000, key="datarefresh")

# --- FUNKCIJA ZA ISKANJE TEKEM ---
def get_active_matches():
    """Pridobi seznam trenutnih tekem s KZS preko njihovega API-ja."""
    try:
        # Poskusimo dostopati do seznama aktivnih tekem
        res = requests.get("https://zapisniki.kzs.si/api/v1/matches/active", timeout=5)
        if res.status_code == 200:
            data = res.json()
            # Ustvarimo slovar {Ime tekme: ID}
            return {f"{m.get('homeTeam', {}).get('name', 'Domači')} vs {m.get('awayTeam', {}).get('name', 'Gosti')}": m['id'] for m in data}
        return {}
    except Exception:
        return {}

# --- SHRAMBA PODATKOV (Session State) ---
if 'db' not in st.session_state:
    st.session_state.db = pd.DataFrame(columns=['vreme', 'ekipa', 'igralec', 'akcija', 'tocke'])

if 'ws_active' not in st.session_state:
    st.session_state.ws_active = False

# --- LOGIKA ZA WEBSOCKET ---
def run_websocket(match_id):
    def on_message(ws, message):
        try:
            data = json.loads(message)
            if "message" in data:
                msg = data["message"]
                
                # Ekstrakcija podatkov (prilagojeno KZS formatu)
                new_event = {
                    'vreme': msg.get('clock', '-'),
                    'ekipa': msg.get('teamName', '-'),
                    'igralec': msg.get('playerName', 'Ekipa'),
                    'akcija': msg.get('actionType', 'dogodek'),
                    'tocke': int(msg.get('points', 0)) if msg.get('points') else 0
                }
                
                # Dodajanje v DataFrame v session_state
                st.session_state.db = pd.concat([st.session_state.db, pd.DataFrame([new_event])], ignore_index=True)
        except Exception as e:
            print(f"Napaka pri obdelavi sporočila: {e}")

    def on_open(ws):
        # Naročnina na ScoreChannel za specifičen match_id
        sub_payload = {
            "command": "subscribe",
            "identifier": json.dumps({"channel": "ScoreChannel", "matchId": str(match_id)})
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

m_id = None
if available_matches:
    selected_name = st.sidebar.selectbox("Izberi aktivno tekmo:", list(available_matches.keys()))
    m_id = available_matches[selected_name]
else:
    st.sidebar.info("Ni zaznanih aktivnih tekem preko API-ja.")
    m_id = st.sidebar.text_input("Ročni vnos Match ID (npr. 123456):")

if st.sidebar.button("Poveži se v živo"):
    if m_id and not st.session_state.ws_active:
        # Zaženemo v ozadju
        thread = threading.Thread(target=run_websocket, args=(m_id,), daemon=True)
        thread.start()
        st.session_state.ws_active = True
        st.sidebar.success(f"Povezano na tekmo: {m_id}")
    elif st.session_state.ws_active:
        st.sidebar.warning("Povezava že teče.")

# --- DASHBOARD PRIKAZ ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Dogodki v živo (Play-by-Play)")
    if not st.session_state.db.empty:
        # Prikažemo zadnjih 15 dogodkov, najnovejši zgoraj
        st.table(st.session_state.db.iloc[::-1].head(15))
    else:
        st.info("Čakam na podatke... Izberi tekmo in klikni gumb 'Poveži se'.")

with col2:
    st.subheader("Analitika")
    if not st.session_state.db.empty:
        # Seštevek točk po ekipah
        team_stats = st.session_state.db.groupby('ekipa')['tocke'].sum().reset_index()
        st.bar_chart(team_stats.set_index('ekipa'))
        
        # Najboljši strelci
        st.write("Točke po igralcih:")
        player_stats = st.session_state.db.groupby('igralec')['tocke'].sum().sort_values(ascending=False)
        st.dataframe(player_stats)

# Gumb za resetiranje podatkov
if st.sidebar.button("Ponastavi podatke"):
    st.session_state.db = pd.DataFrame(columns=['vreme', 'ekipa', 'igralec', 'akcija', 'tocke'])
    st.rerun()
