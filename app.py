import streamlit as st
import json
import asyncio
import websockets
import pandas as pd
import time

# Configuration de la page
st.set_page_config(page_title="Deriv Scalper Bot", layout="wide")
st.title("🤖 Robot de Scalping EURUSD - Deriv")

# --- BARRE LATÉRALE : CONFIGURATION ---
st.sidebar.header("🔐 Authentification")
# Zone de texte sécurisée pour le Token API
api_token = st.sidebar.text_input("Jeton API Deriv (API Token)", type="password", help="Collez ici votre jeton créé sur le site de Deriv")
# Zone pour l'App ID (Bloqué sur 1089 par défaut pour éviter les erreurs)
app_id = st.sidebar.text_input("App ID (Laissez 1089 pour les tests)", value="1089")

st.sidebar.divider()
st.sidebar.header("🔧 Paramètres de Trading")
symbol = "frxEURUSD"  # Code officiel de Deriv pour l'EUR/USD
stake_amount = st.sidebar.number_input("Montant du trade ($)", min_value=0.35, max_value=10.0, value=1.0, step=0.5)
duration = st.sidebar.number_input("Durée du Scalp (en ticks/secondes)", min_value=1, max_value=60, value=5)
duration_unit = st.sidebar.selectbox("Unité de temps", ["t", "s"], index=0) # t = ticks, s = secondes

# --- FONCTIONS REQUÊTES DERIV (ASYNC CORRIGÉE) ---
async def send_deriv_request(request):
    """Gère la connexion WebSocket sécurisée et l'envoi d'une requête à Deriv."""
    
    # 1. Nettoyage et validation de l'App ID
    clean_app_id = str(app_id).strip()
    if not clean_app_id or not clean_app_id.isdigit():
        clean_app_id = "1089"  # Sécurité : force l'identifiant par défaut si mauvaise saisie
        
    # L'adresse réseau (URI) correcte ne doit JAMAIS contenir le token secret
    uri = f"wss://://derivws.com{clean_app_id}"
    
    try:
        async with websockets.connect(uri) as websocket:
            # 2. Nettoyage du jeton API (supprime les espaces avant/après)
            clean_token = str(api_token).strip()
            
            # 3. Étape d'authentification obligatoire (Le token est envoyé DANS le message)
            auth_request = {"authorize": clean_token}
            await websocket.send(json.dumps(auth_request))
            auth_response = await websocket.recv()
            auth_data = json.loads(auth_response)
            
            if "error" in auth_data:
                return {"error": auth_data["error"]["message"]}
            
            # 4. Envoi de la requête de trading si l'authentification a réussi
            await websocket.send(json.dumps(request))
            response = await websocket.recv()
            return json.loads(response)
            
    except Exception as e:
        return {"error": f"Impossible de se connecter aux serveurs Deriv : {str(e)}"}

# --- INTERFACE PRINCIPALE ET LOGIQUE ---
if not api_token:
    st.warning("⚠️ Veuillez entrer votre Jeton API Deriv dans la barre latérale pour commencer.")
else:
    st.success("Configuration valide. Prêt à communiquer avec Deriv.")

    # Section 1 : Vérification du Solde du Compte
    if st.button("🔄 Vérifier le Solde du Compte"):
        with st.spinner("Connexion en cours..."):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            res = loop.run_until_complete(send_deriv_request({"balance": 1}))
            
            if "error" in res:
                st.error(f"Erreur Deriv : {res['error']}")
            else:
                balance = res["balance"]["balance"]
                currency = res["balance"]["currency"]
                st.metric(label="Solde Actuel de votre Compte", value=f"{balance} {currency}")

    st.divider()

    # Section 2 : Trading Manuel Instantané (Options Rise/Fall pour Scalping)
    st.subheader("⚡ Exécution Manuelle ultra-rapide")
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
                st.error(f"Échec de l'ordre : {res['error']}")
            else:
                st.success(f"✅ Contrat HAUSSE acheté ! ID: {res['buy']['contract_id']}")

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
                st.error(f"Échec de l'ordre : {res['error']}")
            else:
                st.success(f"✅ Contrat BAISSE acheté ! ID: {res['buy']['contract_id']}")

    st.divider()

    # Section 3 : Robot Automatique de Scalping Séquentiel
    st.subheader("📈 Stratégie Automatique (Mode Recherche)")
    bot_active = st.checkbox("Activer le Robot de Scalping Automatique")
    placeholder = st.empty()

    if bot_active:
        st.info("Le robot scanne activement le marché. Laissez cet onglet ouvert pour maintenir l'exécution.")
        
        while bot_active:
            loop = asyncio.new_event_loop()
            tick_res = loop.run_until_complete(send_deriv_request({"ticks": symbol}))
            
            if "tick" in tick_res:
                current_price = tick_res["tick"]["quote"]
                placeholder.metric("Prix EURUSD en Direct (Deriv)", f"{current_price}")
                
                # --- INSÉREZ VOTRE LOGIQUE DE TRADING ICI ---
                # Exemple générique : si vous souhaitez automatiser selon vos propres règles.
                
            else:
                if "error" in tick_res:
                    st.error(f"Erreur lors de la lecture des prix : {tick_res['error']}")
                    break
                    
            time.sleep(2) # Temporisation de 2 secondes pour respecter les limites de requêtes de l'API



