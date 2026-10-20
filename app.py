import streamlit as st
import pandas as pd
import json
import os
import random

# ==========================================
# CONFIGURACIÓN DE LA PÁGINA
# ==========================================
st.set_page_config(
    page_title="OPTCG Swiss Tournament Manager",
    page_icon="🏴‍☠️",
    layout="wide"
)

DB_FILE = "tournament_db.json"

# ==========================================
# BASE DE DATOS Y PERSISTENCIA (JSON)
# ==========================================
def load_db():
    if not os.path.exists(DB_FILE):
        default_db = {
            "users": {
                "zeloth": {
                    "password": "sccadmin",
                    "name": "[SCC]zeloth",
                    "role": "admin",
                    "deck": ""
                }
            },
            "tournament": {
                "status": "not_started", # not_started, active, finished
                "name": "",
                "round": 0,
                "players": {}, # {username: {"points": 0, "dropped": False, "deck": "", "history": []}}
                "pairings": {}, # {round_num: [{"p1": str, "p2": str/None, "result": None, "first": None}]}
                "past_tournaments": []
            }
        }
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(default_db, f, indent=4)
        return default_db
    
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

db = load_db()

# Manejo de sesión de usuario
if "logged_user" not in st.session_state:
    st.session_state.logged_user = None

# ==========================================
# LÓGICA DEL TORNEO (RONDA SUIZA BO1)
# ==========================================
def generate_swiss_pairings(db_data):
    t_data = db_data["tournament"]
    active_players = [
        u for u, p in t_data["players"].items() if not p.get("dropped", False)
    ]
    
    # Ordenar jugadores por puntos descendentes
    active_players.sort(key=lambda x: t_data["players"][x]["points"], reverse=True)
    
    # Si hay impar, dar Bye al jugador de menor puntaje que no haya tenido Bye
    bye_player = None
    if len(active_players) % 2 != 0:
        for p in reversed(active_players):
            if "BYE" not in t_data["players"][p].get("history", []):
                bye_player = p
                break
        if not bye_player:
            bye_player = active_players[-1]
        active_players.remove(bye_player)
    
    # Historial de oponentes jugados
    def played_before(p1, p2):
        return p2 in t_data["players"][p1].get("history", [])

    pairings = []
    unpaired = list(active_players)
    
    while len(unpaired) > 1:
        p1 = unpaired.pop(0)
        found_p2 = None
        for i, p2 in enumerate(unpaired):
            if not played_before(p1, p2):
                found_p2 = p2
                unpaired.pop(i)
                break
        if not found_p2:
            found_p2 = unpaired.pop(0)
        
        pairings.append({"p1": p1, "p2": found_p2, "result": None, "first": None})

    if bye_player:
        pairings.append({"p1": bye_player, "p2": None, "result": "BYE", "first": None})
        # Otorgar 3 puntos automáticos por Bye
        t_data["players"][bye_player]["points"] += 3
        t_data["players"][bye_player].setdefault("history", []).append("BYE")

    next_round = t_data["round"] + 1
    t_data["round"] = next_round
    t_data["pairings"][str(next_round)] = pairings
    save_db(db_data)

# ==========================================
# BARRA LATERAL: AUTENTICACIÓN
# ==========================================
st.sidebar.title("🏴‍☠️ OPTCG Torneos")

if st.session_state.logged_user is None:
    st.sidebar.subheader("Iniciar Sesión / Registro")
    auth_mode = st.sidebar.radio("Modo", ["Iniciar Sesión", "Registrarse"])
    
    username = st.sidebar.text_input("Usuario")
    password = st.sidebar.text_input("Contraseña", type="password")
    
    if auth_mode == "Registrarse":
        user_name = st.sidebar.text_input("Nombre de Jugador")
        deck_name = st.sidebar.text_input("Mazo / Leader Principal")
        
        if st.sidebar.button("Crear Cuenta"):
            if username in db["users"]:
                st.sidebar.error("El nombre de usuario ya existe.")
            elif username and password and user_name:
                db["users"][username] = {
                    "password": password,
                    "name": user_name,
                    "role": "player",
                    "deck": deck_name
                }
                save_db(db)
                st.sidebar.success("¡Cuenta creada con éxito! Ahora inicia sesión.")
            else:
                st.sidebar.warning("Por favor completa todos los campos.")

    else:
        if st.sidebar.button("Ingresar"):
            if username in db["users"] and db["users"][username]["password"] == password:
                st.session_state.logged_user = username
                st.rerun()
            else:
                st.sidebar.error("Usuario o contraseña incorrectos.")
else:
    cur_user = db["users"][st.session_state.logged_user]
    st.sidebar.write(f"👋 Hola, **{cur_user['name']}**")
    st.sidebar.write(f"Rol: `{cur_user['role'].upper()}`")
    
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.logged_user = None
        st.rerun()

# ==========================================
# NAVEGACIÓN Y PESTAÑAS PRINCIPALES
# ==========================================
st.title("🏆 Gestión de Torneos One Piece Card Game")

tab1, tab2, tab3, tab4 = st.tabs(["⚔️ Torneo Actual", "📊 Standings", "📜 Historial", "⚙️ Administración"])

# ------------------------------------------
# TAB 1: TORNEO ACTUAL & EMPAREJAMIENTOS
# ------------------------------------------
with tab1:
    t_info = db["tournament"]
    
    if t_info["status"] == "not_started":
        st.info("No hay ningún torneo activo en este momento.")
        if st.session_state.logged_user:
            curr_u = st.session_state.logged_user
            in_registered = curr_u in t_info["players"]
            
            st.subheader("Inscripción al Próximo Torneo")
            user_deck = st.text_input("Mazo para el torneo:", value=db["users"][curr_u].get("deck", ""))
            
            col1, col2 = st.columns(2)
            with col1:
                if not in_registered:
                    if st.button("Inscribirme al Torneo"):
                        t_info["players"][curr_u] = {
                            "points": 0, "dropped": False, "deck": user_deck, "history": []
                        }
                        save_db(db)
                        st.success("¡Inscrito correctamente!")
                        st.rerun()
                else:
                    st.success("Ya estás inscrito en el torneo.")
                    if st.button("Cancelar Inscripción"):
                        del t_info["players"][curr_u]
                        save_db(db)
                        st.warning("Inscripción cancelada.")
                        st.rerun()

    elif t_info["status"] in ["active", "finished"]:
        st.subheader(f"Torneo: {t_info['name']} (Ronda {t_info['round']})")
        
        curr_round_str = str(t_info["round"])
        round_matches = t_info["pairings"].get(curr_round_str, [])
        
        st.write("### Emparejamientos de la Ronda")
        
        for idx, match in enumerate(round_matches):
            p1_name = db["users"].get(match["p1"], {}).get("name", match["p1"])
            
            if match["p2"] is None:
                st.success(f"🔹 **Mesa {idx+1}:** {p1_name} tiene **BYE** (+3 pts)")
                continue

            p2_name = db["users"].get(match["p2"], {}).get("name", match["p2"])
            
            with st.expander(f"Mesa {idx+1}: {p1_name} vs {p2_name} | Estado: {match['result'] or 'Pendiente'}"):
                col_a, col_b = st.columns(2)
                col_a.write(f"**Jugador 1:** {p1_name} ({db['users'][match['p1']].get('deck', 'Mazo N/A')})")
                col_b.write(f"**Jugador 2:** {p2_name} ({db['users'][match['p2']].get('deck', 'Mazo N/A')})")

                # Comprobar si el usuario actual es participante o admin
                user = st.session_state.logged_user
                is_participant = user in [match["p1"], match["p2"]]
                is_admin = db["users"].get(user, {}).get("role") == "admin"
                
                if match["result"] is None:
                    if is_participant or is_admin:
                        st.write("---")
                        st.write("**Registrar Resultado:**")
                        c1, c2 = st.columns(2)
                        
                        winner = c1.selectbox(
                            "Ganador:", 
                            [p1_name, p2_name, "Empate"], 
                            key=f"win_{t_info['round']}_{idx}"
                        )
                        first_player = c2.selectbox(
                            "¿Quién inició primero?:", 
                            [p1_name, p2_name], 
                            key=f"first_{t_info['round']}_{idx}"
                        )
                        
                        if st.button("Guardar Resultado", key=f"btn_{t_info['round']}_{idx}"):
                            # Asignar resultados
                            if winner == p1_name:
                                match["result"] = match["p1"]
                                t_info["players"][match["p1"]]["points"] += 3
                            elif winner == p2_name:
                                match["result"] = match["p2"]
                                t_info["players"][match["p2"]]["points"] += 3
                            else:
                                match["result"] = "DRAW"
                                t_info["players"][match["p1"]]["points"] += 1
                                t_info["players"][match["p2"]]["points"] += 1

                            # Historial de oponentes
                            t_info["players"][match["p1"]].setdefault("history", []).append(match["p2"])
                            t_info["players"][match["p2"]].setdefault("history", []).append(match["p1"])

                            match["first"] = match["p1"] if first_player == p1_name else match["p2"]
                            save_db(db)
                            st.success("Resultado guardado.")
                            st.rerun()
                else:
                    st.write(f"**Resultado registrado:** {match['result']}")
                    if match["first"]:
                        first_name = db["users"].get(match["first"], {}).get("name")
                        st.write(f"**Inició Primero:** {first_name}")

# ------------------------------------------
# TAB 2: STANDINGS (TABLA DE POSICIONES)
# ------------------------------------------
with tab2:
    st.subheader("📊 Tabla de Posiciones")
    if db["tournament"]["players"]:
        standings_data = []
        for username, pdata in db["tournament"]["players"].items():
            u_info = db["users"].get(username, {})
            standings_data.append({
                "Jugador": u_info.get("name", username),
                "Mazo": pdata.get("deck", "N/A"),
                "Puntos": pdata.get("points", 0),
                "Estado": "DROPPED" if pdata.get("dropped") else "Activo"
            })
        
        df = pd.DataFrame(standings_data)
        df = df.sort_values(by=["Puntos"], ascending=False).reset_index(drop=True)
        df.index += 1
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Aún no hay jugadores registrados en el torneo.")

# ------------------------------------------
# TAB 3: HISTORIAL
# ------------------------------------------
with tab3:
    st.subheader("📜 Historial de Torneos")
    past_list = db["tournament"].get("past_tournaments", [])
    if past_list:
        for past in reversed(past_list):
            with st.expander(f"Torneo: {past['name']} - Ganador: {past.get('winner', 'N/A')}"):
                st.write(f"Rondas totales: {past['total_rounds']}")
                st.json(past["standings"])
    else:
        st.info("No hay torneos pasados registrados.")

# ------------------------------------------
# TAB 4: PANEL DE ADMINISTRACIÓN (SOLO ADMINS)
# ------------------------------------------
with tab4:
    logged = st.session_state.logged_user
    if logged and db["users"].get(logged, {}).get("role") == "admin":
        st.subheader("⚙️ Controles de Administrador")
        t_data = db["tournament"]

        # Crear nuevo torneo
        if t_data["status"] == "not_started":
            st.write("### Crear Nuevo Torneo")
            t_name = st.text_input("Nombre del Torneo", "Torneo Semanal OPTCG")
            if st.button("Iniciar Torneo / Cerrar Inscripciones"):
                if len(t_data["players"]) < 2:
                    st.error("Se necesitan al menos 2 jugadores.")
                else:
                    t_data["name"] = t_name
                    t_data["status"] = "active"
                    generate_swiss_pairings(db)
                    st.success("Torneo iniciado y Primera Ronda generada.")
                    st.rerun()

        # Controles durante torneo activo
        elif t_data["status"] == "active":
            st.write("### Avance de Rondas")
            curr_r = str(t_data["round"])
            matches = t_data["pairings"].get(curr_r, [])
            pending_matches = [m for m in matches if m["result"] is None and m["p2"] is not None]
            
            if pending_matches:
                st.warning(f"Hay {len(pending_matches)} partida(s) sin resultado en la ronda actual.")
                
                st.write("#### Intervención Forzada de Admin")
                for m in pending_matches:
                    p1_n = db["users"].get(m["p1"], {}).get("name")
                    p2_n = db["users"].get(m["p2"], {}).get("name")
                    
                    st.write(f"**{p1_n} vs {p2_n}**")
                    col_adm1, col_adm2, col_adm3 = st.columns(3)
                    if col_adm1.button(f"Gana {p1_n}", key=f"force_p1_{m['p1']}"):
                        m["result"] = m["p1"]
                        t_data["players"][m["p1"]]["points"] += 3
                        save_db(db)
                        st.rerun()
                    if col_adm2.button(f"Gana {p2_n}", key=f"force_p2_{m['p2']}"):
                        m["result"] = m["p2"]
                        t_data["players"][m["p2"]]["points"] += 3
                        save_db(db)
                        st.rerun()
                    if col_adm3.button("Doble Lose (0 Pts)", key=f"force_dl_{m['p1']}"):
                        m["result"] = "DOUBLE_LOSS"
                        save_db(db)
                        st.rerun()
            else:
                if st.button("Siguiente Ronda Suiza ➡️"):
                    generate_swiss_pairings(db)
                    st.success("Nueva ronda generada.")
                    st.rerun()

            st.write("---")
            st.write("### Retiro (Drop) de Jugadores")
            active_p = [u for u, p in t_data["players"].items() if not p.get("dropped")]
            drop_target = st.selectbox("Seleccionar Jugador para Drop:", active_p)
            if st.button("Dropear Jugador"):
                t_data["players"][drop_target]["dropped"] = True
                save_db(db)
                st.warning(f"{drop_target} ha sido retirado del torneo.")
                st.rerun()

            st.write("---")
            if st.button("Finalizar Torneo 🏆"):
                t_data["status"] = "finished"
                # Determinar ganador por puntos
                sorted_p = sorted(t_data["players"].items(), key=lambda x: x[1]["points"], reverse=True)
                winner = sorted_p[0][0] if sorted_p else "N/A"
                winner_name = db["users"].get(winner, {}).get("name", winner)
                
                # Archivar torneo
                t_data.setdefault("past_tournaments", []).append({
                    "name": t_data["name"],
                    "total_rounds": t_data["round"],
                    "winner": winner_name,
                    "standings": t_data["players"]
                })
                
                # Resetear estado actual
                t_data["status"] = "not_started"
                t_data["round"] = 0
                t_data["players"] = {}
                t_data["pairings"] = {}
                save_db(db)
                st.success(f"Torneo Finalizado. ¡Ganador: {winner_name}!")
                st.rerun()
    else:
        st.warning("Acceso restringido solo para administradores.")