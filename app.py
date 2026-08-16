import streamlit as st
import json
import asyncio
import websockets
import pandas as pd
import time

# Configuration de la page Streamlit
st.set_page_config(page_title="Deriv Scalper Bot", layout="wide")
st.title("🤖 Robot de Scalping EURUSD - Deriv")

# --- BARRE LATÉRALE : CONFIGURATION ---
st.sidebar.header("🔐 Authentification")

# Zone de texte sécurisée pour insérer votre jeton de compte (Démo ou Réel)
api_token = st.sidebar.text_input(
    "Jeton API Deriv (API Token)", 
    type="password", 
    help="Collez ici le jeton (Token) généré depuis les paramètres de votre compte Deriv."
)

st.sidebar.divider()
st.sidebar.header("🔧 Paramètres de Trading")
symbol = "frxEURUSD"  # Code officiel Deriv pour l'EUR/USD
stake_amount = st.sidebar.number_input("Montant du trade ($)", min_value=0.35, max_value=10.0, value=1.0, step=0.5)
duration = st.sidebar.number_input("Durée du Scalp", min_value=1, max_value=60, value=5)
duration_unit = st.sidebar.selectbox("Unité de temps", ["t", "s"], index=0) # t = ticks, s = secondes

# --- FONCTION DE CONNEXION DIRECTE (CORRIGÉE ET FIABLE) ---
async def send_deriv_request(request):
    """Gère la connexion WebSocket et l'envoi d'une requête à Deriv."""
    
    # URL brute et immuable pour éliminer définitivement l'erreur "hostname isn't provided"
    uri = "wss://://derivws.com"
    
    try:
        async with websockets.connect(uri) as websocket:
            # Nettoyage automatique des espaces autour du jeton inséré
            clean_token = str(api_token).strip()
            
            # Étape 1 : Authentification du compte via le Jeton
            auth_request = {"authorize": clean_token}
            await websocket.send(json.dumps(auth_request))
            auth_response = await websocket.recv()
            auth_data = json.loads(auth_response)
            
            if "error" in auth_data:
                return {"error": auth_data["error"]["message"]}
            
            # Étape 2 : Envoi de l'ordre de trading si l'authentification est validée
            await websocket.send(json.dumps(request))
            response = await websocket.recv()
            return json.loads(response)
            
    except Exception as e:
        return {"error": f"Erreur réseau : {str(e)}"}

# --- APPLICATION PRINCIPALE ---
if not api_token:
    st.warning("⚠️ En attente de votre Jeton API Deriv dans la barre latérale pour activer l'application.")
else:
    st.success("Structure prête. Prêt à envoyer les ordres à Deriv.")

    # Bouton de synchronisation du compte
    if st.button("🔄 Vérifier le Solde du Compte"):
        with st.spinner("Interrogation des serveurs de Deriv..."):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            res = loop.run_until_complete(send_deriv_request({"balance": 1}))
            
            if "error" in res:
                st.error(f"Réponse Deriv : {res['error']}")
            else:
                balance = res["balance"]["balance"]
                currency = res["balance"]["currency"]
                st.metric(label="Solde disponible sur ce compte", value=f"{balance} {currency}")

    st.divider()

    # Section Trading Instantané (Idéal pour scalper manuellement sur les micro-mouvements)
    st.subheader("⚡ Exécution Manuelle instantanée (Options Rise/Fall)")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("🟢 ACHETER (HAUSSE / RISE)", use_container_width=True, type="primary"):
            req = {
                "buy": 1,
                "price": stake_amount,
                "parameters": {
                    "amount": stake_amount,
                    "basis": "stake",
                    "contract_type": "CALL",
                    "currency": "USD",
                    "duration": int(duration),
                    "duration_unit": duration_unit,
                    "symbol": symbol
                }
            }
            loop = asyncio.new_event_loop()
            res = loop.run_until_complete(send_deriv_request(req))
            if "error" in res:
                st.error(f"Refus de l'ordre : {res['error']}")
            else:
                st.success(f"✅ Position Hausse ouverte ! ID Contrat : {res['buy']['contract_id']}")

    with col2:
        if st.button("🔴 VENDRE (BAISSE / FALL)", use_container_width=True, type="secondary"):
            req = {
                "buy": 1,
                "price": stake_amount,
                "parameters": {
                    "amount": stake_amount,
                    "basis": "stake",
                    "contract_type": "PUT",
                    "currency": "USD",
                    "duration": int(duration),
                    "duration_unit": duration_unit,
                    "symbol": symbol
                }
            }
            loop = asyncio.new_event_loop()
            res = loop.run_until_complete(send_deriv_request(req))
            if "error" in res:
                st.error(f"Refus de l'ordre : {res['error']}")
            else:
                st.success(f"✅ Position Baisse ouverte ! ID Contrat : {res['buy']['contract_id']}")

    st.divider()

    # Section Visualisation du Flux Automatique
    st.subheader("📈 Suivi du Flux en Temps Réel")
    bot_active = st.checkbox("Activer la lecture des prix du Marché")
    placeholder = st.empty()

    if bot_active:
        st.info("Flux en cours d'analyse. Gardez cet onglet actif.")
        
        while bot_active:
            loop = asyncio.new_event_loop()
            tick_res = loop.run_until_complete(send_deriv_request({"ticks": symbol}))
            
            if "tick" in tick_res:
                current_price = tick_res["tick"]["quote"]
                placeholder.metric("Dernier prix EURUSD reçu", f"{current_price} USD")
            else:
                if "error" in tick_res:
                    st.error(f"Interruption du flux : {tick_res['error']}")
                    break
                    
            time.sleep(2) # Intervalle de sécurité de 2 secondes




