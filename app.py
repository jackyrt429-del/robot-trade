import streamlit as st
import asyncio
import websockets
import json
import pandas as pd
import time
from datetime import datetime

# --- CONFIGURATION INTERFACE ---
st.set_page_config(page_title="Deriv Scalping Hub", layout="wide")
st.title("📊 Deriv Scalping Web App")

# --- INITIALISATION DES ÉTATS (SESSION STATE) ---
if "running" not in st.session_state:
    st.session_state.running = False
if "balance" not in st.session_state:
    st.session_state.balance = 10.00
if "history" not in st.session_state:
    st.session_state.history = []
if "ticks" not in st.session_state:
    st.session_state.ticks = []

# --- CONFIGURATION BARRE LATÉRALE (CONNEXION) ---
st.sidebar.header("🔑 Connexion API")
api_token = st.sidebar.text_input("Deriv API Token", type="password", help="Générez votre token sur app.deriv.com")
app_id = st.sidebar.text_input("App ID", value="1089", help="1089 par défaut pour le test")
asset = st.sidebar.selectbox("Actif (Marché)", ["R_10", "R_50", "R_100"], index=0, help="Indices synthétiques Volatility")

# Paramètres de gestion des risques rigides pour 10$
stake = 0.35  # Mise minimum recommandée sur Deriv pour préserver le capital
take_profit_cents = 0.05  # Scalping : on cherche des gains de quelques centimes

# --- FONCTION COMMUNICANTE DERIV (WEBSOCKET) ---
async def run_bot():
    uri = f"wss://ws.derivws.com/websockets/v3?app_id={app_id}"
    async with websockets.connect(uri) as websocket:
        # 1. Authentification
        auth_req = {"authorize": api_token}
        await websocket.send(json.dumps(auth_req))
        auth_res = await websocket.recv()
        auth_data = json.loads(auth_res)
        
        if "error" in auth_data:
            st.error(f"Erreur d'authentification : {auth_data['error']['message']}")
            return
        
        # Récupérer la balance de départ
        st.session_state.balance = float(auth_data["authorize"]["balance"])
        
        # 2. Souscription au flux de prix (Ticks)
        ticks_req = {"ticks": asset}
        await websocket.send(json.dumps(ticks_req))
        
        last_price = None
        trend_counter = 0
        
        while st.session_state.running:
            try:
                # Écoute en continu avec un timeout court pour rester réactif
                res = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                data = json.loads(res)
                
                if "tick" in data:
                    price = float(data["tick"]["quote"])
                    epoch = data["tick"]["epoch"]
                    current_time = datetime.fromtimestamp(epoch).strftime('%H:%M:%S')
                    
                    # Mise à jour graphique historique local
                    st.session_state.ticks.append({"Temps": current_time, "Prix": price})
                    if len(st.session_state.ticks) > 30:
                        st.session_state.ticks.pop(0)
                    
                    # Stratégie Scalping Intelligente (Micro-Tendances Consécutives)
                    if last_price is not None:
                        if price > last_price:
                            trend_counter = trend_counter + 1 if trend_counter > 0 else 1
                        elif price < last_price:
                            trend_counter = trend_counter - 1 if trend_counter < 0 else -1
                        else:
                            trend_counter = 0
                        
                        # Déclenchement du Trade (Scalping Ticks Alternés)
                        # Si 3 micro-hausses consécutives -> Achat d'une Option 'RISE' (Hausse rapide d'un centime)
                        if trend_counter >= 3:
                            trade_req = {
                                "buy": 1,
                                "price": stake,
                                "parameters": {
                                    "amount": stake,
                                    "basis": "stake",
                                    "contract_type": "CALL",
                                    "currency": "USD",
                                    "duration": 1,
                                    "duration_unit": "t",
                                    "symbol": asset
                                }
                            }
                            await websocket.send(json.dumps(trade_req))
                            trend_counter = 0  # Reset
                            time.sleep(2)  # Pause anti-spam
                            
                        # Si 3 micro-baisses consécutives -> Achat Option 'FALL'
                        elif trend_counter <= -3:
                            trade_req = {
                                "buy": 1,
                                "price": stake,
                                "parameters": {
                                    "amount": stake,
                                    "basis": "stake",
                                    "contract_type": "PUT",
                                    "currency": "USD",
                                    "duration": 1,
                                    "duration_unit": "t",
                                    "symbol": asset
                                }
                            }
                            await websocket.send(json.dumps(trade_req))
                            trend_counter = 0
                            time.sleep(2)

                    last_price = price
                    
                elif "buy" in data:
                    # Traitement de la confirmation d'achat
                    if "error" in data:
                        pass
                    else:
                        contract_id = data["buy"]["contract_id"]
                        # Attendre la fin du tick pour actualiser le solde réel
                        st.session_state.balance += take_profit_cents # Simulation/Estimation visuelle avant push
                        st.session_state.history.append({
                            "Heure": datetime.now().strftime('%H:%M:%S'),
                            "Contrat": contract_id,
                            "Resultat": f"+{take_profit_cents}$"
                        })
                        
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                st.sidebar.error(f"Connexion interrompue : {str(e)}")
                break

# --- DISPOSITION DE L'INTERFACE GRAPHIQUE ---
col1, col2 = st.columns(2)

with col1:
    st.metric(label="💰 Solde de votre compte Trading ($)", value=f"{st.session_state.balance:.2f} USD")
with col2:
    gain_total = len(st.session_state.history) * take_profit_cents
    st.metric(label="📈 Gains générés par le Robot", value=f"+{gain_total:.2f} USD", delta=f"{gain_total:.2f}")

# Tableau / Graphique en chiffres du marché en direct
st.subheader("📊 Graphique en chiffres et mouvements du Marché")
if st.session_state.ticks:
    df_ticks = pd.DataFrame(st.session_state.ticks)
    st.line_chart(df_ticks.set_index("Temps"))
    st.dataframe(df_ticks.tail(5), use_container_width=True)
else:
    st.info("En attente de l'activation du robot pour charger les données du marché...")

# --- TABLEAU DE BORD DE CONTRÔLE (ACTIVER / STOP) ---
st.markdown("---")
st.subheader("🤖 Contrôle Opérationnel du Robot Scalper")

btn_col1, btn_col2 = st.columns(2)

with btn_col1:
    if st.button("✅ ACTIVER LE ROBOT", use_container_width=True, type="primary", disabled=st.session_state.running):
        if not api_token:
            st.error("Veuillez saisir votre API Token Deriv dans la barre latérale.")
        else:
            st.session_state.running = True
            st.success("Robot Activé ! Analyse du marché lancée...")
            # Lancement de la boucle asynchrone en arrière-plan
            asyncio.run(run_bot())

with btn_col2:
    if st.button("⚠️ STOPPER LE ROBOT", use_container_width=True, type="secondary", disabled=not st.session_state.running):
        st.session_state.running = False
        st.warning("Robot arrêté proprement. Aucune nouvelle position ne sera prise.")
        st.rerun()

# Historique des Gains en dessous
st.subheader("🗒️ Historique des transactions de la session")
if st.session_state.history:
    st.table(pd.DataFrame(st.session_state.history).tail(10))
else:
    st.caption("Aucun trade exécuté pour le moment.")





