import streamlit as st
import pandas as pd
import json
import os
import requests

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

ADMIN_USER = st.secrets.get("ADMIN_USER", "zeloth")
ADMIN_PASS = st.secrets.get("ADMIN_PASS", "admin123")
WEBAPP_URL = st.secrets.get("WEBAPP_URL", "")

def login_user(username):
    st.session_state.logged_user = username
    st.query_params["user"] = username

def logout_user():
    st.session_state.logged_user = None
    if "user" in st.query_params:
        del st.query_params["user"]

# ==========================================
# LECTURA / ESCRITURA MEDIANTE WEBAPP
# ==========================================
def load_db():
    default_tourney = {
        "status": "not_started",
        "name": "",
        "round": 0,
        "players": {},
        "pairings": {},
        "past_tournaments": []
    }
    
    default_users = {
        ADMIN_USER: {
            "password": ADMIN_PASS,
            "name": "[SCC]zeloth",
            "role": "admin",
            "deck": "Sin mazo asignado",
            "email": "admin@domain.com",
            "reset_requested": False
        }
    }
    
    default_decks = {
        "OP17-Shanks": "Líder agresivo de los Piratas del Pelirrojo.",
        "OP01-001 Zoro": "Líder Rojo agresivo con gran presión ofensiva."
    }

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
            return {"users": default_users, "tournament": default_tourney, "decks": default_decks}

        # 1. Cargar Usuarios (Cols A-G)
        users_dict = {}
        if 'username' in df_all.columns:
            for _, row in df_all.iterrows():
                u_val = row.get('username')
                if pd.notna(u_val) and str(u_val).strip() != "":
                    u_name = str(u_val).strip()
                    users_dict[u_name] = {
                        "password": str(row.get('password', '')) if pd.notna(row.get('password')) else "",
                        "name": str(row.get('name', u_name)) if pd.notna(row.get('name')) else u_name,
                        "role": str(row.get('role', 'player')) if pd.notna(row.get('role')) else "player",
                        "deck": str(row.get('deck', 'Sin mazo asignado')).strip() if pd.notna(row.get('deck')) else "Sin mazo asignado",
                        "email": str(row.get('email', '')).strip() if pd.notna(row.get('email')) else "",
                        "reset_requested": str(row.get('reset_requested', 'false')).lower() == 'true'
                    }
                    
        if ADMIN_USER not in users_dict:
            users_dict[ADMIN_USER] = default_users[ADMIN_USER]

        # 2. Cargar Torneo (Cols K-L)
        tourney_dict = dict(default_tourney)
        if 'key' in df_all.columns and 'value' in df_all.columns:
            tourney_row = df_all.loc[df_all['key'].astype(str).str.strip().str.lower() == 'data']
            if not tourney_row.empty:
                val = tourney_row['value'].values[0]
                if pd.notna(val) and str(val).strip() != "":
                    try:
                        parsed_val = json.loads(val)
                        if isinstance(parsed_val, dict):
                            tourney_dict.update(parsed_val)
                    except Exception:
                        pass

        # 3. Cargar Mazos (Cols P-Q)
        decks_dict = {}
        if 'deck_name' in df_all.columns:
            for _, row in df_all.iterrows():
                d_name_val = row.get('deck_name')
                if pd.notna(d_name_val) and str(d_name_val).strip() != "":
                    d_name = str(d_name_val).strip()
                    if d_name.lower() != 'deck_name':
                        d_desc = str(row.get('deck_description', 'Sin descripción.')).strip()
                        decks_dict[d_name] = d_desc if d_desc else "Sin descripción."

        if not decks_dict:
            decks_dict = default_decks

        return {"users": users_dict, "tournament": tourney_dict, "decks": decks_dict}

    except Exception:
        return {
            "users": default_users,
            "tournament": default_tourney,
            "decks": default_decks
        }

def save_db(data):
    if not WEBAPP_URL:
        st.warning("⚠️ No se ha configurado la URL de Apps Script (WEBAPP_URL).")
        return

    try:
        headers = ["username", "password", "name", "role", "deck", "reset_requested", "email", "", "", "", "key", "value", "", "", "", "deck_name", "deck_description"]
        
        users_rows = [headers]
        deck_items = list(data["decks"].items())
        u_keys = list(data["users"].keys())
        max_len = max(len(u_keys), 1, len(deck_items))
        
        for i in range(max_len):
            row = [""] * 17
            
            if i < len(u_keys):
                u_id = u_keys[i]
                u_data = data["users"][u_id]
                row[0] = u_id
                row[1] = str(u_data.get("password", ""))
                row[2] = str(u_data.get("name", ""))
                row[3] = str(u_data.get("role", "player"))
                row[4] = str(u_data.get("deck", "Sin mazo asignado"))
                row[5] = "TRUE" if u_data.get("reset_requested") else "FALSE"
                row[6] = str(u_data.get("email", ""))

            if i == 0:
                row[10] = "data"
                row[11] = json.dumps(data["tournament"])

            if i < len(deck_items):
                row[15] = str(deck_items[i][0])
                row[16] = str(deck_items[i][1])

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
db = {"users": db_full["users"], "tournament": db_full["tournament"]}
available_decks = db_full["decks"]
deck_names_list = list(available_decks.keys())

# ==========================================
# LÓGICA DEL TORNEO (RONDA SUIZA)
# ==========================================
def generate_swiss_pairings(db_data):
    t_data = db_data["tournament"]
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

    next_round = t_data["round"] + 1
    t_data["round"] = next_round
    t_data["pairings"][str(next_round)] = pairings
    save_db({"users": db["users"], "tournament": t_data, "decks": available_decks})

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
                        "deck": "Sin mazo asignado",
                        "email": user_email.strip(),
                        "reset_requested": False
                    }
                    save_db({"users": db["users"], "tournament": db["tournament"], "decks": available_decks})
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
                    save_db({"users": db["users"], "tournament": db["tournament"], "decks": available_decks})
                    st.success(f"Solicitud enviada al Administrador. Se notificará al correo registrado: {u_email}")
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
# NAVEGACIÓN PRINCIPAL
# ==========================================
st.title("🏆 Gestión de Torneos One Piece Card Game")

is_logged = st.session_state.logged_user is not None and st.session_state.logged_user in db["users"]
is_admin = False
if is_logged:
    is_admin = db["users"].get(st.session_state.logged_user, {}).get("role") == "admin"

tabs = ["⚔️ Torneos", "📊 Standings", "📜 Historial"]
if is_logged:
    tabs.append("👤 Mi Perfil")
if is_admin:
    tabs.extend(["👥 Gestión de Cuentas", "⚙️ Admin Torneo"])

tab_elements = st.tabs(tabs)

# ------------------------------------------
# TAB 1: TORNEOS
# ------------------------------------------
with tab_elements[0]:
    t_info = db["tournament"]
    
    st.subheader("🎯 Torneo Activo / Próximo Evento")
    
    if t_info.get("status") == "not_started":
        if t_info.get("name"):
            st.success(f"🏆 **Torneo Anunciado:** {t_info['name']}")
            st.info("Las inscripciones están **abiertas**. Inscríbete con tu mazo seleccionado desde tu perfil.")
            
            if is_logged:
                curr_u = st.session_state.logged_user
                in_registered = curr_u in t_info["players"]
                current_deck = db["users"][curr_u].get("deck", "Sin mazo asignado")
                
                st.write("#### Tu Estado en el Torneo")
                st.write(f"Jugador: **{db['users'][curr_u]['name']}** | Mazo registrado: **{current_deck}**")
                
                col_ins1, col_ins2 = st.columns(2)
                with col_ins1:
                    if not in_registered:
                        if st.button("Inscribirme al Torneo", type="primary"):
                            t_info["players"][curr_u] = {
                                "points": 0, "dropped": False, "deck": current_deck, "history": []
                            }
                            save_db({"users": db["users"], "tournament": t_info, "decks": available_decks})
                            st.success("¡Te has inscrito correctamente!")
                            st.rerun()
                    else:
                        st.info("✅ Ya estás inscrito en este torneo.")
                        if st.button("Cancelar mi Inscripción"):
                            del t_info["players"][curr_u]
                            save_db({"users": db["users"], "tournament": t_info, "decks": available_decks})
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
                    registered_list.append({"Jugador": p_name, "Mazo": p_data.get("deck", "Sin mazo")})
                st.dataframe(pd.DataFrame(registered_list), use_container_width=True)
            else:
                st.caption("Aún no hay jugadores inscritos.")
        else:
            st.info("No hay ningún torneo anunciado en este momento. El administrador creará uno próximamente.")

    elif t_info.get("status") in ["active", "finished"]:
        st.write(f"### ⚔️ {t_info['name']} (Ronda {t_info['round']})")
        
        curr_round_str = str(t_info["round"])
        round_matches = t_info["pairings"].get(curr_round_str, [])
        
        st.write("#### Emparejamientos de la Ronda Actual")
        
        for idx, match in enumerate(round_matches):
            p1_name = db["users"].get(match["p1"], {}).get("name", match["p1"])
            
            if match["p2"] is None:
                st.success(f"🔹 **Mesa {idx+1}:** {p1_name} tiene **BYE** (+3 pts)")
                continue

            p2_name = db["users"].get(match["p2"], {}).get("name", match["p2"])
            
            with st.expander(f"Mesa {idx+1}: {p1_name} vs {p2_name} | Estado: {match['result'] or 'Pendiente'}"):
                p1_deck = t_info["players"].get(match["p1"], {}).get("deck", "N/A")
                p2_deck = t_info["players"].get(match["p2"], {}).get("deck", "N/A")
                st.write(f"**{p1_name}** ({p1_deck}) vs **{p2_name}** ({p2_deck})")

                user = st.session_state.logged_user
                if match["result"] is None and (user in [match["p1"], match["p2"]] or is_admin):
                    c1, c2 = st.columns(2)
                    winner = c1.selectbox("Ganador:", [p1_name, p2_name, "Empate"], key=f"win_{t_info['round']}_{idx}")
                    first_player = c2.selectbox("¿Quién inició primero?:", [p1_name, p2_name], key=f"first_{t_info['round']}_{idx}")
                    
                    if st.button("Guardar Resultado", key=f"btn_{t_info['round']}_{idx}"):
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
                        save_db({"users": db["users"], "tournament": t_info, "decks": available_decks})
                        st.rerun()

    st.write("---")
    st.subheader("🏅 Últimos Torneos Realizados")
    past_tourneys = db["tournament"].get("past_tournaments", [])
    if past_tourneys:
        summary_rows = []
        for t in list(reversed(past_tourneys))[:5]:
            summary_rows.append({
                "Torneo": t.get("name", "Torneo"),
                "Ganador 👑": t.get("winner_name", "N/A"),
                "Mazo Ganador 🎴": t.get("winner_deck", "N/A"),
                "Rondas": t.get("total_rounds", "N/A")
            })
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)
    else:
        st.caption("Aún no hay historial de torneos finalizados.")

# ------------------------------------------
# TAB 2: STANDINGS
# ------------------------------------------
with tab_elements[1]:
    st.subheader("📊 Tabla de Posiciones")
    if db["tournament"]["players"]:
        standings_data = []
        for username, pdata in db["tournament"]["players"].items():
            u_info = db["users"].get(username, {})
            standings_data.append({
                "Jugador": u_info.get("name", username),
                "Mazo": pdata.get("deck", "Sin mazo asignado"),
                "Puntos": pdata.get("points", 0),
                "Estado": "DROPPED" if pdata.get("dropped") else "Activo"
            })
        df = pd.DataFrame(standings_data).sort_values(by=["Puntos"], ascending=False).reset_index(drop=True)
        df.index += 1
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Aún no hay jugadores registrados.")

# ------------------------------------------
# TAB 3: HISTORIAL
# ------------------------------------------
with tab_elements[2]:
    st.subheader("📜 Historial de Torneos")
    past_list = db["tournament"].get("past_tournaments", [])
    if past_list:
        for past in reversed(past_list):
            with st.expander(f"🏆 {past['name']} — Ganador: {past.get('winner_name', 'N/A')}"):
                st.write(f"Rondas: {past.get('total_rounds')}")
                st.json(past.get("standings", {}))
    else:
        st.info("No hay torneos pasados.")

# ------------------------------------------
# TAB 4: MI PERFIL
# ------------------------------------------
if is_logged:
    with tab_elements[3]:
        st.subheader("👤 MI PERFIL")
        curr_username = st.session_state.logged_user
        user_data = db["users"][curr_username]
        
        col_prof1, col_prof2 = st.columns(2)
        
        with col_prof1:
            st.write("### ✏️ Información Personal")
            new_name = st.text_input("Nombre Visible / Nick:", value=user_data.get("name", ""))
            new_email = st.text_input("Correo Electrónico registrado:", value=user_data.get("email", ""))
            
            options_deck = ["Sin mazo asignado"] + deck_names_list
            curr_deck_val = user_data.get("deck", "Sin mazo asignado")
            idx_deck = options_deck.index(curr_deck_val) if curr_deck_val in options_deck else 0
            
            selected_deck = st.selectbox("Mazo / Líder Seleccionado:", options=options_deck, index=idx_deck)
            
            st.write("---")
            if selected_deck != "Sin mazo asignado":
                col_img, col_desc = st.columns([1, 2])
                img_path = os.path.join("images", f"{selected_deck}.png")
                with col_img:
                    if os.path.exists(img_path):
                        st.image(img_path, caption=selected_deck, use_column_width=True)
                    else:
                        st.caption(f"ℹ️ (Agrega {selected_deck}.png en /images)")
                with col_desc:
                    st.write("**Descripción del Líder:**")
                    st.info(available_decks.get(selected_deck, "Sin descripción registrada."))
            else:
                st.info("Actualmente estás marcado como 'Sin mazo asignado'.")

            st.write("---")
            if st.button("Guardar Cambios de Perfil"):
                db["users"][curr_username]["name"] = new_name.strip()
                db["users"][curr_username]["email"] = new_email.strip()
                db["users"][curr_username]["deck"] = selected_deck
                save_db({"users": db["users"], "tournament": db["tournament"], "decks": available_decks})
                st.success("Perfil actualizado correctamente.")
                st.rerun()

        with col_prof2:
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
                    save_db({"users": db["users"], "tournament": db["tournament"], "decks": available_decks})
                    st.success("¡Contraseña actualizada con éxito!")
                    st.rerun()
                else:
                    st.error("Las contraseñas no coinciden.")

# ------------------------------------------
# TAB 5: GESTIÓN DE CUENTAS (SOLO ADMINS)
# ------------------------------------------
if is_admin:
    with tab_elements[4]:
        st.subheader("👥 Gestión de Cuentas")
        users_list = []
        for u_id, u_data in db["users"].items():
            users_list.append({
                "Usuario": u_id,
                "Nombre": u_data.get("name", ""),
                "Correo": u_data.get("email", ""),
                "Rol": u_data.get("role", "player"),
                "Mazo": u_data.get("deck", "Sin mazo asignado"),
                "Reset Solicitado": "SÍ" if u_data.get("reset_requested") else "No"
            })
        st.dataframe(pd.DataFrame(users_list), use_container_width=True)

# ------------------------------------------
# TAB 6: ADMIN TORNEO (SOLO ADMINS)
# ------------------------------------------
if is_admin:
    with tab_elements[5]:
        st.subheader("⚙️ Panel de Control de Torneo")
        t_data = db["tournament"]

        # ESTADO 1: No iniciado o listo para anunciar
        if t_data.get("status") == "not_started":
            st.write("### 🆕 Configurar y Anunciar Nuevo Torneo")
            
            # Nombre del torneo (si ya hay uno anunciado se mantiene su valor)
            t_name_input = st.text_input("Nombre del Torneo:", value=t_data.get("name") or "Torneo Semanal OPTCG")
            
            col_adm_btn1, col_adm_btn2 = st.columns(2)
            
            # BOTÓN 1: Anunciar torneo (SIN VALIDACIÓN DE JUGADORES)
            with col_adm_btn1:
                if st.button("📢 Anunciar Torneo (Abrir Inscripciones)"):
                    if not t_name_input.strip():
                        st.error("Por favor escribe un nombre válido para el torneo.")
                    else:
                        t_data["name"] = t_name_input.strip()
                        t_data["status"] = "not_started"
                        t_data["players"] = {}
                        t_data["pairings"] = {}
                        t_data["round"] = 0
                        save_db({"users": db["users"], "tournament": t_data, "decks": available_decks})
                        st.success(f"¡Torneo '{t_name_input}' anunciado con éxito! Las inscripciones están abiertas.")
                        st.rerun()
                    
            # BOTÓN 2: Cerrar inscripciones e iniciar (CON VALIDACIÓN DE MÍNIMO 2 JUGADORES)
            with col_adm_btn2:
                # Solo se habilita el botón si el torneo ya fue anunciado previamente
                if t_data.get("name"):
                    if st.button("🔒 Cerrar Inscripciones e Iniciar R1", type="primary"):
                        current_players = t_data.get("players", {})
                        if len(current_players) < 2:
                            st.error(f"❌ No se puede iniciar el torneo: Hay {len(current_players)} jugador(es) inscrito(s). Se requieren al menos 2.")
                        else:
                            t_data["status"] = "active"
                            generate_swiss_pairings({"users": db["users"], "tournament": t_data, "decks": available_decks})
                            st.success("¡Inscripciones cerradas! Torneo iniciado y Ronda 1 generada.")
                            st.rerun()
                else:
                    st.caption("ℹ️ Primero debes anunciar el torneo para que los jugadores se inscriban.")
                        
            st.write("---")
            st.write(f"👥 **Jugadores Inscritos en Tiempo Real ({len(t_data.get('players', {}))}):**")
            if t_data.get("players"):
                registered_list = []
                for p_id, p_data in t_data["players"].items():
                    p_name = db["users"].get(p_id, {}).get("name", p_id)
                    registered_list.append({"Usuario": p_id, "Nombre": p_name, "Mazo": p_data.get("deck", "Sin mazo")})
                st.dataframe(pd.DataFrame(registered_list), use_container_width=True)
            else:
                st.caption("Aún no hay ningún jugador inscrito en este torneo.")

        # ESTADO 2: Torneo Activo en curso
        elif t_data.get("status") == "active":
            st.write(f"### ⚔️ Torneo en Curso: **{t_data['name']}** (Ronda {t_data['round']})")
            
            curr_r = str(t_data["round"])
            matches = t_data["pairings"].get(curr_r, [])
            pending = [m for m in matches if m["result"] is None and m["p2"] is not None]
            
            if pending:
                st.warning(f"Hay {len(pending)} partida(s) pendiente(s) en esta ronda.")
            else:
                st.success("Todas las partidas de la ronda actual han sido completadas.")
                if st.button("➡️ Generar Siguiente Ronda Suiza", type="primary"):
                    generate_swiss_pairings({"users": db["users"], "tournament": t_data, "decks": available_decks})
                    st.rerun()

            st.write("---")
            if st.button("🏆 Finalizar Torneo Actual", type="primary"):
                t_data["status"] = "finished"
                sorted_p = sorted(t_data["players"].items(), key=lambda x: x[1]["points"], reverse=True)
                winner_user = sorted_p[0][0] if sorted_p else "N/A"
                winner_name = db["users"].get(winner_user, {}).get("name", winner_user)
                winner_deck = t_data["players"].get(winner_user, {}).get("deck", "N/A")
                
                t_data.setdefault("past_tournaments", []).append({
                    "name": t_data["name"],
                    "total_rounds": t_data["round"],
                    "winner_user": winner_user,
                    "winner_name": winner_name,
                    "winner_deck": winner_deck,
                    "standings": t_data["players"]
                })
                
                t_data["status"] = "not_started"
                t_data["name"] = ""
                t_data["round"] = 0
                t_data["players"] = {}
                t_data["pairings"] = {}
                save_db({"users": db["users"], "tournament": t_data, "decks": available_decks})
                st.success("¡Torneo finalizado y guardado en el historial!")
                st.rerun()