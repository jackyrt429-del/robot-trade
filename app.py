import streamlit as st
import pandas as pd
import numpy as np
import time
import asyncio
import json
import websockets

# Configuration initiale de la page web
st.set_page_config(page_title="Robot Scalping Deriv Cloud", page_icon="🤖", layout="wide")

# Initialisation des variables d'état si elles n'existent pas
if 'robot_actif' not in st.session_state:
    st.session_state.robot_actif = False
if 'logs' not in st.session_state:
    st.session_state.logs = ["Application prête. Veuillez configurer vos accès Deriv à gauche."]
if 'deriv_auth' not in st.session_state:
    st.session_state.deriv_auth = False

st.title("🤖 Application Robot Scalping Deriv API")
st.write("Connectez votre compte Deriv via Token API, configurez vos réglages et lancez le robot.")
st.markdown("---")

# ==========================================
# BARRE LATÉRALE : ACCÈS & PARAMÈTRES DERIV
# ==========================================
st.sidebar.header("🔑 Connexion API Deriv")

# Deriv utilise un système d'App ID et de Token API
app_id = st.sidebar.text_input("1. Application ID (App ID)", value="1089", help="Par défaut 1089 pour les tests, ou créez la vôtre sur votre portail Deriv.")
api_token = st.sidebar.text_input("2. API Token", value="", type="password", help="Générez un token avec les droits 'Read' et 'Trade' dans vos paramètres Deriv.")

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Configuration du Trade")

# Actifs Deriv standard (ex: frxEURUSD pour l'EUR/USD ou R_100 pour l'indice synthétique Volatility 100)
symbol = st.sidebar.text_input("Symbole de l'Actif", value="frxEURUSD", help="Exemples : 'frxEURUSD' (Forex) ou 'R_100' (Indice de Volatilité 100)")
lot_size = st.sidebar.number_input("Montant de la mise (Stake / USD)", min_value=1.0, max_value=1000.0, value=10.0, step=1.0, help="Le montant investi par position (contrat option)")
contract_duration = st.sidebar.number_input("Durée du contrat (Ticks)", min_value=5, max_value=60, value=5, step=1, help="Nombre de mouvements (ticks) avant expiration de l'option")

st.sidebar.markdown("---")
st.sidebar.header("📈 Réglages du RSI")
rsi_periode = st.sidebar.slider("Période RSI (Bougies)", 5, 21, 14)
rsi_surachat = st.sidebar.slider("Zone Vente (Surachat)", 70, 90, 70)
rsi_survente = st.sidebar.slider("Zone Achat (Survente)", 10, 30, 30)

# URL WebSocket Deriv de production / démo globale
DERIV_WS_URL = f"wss://://derivws.com{app_id}"

# ==========================================
# ZONE DE CONTRÔLE (BOUTONS ON/OFF)
# ==========================================
col1, col2 = st.columns(2)

with col1:
    if st.button("▶️ ACTIVER LE ROBOT DERIV", use_container_width=True, type="primary"):
        if not api_token:
            st.error("⚠️ Veuillez renseigner votre API Token Deriv à gauche avant de lancer le robot.")
        else:
            st.session_state.robot_actif = True
            st.session_state.logs.append("🟢 Initialisation de la session Deriv WebSocket...")

with col2:
    if st.button("⏹️ STOPPER LE ROBOT", use_container_width=True):
        st.session_state.robot_actif = False
        st.session_state.deriv_auth = False
        st.session_state.logs.append("🔴 Robot arrêté. Déconnexion de l'API Deriv.")

st.markdown("---")

# Conteneurs d'affichage fixes
placeholder_metrics = st.empty()
placeholder_chart = st.empty()
placeholder_rsi = st.empty()
placeholder_info = st.empty()

# ==========================================
# FONCTION TECHNIQUE DU CALCUL RSI
# ==========================================
def calculer_rsi_df(df, periode):
    if len(df) < periode + 1:
        return 50.0
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periode).mean()
    perte = (-delta.where(delta < 0, 0)).rolling(window=periode).mean()
    perte = perte.replace(0, 0.00001)
    rs = gain / perte
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])

# ==========================================
# MOTEUR DE TRADING ASYNCHRONE WEBSOCKET DERIV
# ==========================================
async def executer_scalping_deriv():
    try:
        async with websockets.connect(DERIV_WS_URL) as ws:
            # 1. Authentification obligatoire à chaque ouverture de flux
            auth_request = {"authorize": api_token}
            await ws.send(json.dumps(auth_request))
            auth_res = json.loads(await ws.recv())

            if "error" in auth_res:
                st.session_state.logs.append(f"❌ Échec Authentification : {auth_res['error']['message']}")
                st.session_state.robot_actif = False
                return

            st.session_state.deriv_auth = True
            
            # Récupération du solde et de l'identifiant du compte
            balance = float(auth_res["authorize"]["balance"])
            currency = auth_res["authorize"]["currency"]
            account_id = auth_res["authorize"]["loginid"]

            with placeholder_metrics.container():
                m1, m2 = st.columns(2)
                m1.metric("Compte Deriv ID", account_id)
                m2.metric(f"Solde Actuel ({currency})", f"{balance:,.2f} {currency}")

            # 2. Récupération des bougies historiques (Historique équivalent à 1 minute M1)
            # Demande 100 bougies historiques de 1 minute (60 secondes)
            ticks_history_request = {
                "ticks_history": symbol,
                "adjust_start_time": 1,
                "count": 100,
                "end": "latest",
                "style": "candles",
                "granularity": 60
            }
            await ws.send(json.dumps(ticks_history_request))
            history_res = json.loads(await ws.recv())

            if "error" in history_res:
                st.session_state.logs.append(f"⚠️ Erreur Données Historiques : {history_res['error']['message']}")
                return

            candles = history_res.get("candles", [])
            if candles:
                df_candles = pd.DataFrame(candles)
                # Conversion du format epoch unix vers datetime
                df_candles['date'] = pd.to_datetime(df_candles['epoch'], unit='s')
                
                with placeholder_chart.container():
                    st.subheader(f"📈 Bougies 1 Minute (M1) en direct sur Deriv : {symbol}")
                    st.line_chart(df_candles.set_index('date')['close'])

                # 3. Calcul du RSI
                rsi_actuel = calculer_rsi_df(df_candles, rsi_periode)
                with placeholder_rsi.container():
                    st.metric("RSI (Clôture M1)", f"{rsi_actuel:.2f}")

                # 4. Prise de décision de Scalping (Options Numériques Rise / Fall)
                # Remarque : L'exécution d'options sur Deriv est instantanée et n'a pas besoin de suivi de position complexe comme le Forex IBKR
                
                # Signal d'Achat (Rise / CALL) : RSI en survente
                if rsi_actuel < rsi_survente:
                    st.session_state.logs.append(f"🛒 Signal Achat Deriv (RISE) ! RSI bas ({rsi_actuel:.2f})")
                    buy_request = {
                        "buy": 1,
                        "price": lot_size,
                        "parameters": {
                            "amount": lot_size,
                            "basis": "stake",
                            "contract_type": "CALL",
                            "currency": currency,
                            "duration": contract_duration,
                            "duration_unit": "t",
                            "symbol": symbol
                        }
                    }
                    await ws.send(json.dumps(buy_request))
                    order_res = json.loads(await ws.recv())
                    
                    if "error" in order_res:
                        st.session_state.logs.append(f"❌ Erreur Ordre : {order_res['error']['message']}")
                    else:
                        st.session_state.logs.append(f"✅ Contrat CALL acheté ! ID: {order_res['buy']['contract_id']}")

                # Signal de Vente (Fall / PUT) : RSI en surachat
                elif rsi_actuel > rsi_surachat:
                    st.session_state.logs.append(f"📉 Signal Vente Deriv (FALL) ! RSI haut ({rsi_actuel:.2f})")
                    buy_request = {
                        "buy": 1,
                        "price": lot_size,
                        "parameters": {
                            "amount": lot_size,
                            "basis": "stake",
                            "contract_type": "PUT",
                            "currency": currency,
                            "duration": contract_duration,
                            "duration_unit": "t",
                            "symbol": symbol
                        }
                    }
                    await ws.send(json.dumps(buy_request))
                    order_res = json.loads(await ws.recv())
                    
                    if "error" in order_res:
                        st.session_state.logs.append(f"❌ Erreur Ordre : {order_res['error']['message']}")
                    else:
                        st.session_state.logs.append(f"✅ Contrat PUT acheté ! ID: {order_res['buy']['contract_id']}")
                else:
                    with placeholder_info.container():
                        st.info(f"⚡ RSI stable ({rsi_actuel:.2f}). Analyse du marché en cours...")
            else:
                st.session_state.logs.append("⚠️ Impossible de charger les bougies depuis Deriv.")

    except Exception as e:
        st.session_state.logs.append(f"⚠️ Erreur Deriv API Connection : {str(e)}")

# Gestion de la boucle asynchrone pour l'exécution dans Streamlit
if st.session_state.robot_actif:
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        


