import streamlit as st
import pandas as pd
import numpy as np
import time
import asyncio
from ib_async import IB, Forex, MarketOrder

# Configuration initiale de la page web
st.set_page_config(page_title="Robot Scalping IBKR Cloud", page_icon="🏦", layout="wide")

# Initialisation des variables d'état si elles n'existent pas
if 'robot_actif' not in st.session_state:
    st.session_state.robot_actif = False
if 'logs' not in st.session_state:
    st.session_state.logs = ["Application prête. Veuillez configurer vos accès IBKR à gauche."]
if 'ibkr_instance' not in st.session_state:
    st.session_state.ibkr_instance = None

st.title("🤖 Application Robot Scalping Interactive Brokers")
st.write("Connectez votre passerelle IBKR Client Portal, configurez vos réglages et lancez le robot.")
st.markdown("---")

# ==========================================
# BARRE LATÉRALE : ACCÈS & PARAMÈTRES IBKR
# ==========================================
st.sidebar.header("🔑 Connexion Passerelle IBKR")

# L'API Web d'IBKR s'appuie sur une passerelle locale ou un jeton d'hôte
gateway_host = st.sidebar.text_input("1. Hôte Passerelle API", value="localhost", help="L'adresse IP de votre passerelle Client Portal ou serveur hôte")
gateway_port = st.sidebar.number_input("2. Port API", value=5000, step=1, help="Le port configuré sur votre passerelle (par défaut 5000 pour Client Portal)")
client_id = st.sidebar.number_input("3. Client ID unique", value=1, step=1)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Configuration du Trade")

# Format IBKR standard pour le Forex
base_currency = st.sidebar.text_input("Devise de Base", value="EUR")
quote_currency = st.sidebar.text_input("Devise de Contrepartie", value="USD")
lot_size = st.sidebar.number_input("Taille de la Position (Unités)", min_value=1000, max_value=100000, value=10000, step=1000, help="10 000 unités correspondent à 0.1 lot standard (un mini-lot)")

st.sidebar.markdown("---")
st.sidebar.header("📈 Réglages du RSI")
rsi_periode = st.sidebar.slider("Période RSI (Bougies)", 5, 21, 14)
rsi_surachat = st.sidebar.slider("Zone Vente (Surachat)", 70, 90, 70)
rsi_survente = st.sidebar.slider("Zone Achat (Survente)", 10, 30, 30)

# ==========================================
# ZONE DE CONTRÔLE (BOUTONS ON/OFF)
# ==========================================
col1, col2 = st.columns(2)

with col1:
    if st.button("▶️ ACTIVER LE ROBOT IBKR", use_container_width=True, type="primary"):
        st.session_state.robot_actif = True
        st.session_state.logs.append("🟢 Initialisation de la session Interactive Brokers...")

with col2:
    if st.button("⏹️ STOPPER LE ROBOT", use_container_width=True):
        st.session_state.robot_actif = False
        st.session_state.logs.append("🔴 Robot arrêté. Déconnexion d'IBKR.")
        if st.session_state.ibkr_instance and st.session_state.ibkr_instance.isConnected():
            try:
                st.session_state.ibkr_instance.disconnect()
            except:
                pass
        st.session_state.ibkr_instance = None

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
# MOTEUR DE TRADING ASYNCHRONE IBKR
# ==========================================
async def executer_scalping_ibkr():
    try:
        # 1. Gestion de la connexion persistante via ib_async
        if st.session_state.ibkr_instance is None or not st.session_state.ibkr_instance.isConnected():
            st.session_state.logs.append("🔌 Connexion à la passerelle IBKR...")
            ib = IB()
            # Utilisation de la méthode de connexion appropriée pour la passerelle
            await ib.connectAsync(gateway_host, gateway_port, clientId=client_id)
            st.session_state.ibkr_instance = ib
        
        ib = st.session_state.ibkr_instance

        # 2. Récupération des informations financières du compte
        account_summary = ib.accountSummary()
        balance = 0.0
        equity = 0.0
        for item in account_summary:
            if item.tag == 'CashBalance' and item.currency == 'USD':
                balance = float(item.value)
            if item.tag == 'NetLiquidation' and item.currency == 'USD':
                equity = float(item.value)

        with placeholder_metrics.container():
            m1, m2 = st.columns(2)
            m1.metric("Solde Cash (USD)", f"{balance:,.2f} USD")
            m2.metric("Valeur Liquidative (Equity)", f"{equity:,.2f} USD")

        # Definition du contrat Forex IBKR
        contract = Forex(f"{base_currency}{quote_currency}")
        qualify = ib.qualifyContracts(contract)

        # 3. Récupération des bougies historiques (Données de scalping 1 min)
        bars = await ib.reqHistoricalDataAsync(
            contract, endDateTime='', durationStr='60 D',
            barSizeSetting='1 min', whatToShow='MIDPOINT', useRTH=True
        )

        if bars:
            df_candles = pd.DataFrame([{
                'date': b.date, 'open': b.open, 'high': b.high, 
                'low': b.low, 'close': b.close, 'volume': b.volume
            } for b in bars])
            
            with placeholder_chart.container():
                st.subheader(f"📈 Bougies 1 Minute (M1) en direct : {base_currency}/{quote_currency}")
                st.line_chart(df_candles.set_index('date')['close'])

            # 4. Calcul du RSI
            rsi_actuel = calculer_rsi_df(df_candles, rsi_periode)
            with placeholder_rsi.container():
                st.metric("RSI (Clôture M1)", f"{rsi_actuel:.2f}")

            # 5. Gestion des positions
            positions = ib.positions()
            positions_actives = [p for p in positions if p.contract.localSymbol == f"{base_currency}.{quote_currency}"]

            if len(positions_actives) == 0:
                placeholder_info.empty()
                
                # Signal d'Achat : RSI en survente
                if rsi_actuel < rsi_survente:
                    st.session_state.logs.append(f"🛒 Signal Achat IBKR ! RSI bas ({rsi_actuel:.2f})")
                    order = MarketOrder('BUY', lot_size)
                    trade = ib.placeOrder(contract, order)
                
                # Signal de Vente : RSI en surachat
                elif rsi_actuel > rsi_surachat:
                    st.session_state.logs.append(f"📉 Signal Vente IBKR ! RSI haut ({rsi_actuel:.2f})")
                    order = MarketOrder('SELL', lot_size)
                    trade = ib.placeOrder(contract, order)
            else:
                with placeholder_info.container():
                    st.info(f"🛡️ Position IBKR active sur {base_currency}/{quote_currency}. En attente du dénouement.")
        else:
            st.session_state.logs.append("⚠️ Impossible de charger les bougies depuis IBKR.")

    except Exception as e:
        st.session_state.logs.append(f"⚠️ Erreur IBKR API : {str(e)}")
        st.session_state.ibkr_instance = None

# Gestion de la boucle asynchrone requise pour ib_async dans Streamlit
if st.session_state.robot_actif:
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    loop.run_until_complete(executer_scalping_ibkr())

# ==========================================
# JOURNAL DE BORD (LOGS)
# ==========================================
st.subheader("📋 Journal des actions du Robot")
for log in list(reversed(st.session_state.logs))[:5]:
    st.text(log)

# Rafraîchissement automatique toutes les 5 secondes
if st.session_state.get('robot_actif', False):
    time.sleep(5)
    st.rerun()

