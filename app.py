import streamlit as st
import pandas as pd
import numpy as np
import time
import fxcmpy

# Configuration initiale de la page web
st.set_page_config(page_title="Robot Scalping FXCM Cloud", page_icon="📈", layout="wide")

# Initialisation des variables d'état si elles n'existent pas
if 'robot_actif' not in st.session_state:
    st.session_state.robot_actif = False
if 'logs' not in st.session_state:
    st.session_state.logs = ["Application prête. Veuillez configurer vos accès FXCM à gauche."]

st.title("🤖 Application Robot Scalping FXCM")
st.write("Entrez votre Token de trading FXCM, configurez vos réglages et lancez le robot.")
st.markdown("---")

# ==========================================
# BARRE LATÉRALE : ACCÈS & PARAMÈTRES FXCM
# ==========================================
st.sidebar.header("🔑 Authentification FXCM")

api_token_input = st.sidebar.text_input(
    "1. Token API FXCM", 
    type="password", 
    help="Votre jeton secret généré depuis le portail développeur ou le tableau de bord FXCM"
)

server_mode = st.sidebar.selectbox(
    "2. Environnement Serveur",
    options=["demo", "real"],
    index=0,
    help="Sélectionnez 'demo' pour tester sans risque ou 'real' pour le compte réel"
)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Configuration du Trade")

# Format FXCM standard : "EUR/USD", "GBP/USD", "USD/JPY"
symbol = st.sidebar.text_input("Paire Forex (Format FXCM)", value="EUR/USD")
lot_size = st.sidebar.number_input("Taille de la Position (K=1000)", min_value=1, max_value=100, value=1, step=1, help="Chez FXCM, 1 signifie 1 000 unités (1 micro-lot)")

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
    if st.button("▶️ ACTIVER LE ROBOT FXCM", use_container_width=True, type="primary"):
        if not api_token_input:
            st.error("⚠️ Erreur : Vous devez coller votre Token API FXCM à gauche.")
        else:
            st.session_state.robot_actif = True
            st.session_state.logs.append("🟢 Initialisation de la connexion FXCM...")

with col2:
    if st.button("⏹️ STOPPER LE ROBOT", use_container_width=True):
        st.session_state.robot_actif = False
        st.session_state.logs.append("🔴 Robot arrêté. Trading automatique désactivé.")

st.markdown("---")

# Conteneurs d'affichage fixes pour éviter les sauts d'écran
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
    # Utilisation des prix de clôture réels fournis par FXCM
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periode).mean()
    perte = (-delta.where(delta < 0, 0)).rolling(window=periode).mean()
    perte = perte.replace(0, 0.00001) # Éviter division par zéro
    rs = gain / perte
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])

# ==========================================
# MOTEUR DE TRADING EXÉCUTION FXCM
# ==========================================
def executer_scalping_fxcm(token, mode):
    con = None
    try:
        # 1. Connexion à l'API FXCM (Pas besoin d'asyncio, fxcmpy est synchrone)
        con = fxcmpy.fxcmpy(access_token=token, server=mode)
        
        if not con.is_connected():
            st.session_state.logs.append("⚠️ Échec d'authentification auprès des serveurs FXCM.")
            return

        # 2. Récupération des informations financières du compte
        accounts = con.get_accounts()
        if not accounts.empty:
            balance = accounts.iloc[0]['balance']
            equity = accounts.iloc[0]['equity']
            with placeholder_metrics.container():
                m1, m2 = st.columns(2)
                m1.metric("Solde Compte (Balance)", f"{balance:,.2f} USD")
                m2.metric("Équité Disponible (Equity)", f"{equity:,.2f} USD")

        # 3. Téléchargement des vraies dernières bougies (Historique M1 pour scalping)
        # Demande les 60 dernières bougies d'une minute
        candles = con.get_candles(symbol, period='m1', number=60)
        
        if not candles.empty:
            # Structurer les colonnes pour notre graphique et le calcul
            candles.columns = [c.lower() for c in candles.columns]
            
            with placeholder_chart.container():
                st.subheader(f"📈 Bougies 1 Minute (M1) en direct : {symbol}")
                st.line_chart(candles['close'])

            # 4. Calcul du RSI sur l'historique réel
            rsi_actuel = calculer_rsi_df(candles, rsi_periode)
            with placeholder_rsi.container():
                st.metric("RSI (Clôture M1)", f"{rsi_actuel:.2f}")

            # 5. Gestion des positions en cours
            positions = con.get_open_positions()
            # Filtrer les positions ouvertes sur le symbole configuré
            positions_actives = [] if positions.empty else positions[positions['currency'] == symbol]

            if len(positions_actives) == 0:
                placeholder_info.empty()
                
                # Signal d'Achat : RSI en survente
                if rsi_actuel < rsi_survente:
                    st.session_state.logs.append(f"🛒 Signal Achat FXCM ! RSI bas ({rsi_actuel:.2f})")
                    # Ouverture d'un ordre d'achat au marché
                    # FXCM gère le SL/TP en pips via des arguments dédiés si configuré, ici ordre simple au marché
                    con.open_trade(symbol=symbol, is_buy=True, amount=lot_size, time_in_force='GTC', order_type='AtMarket')
                
                # Signal de Vente : RSI en surachat
                elif rsi_actuel > rsi_surachat:
                    st.session_state.logs.append(f"📉 Signal Vente FXCM ! RSI haut ({rsi_actuel:.2f})")
                    con.open_trade(symbol=symbol, is_buy=False, amount=lot_size, time_in_force='GTC', order_type='AtMarket')
            else:
                with placeholder_info.container():
                    st.info(f"🛡️ Position FXCM active sur {symbol}. En attente du dénouement.")
        else:
            st.session_state.logs.append(f"⚠️ Impossible de récupérer les bougies pour {symbol}.")

    except Exception as e:
        st.session_state.logs.append(f"⚠️ Erreur FXCM API : {str(e)}")
    
    finally:
        # Clôture propre de la session d'API pour éviter les connexions fantômes saturées
        if con is not None and con.is_connected():
            con.close()

# Boucle principale d'exécution Streamlit
if st.session_state.robot_actif:
    executer_scalping_fxcm(api_token_input, server_mode)

# ==========================================
# JOURNAL DE BORD (LOGS)
# ==========================================
st.subheader("📋 Journal des actions du Robot")
for log in list(reversed(st.session_state.logs))[:5]:
    st.text(log)

# Rafraîchissement automatique toutes les 5 secondes (adapté au format M1 de FXCM)
if st.session_state.get('robot_actif', False):
    time.sleep(5)
    st.rerun()
