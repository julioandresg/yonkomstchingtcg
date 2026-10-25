import streamlit as st
import pandas as pd
import json
import os
import requests
import uuid
import re

# ==========================================
# GESTIÓN DE SESIÓN PERSISTENTE (URL QUERY PARAMS)
# ==========================================
query_params = st.query_params
if "logged_user" not in st.session_state:
    st.session_state.logged_user = query_params.get("user", None)

sidebar_state = "collapsed" if st.session_state.logged_user else "expanded"

st.set_page_config(
    page_title="OPTCG Swiss Tournament Manager",
    page_icon="🏴‍☠️",
    layout="wide",
    initial_sidebar_state=sidebar_state
)

ADMIN_USER = st.secrets.get("ADMIN_USER")
ADMIN_PASS = st.secrets.get("ADMIN_PASS")
WEBAPP_URL = st.secrets.get("WEBAPP_URL")

def login_user(username):
    st.session_state.logged_user = username
    st.query_params["user"] = username

def logout_user():
    st.session_state.logged_user = None
    if "user" in st.query_params:
        del st.query_params["user"]

# ==========================================
# BÚSQUEDA Y GESTIÓN DE CARTAS / LÍDERES
# ==========================================
def find_card_image(card_code):
    """
    Busca la imagen de una carta en la nueva estructura images/Cards/<EXP>/<CODIGO>.png
    Ej: images/Cards/OP05/OP05-002.png
    """
    if not card_code:
        return None
    
    clean_code = card_code.strip().upper()
    # Extraer expansión (ej. OP05 de OP05-002)
    match = re.match(r"^([A-Z0-9]+)-", clean_code)
    if match:
        expansion = match.group(1)
        path = os.path.join("images", "Cards", expansion, f"{clean_code}.png")
        if os.path.exists(path):
            return path
        # Intentar minúsculas o extensiones alternativas
        path_jpg = os.path.join("images", "Cards", expansion, f"{clean_code}.jpg")
        if os.path.exists(path_jpg):
            return path_jpg

    # Búsqueda recursiva genérica por si acaso
    base_dir = "images/Cards"
    if os.path.exists(base_dir):
        for root, _, files in os.walk(base_dir):
            for file in files:
                if file.upper().startswith(clean_code):
                    return os.path.join(root, file)
                    
    # Fallback al sistema antiguo de imágenes si estuviera
    legacy_path = os.path.join("images", f"{clean_code}.png")
    if os.path.exists(legacy_path):
        return legacy_path

    return None

def parse_decklist(decklist_text):
    """
    Parsea el texto de la lista de cartas.
    Formato esperado por línea: 4xOP05-015 o 1 x OP05-002
    Retorna: (total_cards, parsed_items_dict, leader_code, error_message)
    """
    if not decklist_text:
        return 0, {}, None, "La lista está vacía."

    lines = decklist_text.strip().split("\n")
    total_count = 0
    parsed_items = {}
    leader_code = None
    
    pattern = re.compile(r"^\s*(\d+)\s*[xX]\s*([A-Z0-9]+-[A-Z0-9]+)\s*$", re.IGNORECASE)

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        
        match = pattern.match(line)
        if not match:
            return 0, {}, None, f"Error en la línea {line_num}: '{line}'. Formato requerido: `4xOP05-015`"
        
        qty = int(match.group(1))
        code = match.group(2).upper()
        
        total_count += qty
        parsed_items[code] = parsed_items.get(code, 0) + qty
        
        # En OPTCG, los líderes suelen ser cantidad 1 y terminan en -001 (o identificados por convención)
        # O permitimos que la carta de cantidad 1 sea detectada como líder potencial
        if qty == 1 and (code.endswith("-001") or not leader_code):
            leader_code = code

    if total_count != 51:
        return 0, {}, None, f"La cantidad total de cartas debe ser exactamente 51. Actualmente hay {total_count} cartas."

    return total_count, parsed_items, leader_code, None

# ==========================================
# LECTURA / ESCRITURA MEDIANTE WEBAPP
# ==========================================
def load_db():
    default_tourneys = {}
    default_past_tourneys = []
    
    default_users = {
        ADMIN_USER: {
            "password": ADMIN_PASS,
            "name": "[SCC]zeloth",
            "role": "admin",
            "decklist": "1xOP05-001\n50xOP05-002",
            "email": "admin@domain.com",
            "reset_requested": False
        }
    }
    
    default_decks = {}

    try:
        df_all = pd.DataFrame()
        if WEBAPP_URL:
            res = requests.get(WEBAPP_URL, timeout=10)
            if res.status_code == 200:
                raw_data = res.json()
                if raw_data and len(raw_data) > 1:
                    headers = [str(c).strip().lower() for c in raw_data[0]]
                    df_all = pd.DataFrame(raw_data[1:], columns=headers)
        
        if df_all.empty:
            return {"users": default_users, "tournaments": default_tourneys, "past_tournaments": default_past_tourneys, "decks": default_decks}

        users_dict = {}
        if 'username' in df_all.columns:
            for _, row in df_all.iterrows():
                u_val = row.get('username')
                if pd.notna(u_val) and str(u_val).strip() != "":
                    u_name = str(u_val).strip()
                    # Compatibilidad con la columna deck anterior transformándola a decklist si es necesario
                    legacy_deck = str(row.get('deck', '')).strip()
                    decklist_val = str(row.get('decklist', '')).strip()
                    if not decklist_val and legacy_deck and "-" in legacy_deck:
                        decklist_val = f"1x{legacy_deck}\n50xOP01-002"

                    users_dict[u_name] = {
                        "password": str(row.get('password', '')) if pd.notna(row.get('password')) else "",
                        "name": str(row.get('name', u_name)) if pd.notna(row.get('name')) else u_name,
                        "role": str(row.get('role', 'player')).strip().lower() if pd.notna(row.get('role')) else "player",
                        "decklist": decklist_val,
                        "email": str(row.get('email', '')).strip() if pd.notna(row.get('email')) else "",
                        "reset_requested": str(row.get('reset_requested', 'false')).lower() == 'true'
                    }
                    
        if ADMIN_USER not in users_dict:
            users_dict[ADMIN_USER] = default_users[ADMIN_USER]

        tourneys_dict = {}
        past_tourneys_list = []
        if 'key' in df_all.columns and 'value' in df_all.columns:
            t_row = df_all.loc[df_all['key'].astype(str).str.strip().str.lower() == 'tournaments']
            if not t_row.empty:
                val = t_row['value'].values[0]
                if pd.notna(val) and str(val).strip() != "":
                    try:
                        tourneys_dict = json.loads(val)
                    except Exception:
                        pass

            past_row = df_all.loc[df_all['key'].astype(str).str.strip().str.lower() == 'past_tournaments']
            if not past_row.empty:
                val_past = past_row['value'].values[0]
                if pd.notna(val_past) and str(val_past).strip() != "":
                    try:
                        past_tourneys_list = json.loads(val_past)
                    except Exception:
                        pass

        return {"users": users_dict, "tournaments": tourneys_dict, "past_tournaments": past_tourneys_list, "decks": default_decks}

    except Exception:
        return {
            "users": default_users,
            "tournaments": default_tourneys,
            "past_tournaments": default_past_tourneys,
            "decks": default_decks
        }

def save_db(data):
    if not WEBAPP_URL:
        st.warning("⚠️ No se ha configurado la URL de Apps Script (WEBAPP_URL).")
        return

    try:
        headers = ["username", "password", "name", "role", "decklist", "reset_requested", "email", "", "", "", "key", "value", "", "", "", "", ""]
        
        users_rows = [headers]
        u_keys = list(data["users"].keys())
        max_len = max(len(u_keys), 2)
        
        for i in range(max_len):
            row = [""] * 17
            
            if i < len(u_keys):
                u_id = u_keys[i]
                u_data = data["users"][u_id]
                row[0] = u_id
                row[1] = str(u_data.get("password", ""))
                row[2] = str(u_data.get("name", ""))
                row[3] = str(u_data.get("role", "player"))
                row[4] = str(u_data.get("decklist", ""))
                row[5] = "TRUE" if u_data.get("reset_requested") else "FALSE"
                row[6] = str(u_data.get("email", ""))

            if i == 0:
                row[10] = "tournaments"
                row[11] = json.dumps(data["tournaments"])
            elif i == 1:
                row[10] = "past_tournaments"
                row[11] = json.dumps(data.get("past_tournaments", []))

            users_rows.append(row)

        payload = {"rows": users_rows}
        res = requests.post(WEBAPP_URL, json=payload, timeout=15)
        if res.status_code == 200:
            st.toast("✅ Base de datos sincronizada", icon="💾")
        else:
            st.error("⚠️ Error al guardar en Google Sheets.")
    except Exception as e:
        st.error(f"⚠️ Error de red al guardar: {e}")

# Cargar base de datos
db_full = load_db()
db = {
    "users": db_full["users"],
    "tournaments": db_full["tournaments"],
    "past_tournaments": db_full["past_tournaments"]
}
available_decks = db_full["decks"]

# ==========================================
# AUXILIARES Y LÓGICA DE TORNEO
# ==========================================
def finish_tournament_logic(t_id, db_data, explicit_winner_user=None):
    t_curr = db_data["tournaments"][t_id]
    t_curr["status"] = "finished"
    
    sorted_p = sorted(t_curr["players"].items(), key=lambda x: x[1]["points"], reverse=True)
    winner_user = explicit_winner_user or (sorted_p[0][0] if sorted_p else "N/A")
    winner_name = db_data["users"].get(winner_user, {}).get("name", winner_user)
    winner_decklist = t_curr["players"].get(winner_user, {}).get("decklist", "")
    _, _, winner_leader, _ = parse_decklist(winner_decklist)
    
    db_data.setdefault("past_tournaments", []).append({
        "name": t_curr["name"],
        "total_rounds": t_curr["round"],
        "winner_user": winner_user,
        "winner_name": winner_name,
        "winner_leader": winner_leader or "Desconocido",
        "standings": t_curr["players"]
    })
    
    del db_data["tournaments"][t_id]
    save_db({"users": db_data["users"], "tournaments": db_data["tournaments"], "past_tournaments": db_data["past_tournaments"], "decks": available_decks})

def generate_swiss_pairings_for_tournament(t_id, db_data):
    t_data = db_data["tournaments"][t_id]
    active_players = [u for u, p in t_data["players"].items() if not p.get("dropped", False)]
    active_players.sort(key=lambda x: t_data["players"][x]["points"], reverse=True)
    
    bye_player = None
    if len(active_players) % 2 != 0:
        for p in reversed(active_players):
            if "BYE" not in t_data["players"][p].get("history", []):
                bye_player = p
                break
        if not bye_player:
            bye_player = active_players[-1]
        active_players.remove(bye_player)
    
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
        t_data["players"][bye_player]["points"] += 3
        t_data["players"][bye_player].setdefault("history", []).append("BYE")

    next_round = t_data.get("round", 0) + 1
    t_data["round"] = next_round
    t_data["pairings"][str(next_round)] = pairings
    save_db({
        "users": db_data["users"],
        "tournaments": db_data["tournaments"],
        "past_tournaments": db_data["past_tournaments"],
        "decks": available_decks
    })

def render_standings_table(t_players_data, users_db):
    if not t_players_data:
        st.caption("Sin datos de posiciones disponibles.")
        return

    standings_rows = []
    for username, pdata in t_players_data.items():
        u_info = users_db.get(username, {})
        decklist = pdata.get("decklist", "")
        _, _, leader, _ = parse_decklist(decklist)
        standings_rows.append({
            "Jugador": u_info.get("name", username),
            "Líder": leader or "N/A",
            "Puntos": pdata.get("points", 0),
            "Estado": "DROPPED" if pdata.get("dropped") else "Activo"
        })
    df = pd.DataFrame(standings_rows).sort_values(by=["Puntos"], ascending=False).reset_index(drop=True)
    df.index += 1
    st.dataframe(df, use_container_width=True)

# ==========================================
# BARRA LATERAL: AUTENTICACIÓN
# ==========================================
st.sidebar.title("🏴‍☠️ OPTCG Torneos")

if st.session_state.logged_user is None or st.session_state.logged_user not in db["users"]:
    st.sidebar.subheader("Acceso de Usuarios")
    auth_mode = st.sidebar.radio("Menú", ["Iniciar Sesión", "Registrarse", "Olvidé mi Contraseña"])
    
    if auth_mode == "Iniciar Sesión":
        with st.sidebar.form("login_form"):
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            submit_login = st.form_submit_button("Ingresar")
            
            if submit_login:
                if username in db["users"] and db["users"][username]["password"] == password:
                    login_user(username)
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
                
    elif auth_mode == "Registrarse":
        with st.sidebar.form("register_form"):
            username = st.text_input("Nombre de Usuario (Login)")
            password = st.text_input("Contraseña", type="password")
            user_name = st.text_input("Nombre / Nick de Jugador")
            user_email = st.text_input("Correo Electrónico (para recuperación)")
            submit_reg = st.form_submit_button("Crear Cuenta")
            
            if submit_reg:
                if username in db["users"]:
                    st.error("El nombre de usuario ya existe.")
                elif username and password and user_name and user_email:
                    db["users"][username] = {
                        "password": password,
                        "name": user_name,
                        "role": "player",
                        "decklist": "1xOP01-001\n50xOP01-002",
                        "email": user_email.strip(),
                        "reset_requested": False
                    }
                    save_db({"users": db["users"], "tournaments": db["tournaments"], "past_tournaments": db["past_tournaments"], "decks": available_decks})
                    st.success("¡Cuenta creada exitosamente! Ya puedes iniciar sesión.")
                else:
                    st.warning("Por favor completa todos los campos obligatorios.")

    elif auth_mode == "Olvidé mi Contraseña":
        with st.sidebar.form("reset_form"):
            reset_user = st.text_input("Ingresa tu usuario:")
            submit_reset = st.form_submit_button("Solicitar Restablecimiento")
            
            if submit_reset:
                if reset_user in db["users"]:
                    db["users"][reset_user]["reset_requested"] = True
                    u_email = db["users"][reset_user].get("email", "no registrado")
                    save_db({"users": db["users"], "tournaments": db["tournaments"], "past_tournaments": db["past_tournaments"], "decks": available_decks})
                    st.success(f"Solicitud enviada al Administrador. Correo: {u_email}")
                else:
                    st.error("El usuario ingresado no existe.")

else:
    cur_user = db["users"][st.session_state.logged_user]
    st.sidebar.write(f"👋 Hola, **{cur_user['name']}**")
    st.sidebar.write(f"Rol: `{cur_user['role'].upper()}`")
    
    if st.sidebar.button("Cerrar Sesión"):
        logout_user()
        st.rerun()

# ==========================================
# NAVEGACIÓN PRINCIPAL Y CONTROL DE ROLES
# ==========================================
st.title("🏆 Gestión de Torneos One Piece Card Game")

is_logged = st.session_state.logged_user is not None and st.session_state.logged_user in db["users"]
user_role = db["users"].get(st.session_state.logged_user, {}).get("role", "player") if is_logged else "guest"

is_admin = user_role == "admin"
is_mod = user_role == "mod"
can_manage_tournaments = is_admin or is_mod

tabs = ["⚔️ Torneos", "📜 Historial"]
if is_logged:
    tabs.append("👤 Mi Perfil")

if is_admin:
    tabs.append("👥 Gestión de Cuentas")

if can_manage_tournaments:
    tabs.append("⚙️ Admin Torneo")

tab_elements = st.tabs(tabs)

# ------------------------------------------
# TAB 1: TORNEOS MULTIPLES
# ------------------------------------------
with tab_elements[0]:
    st.subheader("🎯 Torneos Activos y Próximos Eventos")
    tournaments = db["tournaments"]
    
    if not tournaments:
        st.info("No hay ningún torneo anunciado en este momento. El administrador o moderador creará uno próximamente.")
    else:
        tourney_options = {t_id: t_data["name"] for t_id, t_data in tournaments.items()}
        selected_t_id = st.selectbox("Selecciona un Torneo para interactuar:", options=list(tourney_options.keys()), format_func=lambda x: tourney_options[x])
        
        t_info = tournaments[selected_t_id]
        st.write("---")
        
        if t_info.get("status") == "not_started":
            st.success(f"🏆 **Torneo Anunciado:** {t_info['name']}")
            st.info("Las inscripciones están **abiertas**. Asegúrate de tener tu decklist de 51 cartas guardada en tu perfil antes de inscribirte.")
            
            if is_logged:
                curr_u = st.session_state.logged_user
                in_registered = curr_u in t_info.get("players", {})
                user_decklist = db["users"][curr_u].get("decklist", "")
                
                total_c, _, leader_c, err_msg = parse_decklist(user_decklist)
                
                st.write("#### Tu Estado en este Torneo")
                st.write(f"Jugador: **{db['users'][curr_u]['name']}** | Líder detectado: **{leader_c or 'Ninguno'}**")
                
                if err_msg:
                    st.warning(f"⚠️ Tu decklist actual tiene un problema: {err_msg}. Actualiza tu decklist en la pestaña 'Mi Perfil' para poder inscribirte.")
                
                col_ins1, col_ins2 = st.columns(2)
                with col_ins1:
                    if not in_registered:
                        if st.button("Inscribirme a este Torneo", type="primary", key=f"ins_{selected_t_id}", disabled=(err_msg is not None)):
                            t_info.setdefault("players", {})[curr_u] = {
                                "points": 0, "dropped": False, "decklist": user_decklist, "history": []
                            }
                            save_db({"users": db["users"], "tournaments": db["tournaments"], "past_tournaments": db["past_tournaments"], "decks": available_decks})
                            st.success("¡Te has inscrito correctamente!")
                            st.rerun()
                    else:
                        st.info("✅ Ya estás inscrito en este torneo.")
                        if st.button("Cancelar mi Inscripción", key=f"del_{selected_t_id}"):
                            del t_info["players"][curr_u]
                            save_db({"users": db["users"], "tournaments": db["tournaments"], "past_tournaments": db["past_tournaments"], "decks": available_decks})
                            st.warning("Has cancelado tu inscripción.")
                            st.rerun()
            else:
                st.info("Inicia sesión en la barra lateral para poder inscribirte al torneo.")
                
            st.write("---")
            st.write(f"👥 **Jugadores Inscritos ({len(t_info.get('players', {}))}):**")
            if t_info.get("players"):
                registered_list = []
                for p_id, p_data in t_info["players"].items():
                    p_name = db["users"].get(p_id, {}).get("name", p_id)
                    _, _, p_lead, _ = parse_decklist(p_data.get("decklist", ""))
                    registered_list.append({"Jugador": p_name, "Líder": p_lead or "N/A"})
                st.dataframe(pd.DataFrame(registered_list), use_container_width=True)
            else:
                st.caption("Aún no hay jugadores inscritos.")

        elif t_info.get("status") in ["active", "finished"]:
            st.write(f"### ⚔️ {t_info['name']} (Ronda {t_info.get('round', 0)})")
            
            curr_round_str = str(t_info.get("round", 1))
            round_matches = t_info.get("pairings", {}).get(curr_round_str, [])
            
            st.write("#### 🥊 Emparejamientos de la Ronda Actual")
            
            if not round_matches:
                st.caption("Generando emparejamientos...")
            else:
                for idx, match in enumerate(round_matches):
                    p1_name = db["users"].get(match["p1"], {}).get("name", match["p1"])
                    
                    if match["p2"] is None:
                        st.success(f"🔹 **Mesa {idx+1}:** {p1_name} tiene **BYE** (+3 pts)")
                        continue

                    p2_name = db["users"].get(match["p2"], {}).get("name", match["p2"])
                    
                    p1_dl = t_info["players"].get(match["p1"], {}).get("decklist", "")
                    p2_dl = t_info["players"].get(match["p2"], {}).get("decklist", "")
                    _, _, p1_lead, _ = parse_decklist(p1_dl)
                    _, _, p2_lead, _ = parse_decklist(p2_dl)

                    with st.expander(f"Mesa {idx+1}: {p1_name} ({p1_lead}) vs {p2_name} ({p2_lead}) | Estado: {match['result'] or 'Pendiente'}"):
                        c_img1, c_img2 = st.columns(2)
                        with c_img1:
                            st.write(f"**{p1_name}** (Líder: {p1_lead})")
                            p1_img = find_card_image(p1_lead)
                            if p1_img:
                                st.image(p1_img, width=150)
                            with st.expander("Ver Decklist completo"):
                                st.text(p1_dl)
                        with c_img2:
                            st.write(f"**{p2_name}** (Líder: {p2_lead})")
                            p2_img = find_card_image(p2_lead)
                            if p2_img:
                                st.image(p2_img, width=150)
                            with st.expander("Ver Decklist completo"):
                                st.text(p2_dl)

                        user = st.session_state.logged_user
                        if match["result"] is None and (user in [match["p1"], match["p2"]] or can_manage_tournaments):
                            st.write("---")
                            c1, c2 = st.columns(2)
                            winner = c1.selectbox("Ganador:", [p1_name, p2_name, "Empate"], key=f"win_{selected_t_id}_{t_info['round']}_{idx}")
                            first_player = c2.selectbox("¿Quién inició primero?:", [p1_name, p2_name], key=f"first_{selected_t_id}_{t_info['round']}_{idx}")
                            
                            if st.button("Guardar Resultado", key=f"btn_{selected_t_id}_{t_info['round']}_{idx}"):
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

                                t_info["players"][match["p1"]].setdefault("history", []).append(match["p2"])
                                t_info["players"][match["p2"]].setdefault("history", []).append(match["p1"])
                                match["first"] = match["p1"] if first_player == p1_name else match["p2"]
                                save_db({"users": db["users"], "tournaments": db["tournaments"], "past_tournaments": db["past_tournaments"], "decks": available_decks})
                                st.rerun()

            st.write("---")
            st.write("#### 📊 Tabla de Posiciones en Tiempo Real (Standings)")
            render_standings_table(t_info.get("players", {}), db["users"])

# ------------------------------------------
# TAB 2: HISTORIAL CON GRÁFICO DE TORTA
# ------------------------------------------
with tab_elements[1]:
    st.subheader("📜 Historial de Torneos Finalizados")
    past_list = db.get("past_tournaments", [])
    if past_list:
        for past in reversed(past_list):
            w_name = past.get("winner_name", "N/A")
            w_leader = past.get("winner_leader", "N/A")
            
            with st.expander(f"🏆 {past['name']} — Ganador: {w_name} ({w_leader})"):
                col_h1, col_h2 = st.columns([1, 2])
                with col_h1:
                    st.success(f"👑 **Campeón:** {w_name}")
                    st.write(f"🎴 **Líder Ganador:** {w_leader}")
                    w_img = find_card_image(w_leader)
                    if w_img:
                        st.image(w_img, width=160)
                with col_h2:
                    st.write(f"**Rondas Totales:** {past.get('total_rounds', 'N/A')}")
                    st.write("#### 📊 Standings Finales:")
                    render_standings_table(past.get("standings", {}), db["users"])

                st.write("---")
                st.write("### 📈 Distribución de Líderes Jugados en el Torneo")
                standings_data = past.get("standings", {})
                if standings_data:
                    leader_counts = {}
                    for _, pdata in standings_data.items():
                        _, _, lead, _ = parse_decklist(pdata.get("decklist", ""))
                        if lead:
                            leader_counts[lead] = leader_counts.get(lead, 0) + 1
                    
                    if leader_counts:
                        df_chart = pd.DataFrame(list(leader_counts.items()), columns=["Líder", "Cantidad"])
                        # Gráfico de torta nativo con st.altair_chart o st.bar_chart / st.pyplot
                        import altair as alt
                        pie_chart = alt.Chart(df_chart).mark_arc(innerRadius=50).encode(
                            theta=alt.Theta(field="Cantidad", type="quantitative"),
                            color=alt.Color(field="Líder", type="nominal"),
                            tooltip=["Líder", "Cantidad"]
                        ).properties(width=400, height=300)
                        st.altair_chart(pie_chart, use_container_width=True)
                    else:
                        st.caption("No hay datos suficientes de líderes para graficar.")
    else:
        st.info("No hay torneos pasados registrados en el historial.")

# ------------------------------------------
# TAB 3: MI PERFIL (GESTIÓN DE DECKLIST)
# ------------------------------------------
if is_logged:
    current_tab_idx = 2
    with tab_elements[current_tab_idx]:
        st.subheader("👤 MI PERFIL - Decklist del Jugador")
        curr_username = st.session_state.logged_user
        user_data = db["users"][curr_username]
        
        col_prof1, col_prof2 = st.columns(2)
        
        with col_prof1:
            st.write("### ✏️ Información Personal")
            new_name = st.text_input("Nombre Visible / Nick:", value=user_data.get("name", ""))
            new_email = st.text_input("Correo Electrónico registrado:", value=user_data.get("email", ""))
            
            st.write("---")
            st.write("### 🎴 Tu Decklist de 51 Cartas")
            st.caption("Ingresa tu lista con el formato `Cantidad x Código` (ej. `1xOP05-001`, `4xOP05-015`). La suma exacta debe ser 51 cartas.")
            
            current_decklist = user_data.get("decklist", "")
            new_decklist = st.text_area("Decklist:", value=current_decklist, height=220)
            
            total_cards, parsed_dict, detected_leader, validation_error = parse_decklist(new_decklist)
            
            if validation_error:
                st.error(f"❌ {validation_error}")
            else:
                st.success(f"✅ ¡Decklist válida! Total de cartas: {total_cards} | Líder detectado: **{detected_leader}**")
                
            st.write("---")
            if st.button("Guardar Mi Perfil y Decklist"):
                if validation_error:
                    st.error("No se puede guardar porque la decklist no es válida (debe sumar exactamente 51 cartas).")
                else:
                    db["users"][curr_username]["name"] = new_name.strip()
                    db["users"][curr_username]["email"] = new_email.strip()
                    db["users"][curr_username]["decklist"] = new_decklist.strip()
                    save_db({"users": db["users"], "tournaments": db["tournaments"], "past_tournaments": db["past_tournaments"], "decks": available_decks})
                    st.success("Perfil y Decklist actualizados correctamente.")
                    st.rerun()

        with col_prof2:
            st.write("### 🔍 Vista Previa del Líder Detectado")
            _, _, leader_code, _ = parse_decklist(new_decklist)
            if leader_code:
                l_img = find_card_image(leader_code)
                if l_img:
                    st.image(l_img, caption=f"Líder: {leader_code}", width=220)
                else:
                    st.warning(f"No se encontró la imagen para el código `{leader_code}` en `images/Cards/`.")
            else:
                st.info("Ingresa una decklist válida para visualizar tu líder.")

            st.write("---")
            st.write("### 🔒 Cambiar Contraseña")
            curr_pass_input = st.text_input("Contraseña Actual:", type="password")
            new_pass_input = st.text_input("Nueva Contraseña:", type="password")
            confirm_pass_input = st.text_input("Reingresar Nueva Contraseña:", type="password")
            
            if st.button("Actualizar Contraseña"):
                if curr_pass_input != user_data["password"]:
                    st.error("La contraseña actual es incorrecta.")
                elif new_pass_input and new_pass_input == confirm_pass_input:
                    db["users"][curr_username]["password"] = new_pass_input
                    db["users"][curr_username]["reset_requested"] = False
                    save_db({"users": db["users"], "tournaments": db["tournaments"], "past_tournaments": db["past_tournaments"], "decks": available_decks})
                    st.success("¡Contraseña actualizada con éxito!")
                    st.rerun()
                else:
                    st.error("Las contraseñas no coinciden.")

# ------------------------------------------
# TAB 4: GESTIÓN DE CUENTAS (EXCLUSIVO PARA ADMIN)
# ------------------------------------------
if is_admin:
    admin_tab_idx = 3
    with tab_elements[admin_tab_idx]:
        st.subheader("👥 Gestión de Cuentas y Permisos (Solo Administrador)")
        
        users_list = []
        for u_id, u_data in db["users"].items():
            _, _, l_code, _ = parse_decklist(u_data.get("decklist", ""))
            users_list.append({
                "Usuario": u_id,
                "Nombre": u_data.get("name", ""),
                "Correo": u_data.get("email", ""),
                "Rol": u_data.get("role", "player").upper(),
                "Líder Registrado": l_code or "Sin líder",
                "Reset Solicitado": "SÍ" if u_data.get("reset_requested") else "No"
            })
        st.dataframe(pd.DataFrame(users_list), use_container_width=True)
        
        st.write("---")
        st.write("### 🛡️ Administración de Permisos y Roles")
        
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            target_u = st.selectbox("Seleccionar Usuario:", list(db["users"].keys()))
            
        with col_m2:
            current_target_role = db["users"][target_u].get("role", "player").lower()
            role_options = ["player", "mod", "admin"]
            role_index = role_options.index(current_target_role) if current_target_role in role_options else 0
            
            new_role = st.selectbox("Asignar Nuevo Rol:", role_options, index=role_index, format_func=lambda x: x.upper())
            
            if st.button("Guardar Nuevo Rol"):
                if target_u == ADMIN_USER and new_role != "admin":
                    st.error("No se puede cambiar el rol del Administrador Principal.")
                else:
                    db["users"][target_u]["role"] = new_role
                    save_db({"users": db["users"], "tournaments": db["tournaments"], "past_tournaments": db["past_tournaments"], "decks": available_decks})
                    st.success(f"Rol de {target_u} actualizado a '{new_role.upper()}' correctamente.")
                    st.rerun()

# ------------------------------------------
# TAB 5: ADMIN TORNEOS MULTIPLES (ADMIN Y MOD)
# ------------------------------------------
if can_manage_tournaments:
    t_tab_idx = 4 if is_admin else 3
    with tab_elements[t_tab_idx]:
        st.subheader("⚙️ Panel de Control de Torneos (Admin & Moderadores)")
        
        st.write("### 🆕 Anunciar Nuevo Torneo")
        with st.form("create_tournament_form"):
            new_t_name = st.text_input("Nombre del Nuevo Torneo:", placeholder="Ej. Liga Mensual de Octubre")
            submit_create_t = st.form_submit_button("📢 Anunciar y Abrir Inscripciones")
            
            if submit_create_t:
                if not new_t_name.strip():
                    st.error("Escribe un nombre válido.")
                else:
                    new_id = f"t_{uuid.uuid4().hex[:6]}"
                    db["tournaments"][new_id] = {
                        "name": new_t_name.strip(),
                        "status": "not_started",
                        "round": 0,
                        "players": {},
                        "pairings": {}
                    }
                    save_db({"users": db["users"], "tournaments": db["tournaments"], "past_tournaments": db["past_tournaments"], "decks": available_decks})
                    st.success(f"¡Torneo '{new_t_name.strip()}' creado y anunciado con éxito!")
                    st.rerun()

        st.write("---")
        st.write("### ⚙️ Gestionar Torneos Existentes")
        
        if not db["tournaments"]:
            st.caption("No existen torneos activos actualmente.")
        else:
            admin_t_options = {t_id: f"{t_data['name']} ({'Inscripciones Abiertas' if t_data.get('status')=='not_started' else 'En Curso'})" for t_id, t_data in db["tournaments"].items()}
            adm_selected_t_id = st.selectbox("Selecciona un Torneo para Gestionar:", options=list(admin_t_options.keys()), format_func=lambda x: admin_t_options[x])
            
            t_curr = db["tournaments"][adm_selected_t_id]
            st.write(f"**Estado del Torneo:** `{t_curr.get('status')}` | **Ronda:** {t_curr.get('round', 0)}")
            
            if t_curr.get("status") == "not_started":
                col_a1, col_a2 = st.columns(2)
                with col_a1:
                    if st.button("🔒 Cerrar Inscripciones e Iniciar R1", type="primary", key=f"start_{adm_selected_t_id}"):
                        current_players = t_curr.get("players", {})
                        if len(current_players) < 2:
                            st.error(f"❌ No se puede iniciar: Hay {len(current_players)} jugador(es). Se requieren al menos 2.")
                        else:
                            t_curr["status"] = "active"
                            generate_swiss_pairings_for_tournament(adm_selected_t_id, db)
                            st.success("¡Inscripciones cerradas y Ronda 1 generada!")
                            st.rerun()
                with col_a2:
                    if st.button("🗑️ Cancelar / Eliminar Torneo", key=f"del_t_{adm_selected_t_id}"):
                        del db["tournaments"][adm_selected_t_id]
                        save_db({"users": db["users"], "tournaments": db["tournaments"], "past_tournaments": db["past_tournaments"], "decks": available_decks})
                        st.warning("Torneo eliminado.")
                        st.rerun()

            elif t_curr.get("status") == "active":
                curr_r = str(t_curr.get("round", 1))
                matches = t_curr.get("pairings", {}).get(curr_r, [])
                pending = [m for m in matches if m["result"] is None and m["p2"] is not None]
                
                if pending:
                    st.warning(f"Hay {len(pending)} partida(s) pendiente(s) en este torneo.")
                else:
                    st.success("Todas las partidas de la ronda actual han sido completadas.")
                    
                    active_players_list = [p for p in t_curr["players"].items() if not p[1].get("dropped")]
                    active_players_list.sort(key=lambda x: x[1]["points"], reverse=True)
                    
                    has_single_winner = False
                    single_winner_user = None
                    
                    if len(active_players_list) >= 1:
                        top_points = active_players_list[0][1]["points"]
                        if len(active_players_list) == 1 or active_players_list[1][1]["points"] < top_points:
                            has_single_winner = True
                            single_winner_user = active_players_list[0][0]

                    if has_single_winner:
                        winner_display_name = db["users"].get(single_winner_user, {}).get("name", single_winner_user)
                        st.balloons()
                        st.success(f"🏆 **¡Tenemos un único Ganador Absoluto!** {winner_display_name} lidera la tabla en solitario con {top_points} pts.")
                        
                        if st.button("🏆 Finalizar y Proclamar Ganador", type="primary", key=f"auto_finish_{adm_selected_t_id}"):
                            finish_tournament_logic(adm_selected_t_id, db, explicit_winner_user=single_winner_user)
                            st.rerun()
                    else:
                        if st.button("➡️ Generar Siguiente Ronda Suiza", type="primary", key=f"next_r_{adm_selected_t_id}"):
                            generate_swiss_pairings_for_tournament(adm_selected_t_id, db)
                            st.rerun()

                st.write("---")
                if st.button("🏆 Finalizar Torneo Manualmente", key=f"finish_manual_{adm_selected_t_id}"):
                    finish_tournament_logic(adm_selected_t_id, db)
                    st.success("¡Torneo finalizado y movido al Historial!")
                    st.rerun()

            st.write("---")
            st.write(f"👥 **Jugadores Inscritos en este Torneo ({len(t_curr.get('players', {}))}):**")
            if t_curr.get("players"):
                registered_list = []
                for p_id, p_data in t_curr["players"].items():
                    p_name = db["users"].get(p_id, {}).get("name", p_id)
                    _, _, p_lead, _ = parse_decklist(p_data.get("decklist", ""))
                    registered_list.append({"Usuario": p_id, "Nombre": p_name, "Líder": p_lead or "N/A", "Puntos": p_data.get("points", 0)})
                st.dataframe(pd.DataFrame(registered_list), use_container_width=True)
            else:
                st.caption("Aún no hay ningún jugador inscrito.")