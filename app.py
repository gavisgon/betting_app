import streamlit as st
import gspread
from google.oauth2 import service_account
import pandas as pd  
import datetime

@st.cache_resource
def init_connection():
    # Grab your service account info from Streamlit secrets
    creds_dict = dict(st.secrets["gcp_service_account"])
    
    # Automatically clean up the private key formatting so it never fails
    pk = creds_dict["private_key"]
    pk = pk.replace("\\n", "\n") # Fix any escaped newlines
    
    # Ensure the proper header and footer are present
    if not pk.strip().startswith("-----BEGIN PRIVATE KEY-----"):
        pk = "-----BEGIN PRIVATE KEY-----\n" + pk.strip()
    if not pk.strip().endswith("-----END PRIVATE KEY-----"):
        pk = pk.strip() + "\n-----END PRIVATE KEY-----"
        
    creds_dict["private_key"] = pk
    
    # Set up the connection permissions
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    
    creds = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=scope
    )
    client = gspread.authorize(creds)
    return client

client = init_connection()

# Open Google Sheet Worksheets
try:
    sheet = client.open("Sports Betting App Data")
    picks_worksheet = sheet.worksheet("Picks")
    standings_worksheet = sheet.worksheet("Standings")
    parlays_worksheet = sheet.worksheet("Parlays")
except Exception as e:
    st.error(f"Could not connect to Google Sheet. Make sure worksheets exist. Error: {e}")

# --- PLACE load_ref_data RIGHT HERE ---
@st.cache_data(ttl=600)
def load_ref_data(_client):
    sheet = _client.open("Sports Betting App Data").worksheet("Ref_Data")
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# --- HELPER FUNCTIONS FOR ODDS & STANDINGS CALCULATIONS ---
def american_to_decimal(american_odds):
    try:
        odds = float(american_odds)
        if odds > 0:
            return 1.0 + (odds / 100.0)
        else:
            return 1.0 + (100.0 / abs(odds))
    except:
        return 1.0

def decimal_to_american(decimal_odds):
    if decimal_odds >= 2.0:
        return f"+{int(round((decimal_odds - 1.0) * 100))}"
    elif decimal_odds > 1.0:
        return f"-{int(round(100.0 / (decimal_odds - 1.0)))}"
    return "E"

def calculate_user_standings(df_picks, standings_worksheet=None):
    """Calculates live wins, losses, pushes, and win % for each user from the Picks dataframe 
    and syncs the aggregated table to the Standings Google Sheet worksheet."""
    if df_picks.empty:
        return pd.DataFrame()
    
    # Standardize column headers
    df_clean = df_picks.copy()
    df_clean.columns = [str(c).strip().title() for c in df_clean.columns]
    
    # Check for Result or Status column
    res_col = "Result" if "Result" in df_clean.columns else ("Status" if "Status" in df_clean.columns else None)
    
    if "User" not in df_clean.columns or not res_col:
        return pd.DataFrame()

    stats = []
    users = ["Gavin", "Chris", "Edwin"]

    for u in users:
        u_picks = df_clean[df_clean["User"] == u]
        wins = len(u_picks[u_picks[res_col].astype(str).str.strip() == "Win"])
        losses = len(u_picks[u_picks[res_col].astype(str).str.strip() == "Loss"])
        pushes = len(u_picks[u_picks[res_col].astype(str).str.strip() == "Push"])
        total = wins + losses
        win_pct = (wins / total * 100) if total > 0 else 0.0

        stats.append({
            "User": u,
            "Wins": wins,
            "Losses": losses,
            "Pushes": pushes,
            "Win %": f"{win_pct:.1f}%"
        })

    standings_df = pd.DataFrame(stats)

    # Automatically write / overwrite updated table into Google Sheets 'Standings' worksheet tab
    if standings_worksheet is not None and not standings_df.empty:
        try:
            updated_rows = [standings_df.columns.values.tolist()] + standings_df.values.tolist()
            standings_worksheet.clear()
            standings_worksheet.update("A1", updated_rows)
        except Exception as e:
            pass  # Silent fail-safe so app doesn't crash if API latency occurs

    return standings_df

# --- APP LAYOUT CONFIG ---
st.set_page_config(page_title="Sports Betting Tracker", page_icon="🚀", layout="centered")

# Passwords
USER_PASSWORDS = {
    "Gavin": "gavin123",
    "Chris": "chris123",
    "Edwin": "edwin123"
}

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "current_user" not in st.session_state:
    st.session_state.current_user = None

# ==========================================
# LOGIN SCREEN
# ==========================================
if not st.session_state.logged_in:
    st.title("🔒 User Login")
    st.write("Welcome! Please select your profile and enter your password to continue.")
    
    selected_user = st.selectbox("Select User", ["Gavin", "Chris", "Edwin"])
    password_input = st.text_input("Enter Password", type="password")
    
    if st.button("Log In", type="primary", use_container_width=True):
        if password_input == USER_PASSWORDS.get(selected_user):
            st.session_state.logged_in = True
            st.session_state.current_user = selected_user
            st.success(f"Welcome back, {selected_user}!")
            st.rerun()
        else:
            st.error("Incorrect password. Please try again.")

# ==========================================
# MAIN APP CONTENT
# ==========================================
else:
    current_user = st.session_state.current_user
    
    col_title, col_logout = st.columns([3, 1])
    with col_title:
        st.title(f"🚀 Welcome, {current_user}!")
    with col_logout:
        st.write("")
        if st.button("Log Out"):
            st.session_state.logged_in = False
            st.session_state.current_user = None
            st.rerun()

    sports_teams = {
        "NHL": [
            "— Select Team —", "Anaheim Ducks", "Boston Bruins", "Buffalo Sabres", 
            "Calgary Flames", "Carolina Hurricanes", "Chicago Blackhawks", "Colorado Avalanche", 
            "Columbus Blue Jackets", "Dallas Stars", "Detroit Red Wings", "Edmonton Oilers", 
            "Florida Panthers", "Los Angeles Kings", "Minnesota Wild", "Montreal Canadiens", 
            "Nashville Predators", "New Jersey Devils", "New York Islanders", "New York Rangers", 
            "Ottawa Senators", "Philadelphia Flyers", "Pittsburgh Penguins", "San Jose Sharks", 
            "Seattle Kraken", "St. Louis Blues", "Tampa Bay Lightning", "Toronto Maple Leafs", 
            "Utah Hockey Club", "Vancouver Canucks", "Vegas Golden Knights", "Washington Capitals", "Winnipeg Jets"
        ],
        "MLB": [
            "— Select Team —", "Arizona Diamondbacks", "Atlanta Braves", "Baltimore Orioles", 
            "Boston Red Sox", "Chicago Cubs", "Chicago White Sox", "Cincinnati Reds", 
            "Cleveland Guardians", "Colorado Rockies", "Detroit Tigers", "Houston Astros", 
            "Kansas City Royals", "Los Angeles Angels", "Los Angeles Dodgers", "Miami Marlins", 
            "Milwaukee Brewers", "Minnesota Twins", "New York Mets", "New York Yankees", 
            "Oakland Athletics", "Philadelphia Phillies", "Pittsburgh Pirates", "San Diego Padres", 
            "San Francisco Giants", "Seattle Mariners", "St. Louis Cardinals", "Tampa Bay Rays", 
            "Texas Rangers", "Toronto Blue Jays", "Washington Nationals"
        ],
        "NBA": [
            "— Select Team —", "Atlanta Hawks", "Boston Celtics", "Brooklyn Nets", "Charlotte Hornets", 
            "Chicago Bulls", "Cleveland Cavaliers", "Dallas Mavericks", "Denver Nuggets", "Detroit Pistons", 
            "Golden State Warriors", "Houston Rockets", "Indiana Pacers", "Los Angeles Clippers", 
            "Los Angeles Lakers", "Memphis Grizzlies", "Miami Heat", "Milwaukee Bucks", "Minnesota Timberwolves", 
            "New Orleans Pelicans", "New York Knicks", "Oklahoma City Thunder", "Orlando Magic", 
            "Philadelphia 76ers", "Phoenix Suns", "Portland Trail Blazers", "Sacramento Kings", 
            "San Antonio Spurs", "Toronto Raptors", "Utah Jazz", "Washington Wizards"
        ],
        "NFL": [
            "— Select Team —", "Arizona Cardinals", "Atlanta Falcons", "Baltimore Ravens", "Buffalo Bills", 
            "Carolina Panthers", "Chicago Bears", "Cincinnati Bengals", "Cleveland Browns", "Dallas Cowboys", 
            "Denver Broncos", "Detroit Lions", "Green Bay Packers", "Houston Texans", "Indianapolis Colts", 
            "Jacksonville Jaguars", "Kansas City Chiefs", "Las Vegas Raiders", "Los Angeles Chargers", 
            "Los Angeles Rams", "Miami Dolphins", "Minnesota Vikings", "New England Patriots", "New Orleans Saints", 
            "New York Giants", "New York Jets", "Philadelphia Eagles", "Pittsburgh Steelers", "San Francisco 49ers", 
            "Seattle Seahawks", "Tampa Bay Buccaneers", "Tennessee Titans", "Washington Commanders"
        ],
        "CFL": [
            "— Select Team —", "BC Lions", "Calgary Stampeders", "Edmonton Elks", "Saskatchewan Roughriders", 
            "Winnipeg Blue Bombers", "Hamilton Tiger-Cats", "Toronto Argonauts", "Ottawa Redblacks", "Montreal Alouettes"
        ],
        "NCAAF": ["— Select Team —", "Other / Custom Team"],
        "WJHC": ["— Select Team —", "Canada", "USA", "Sweden", "Finland", "Czechia", "Slovakia", "Switzerland", "Germany"],
        "NCAAB": ["— Select Team —", "Other / Custom Team"]
    }

    tab1, tab2, tab3 = st.tabs(["Today's Picks", "Dashboard", "History"])

    # --- TAB 1: TODAY'S PICKS ---
    with tab1:
        today = datetime.date.today()
        
        if current_user == "Gavin":
            override_date = st.checkbox("⚙️ Admin: Change Date (Backdate/Edit)")
            if override_date:
                col_date_input = st.date_input("Date", value=today)
            else:
                col_date_input = today
        else:
            col_date_input = today

        selected_date_str = str(col_date_input)

        # --- ROBUST LOAD PICKS FOR SELECTED DATE ---
        try:
            all_values = picks_worksheet.get_all_values()
            if len(all_values) > 1:
                headers = [str(h).strip() for h in all_values[0]]
                rows = all_values[1:]
                
                # Align columns and rows safely
                df_all_picks = pd.DataFrame(rows, columns=headers[:len(rows[0])] if len(headers) >= len(rows[0]) else headers + [f"Col_{i}" for i in range(len(headers), len(rows[0]))])
                
                # Clean up column header spaces & standardise names
                df_all_picks.columns = [str(c).strip() for c in df_all_picks.columns]
                
                if "Date" in df_all_picks.columns:
                    df_all_picks["Clean_Date"] = df_all_picks["Date"].astype(str).str.strip()
                    date_all_picks = df_all_picks[df_all_picks["Clean_Date"] == selected_date_str.strip()].copy()
                else:
                    date_all_picks = pd.DataFrame()
            else:
                date_all_picks = pd.DataFrame()
        except Exception as e:
            date_all_picks = pd.DataFrame()
            st.error(f"Error loading picks: {e}")


        st.caption(f"📅 **Selected Date:** {selected_date_str}")

        if "editing_pick" not in st.session_state:
            st.session_state.editing_pick = False
        if "pick_submitted_cache" not in st.session_state:
            st.session_state.pick_submitted_cache = {}

        try:
            all_picks_raw = picks_worksheet.get_all_records(numericise_ignore=['all'])
            df_all_picks = pd.DataFrame(all_picks_raw).astype(str) if all_picks_raw else pd.DataFrame()
        except Exception as e:
            df_all_picks = pd.DataFrame()

        try:
            all_parlays_raw = parlays_worksheet.get_all_records(numericise_ignore=['all'])
            df_all_parlays = pd.DataFrame(all_parlays_raw).astype(str) if all_parlays_raw else pd.DataFrame()
        except Exception as e:
            df_all_parlays = pd.DataFrame()

        user_today_pick = pd.DataFrame()
        date_all_picks = pd.DataFrame()
        existing_parlay = pd.DataFrame()
        
        if not df_all_picks.empty:
            date_col = [c for c in df_all_picks.columns if c.strip().lower() == "date"]
            user_col = [c for c in df_all_picks.columns if c.strip().lower() == "user"]
            
            if date_col and user_col:
                d_name = date_col[0]
                u_name = user_col[0]
                date_all_picks = df_all_picks[df_all_picks[d_name] == selected_date_str]
                user_today_pick = date_all_picks[date_all_picks[u_name] == current_user]

        if not df_all_parlays.empty:
            parlay_date_col = [c for c in df_all_parlays.columns if c.strip().lower() == "date"]
            if parlay_date_col:
                existing_parlay = df_all_parlays[df_all_parlays[parlay_date_col[0]] == selected_date_str]

     # SCENARIO 1: PARLAY IS FINALIZED / LOCKED
        if not existing_parlay.empty:
            parlay_info = existing_parlay.iloc[0]
            parlay_status = parlay_info.get('Status', 'Pending')
            
            if parlay_status == "Win":
                st.balloons()
                st.success(f"🎉 **DAILY PARLAY WON!** Total Payout: **${parlay_info.get('Total_Payout', '0.00')}**")
            elif parlay_status == "Loss":
                st.error(f"❌ **DAILY PARLAY LOST** ({selected_date_str})")
            else:
                st.info(f"🔒 **Daily Parlay Locked & In Progress ({selected_date_str})**")
            
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            m_col1.metric("Wager", f"${parlay_info.get('Stake', '3.00')}")
            m_col2.metric("Final Odds", parlay_info.get('Final_Odds', 'N/A'))
            m_col3.metric("Profit Boost", f"{parlay_info.get('Boost_Pct', '0')}")
            m_col4.metric("Total Payout", f"${parlay_info.get('Total_Payout', '0.00')}")

            st.divider()
            
            # 1. Locked Parlay Legs Table
            st.markdown("### 📜 Locked Parlay Legs & Status")
            if not date_all_picks.empty:
                st.dataframe(date_all_picks, use_container_width=True)
            else:
                st.warning("Picks for this parlay exist in history.")

            # 2. Admin Unlock Button (Positioned right below the table)
            if current_user == "Gavin":
                if st.button("🔓 Admin: Unlock & Re-Edit Parlay", type="secondary"):
                    all_p_rows = parlays_worksheet.get_all_values()
                    for idx, r in enumerate(all_p_rows[1:], start=2):
                        if len(r) >= 1 and r[0].strip() == selected_date_str.strip():
                            parlays_worksheet.delete_rows(idx)
                            break
                    st.success("Parlay unlocked!")
                    st.rerun()

            # 3. Live Game Grader (Positioned below the unlock button)
            if current_user == "Gavin":
                st.divider()
                st.subheader("⚡ Live Game Grader & Auto-Calculator")
                form_key = f"grade_picks_form_{selected_date_str}"
                
                with st.form(key=form_key):
                    if not date_all_picks.empty:
                        for idx, row in date_all_picks.iterrows():
                            u_name = row.get("User", row.get("user", f"Leg {idx+1}"))
                            tm_name = row.get("Team") or row.get("Team / Selection") or row.get("Selection") or row.get("Pick") or "Pick"
                            curr_status = str(row.get("Result") or row.get("Status") or "Pending").strip()
                            
                            status_options = ["Pending", "Win", "Loss", "Push", "Void"]
                            default_idx = status_options.index(curr_status) if curr_status in status_options else 0
                            widget_key = f"status_pick_{selected_date_str}_{idx}_{u_name}"
                            
                            st.selectbox(f"Result for {u_name} ({tm_name})", options=status_options, index=default_idx, key=widget_key)

                    st.write("---")
                    parlay_status_options = ["Auto-Calculate", "Win", "Loss", "Void", "Pending"]
                    manual_parlay_override = st.selectbox("Overall Parlay Status", options=parlay_status_options, index=0, key=f"status_parlay_override_{selected_date_str}")

                    if st.form_submit_button("💾 Save Live Results", type="primary", use_container_width=True):
                        updated_statuses = {}
                        leg_odds_data = []
                        
                        for idx, row in date_all_picks.iterrows():
                            u_name = row.get("User", row.get("user", f"Leg {idx+1}"))
                            raw_odds = row.get("Odds", row.get("odds", "-110"))
                            widget_key = f"status_pick_{selected_date_str}_{idx}_{u_name}"
                            selected_stat = st.session_state.get(widget_key, "Pending")
                            updated_statuses[u_name] = selected_stat
                            leg_odds_data.append({"odds": raw_odds, "status": selected_stat})

                        leg_statuses = [item["status"] for item in leg_odds_data]
                        if manual_parlay_override != "Auto-Calculate":
                            final_parlay_status = manual_parlay_override
                        elif "Loss" in leg_statuses:
                            final_parlay_status = "Loss"
                        elif any(s == "Pending" for s in leg_statuses):
                            final_parlay_status = "Pending"
                        elif all(s in ["Push", "Void"] for s in leg_statuses):
                            final_parlay_status = "Void"
                        else:
                            final_parlay_status = "Win"

                        stake_val = float(parlay_info.get("Stake", 3.00))
                        boost_str = str(parlay_info.get("Boost_Pct", "0"))

                        if final_parlay_status == "Loss":
                            calc_payout = 0.00
                            calc_winnings = -stake_val
                            calc_final_odds = "—"
                        elif final_parlay_status == "Pending":
                            calc_payout = float(parlay_info.get("Total_Payout", 0.00))
                            calc_winnings = round(calc_payout - stake_val, 2)
                            calc_final_odds = parlay_info.get("Final_Odds", "—")
                        else:
                            adj_dec_odds = 1.0
                            for leg in leg_odds_data:
                                if leg["status"] == "Win":
                                    adj_dec_odds *= american_to_decimal(leg["odds"])

                            if "%" in boost_str:
                                b_num = float(boost_str.replace("%", "").strip())
                                base_profit = (stake_val * adj_dec_odds) - stake_val
                                boosted_profit = base_profit * (1.0 + (b_num / 100.0))
                                calc_payout = round(stake_val + boosted_profit, 2)
                            elif "+" in boost_str or "$" in boost_str:
                                b_num = float(boost_str.replace("+", "").replace("$", "").strip())
                                calc_payout = round((stake_val * adj_dec_odds) + b_num, 2)
                            else:
                                calc_payout = round(stake_val * adj_dec_odds, 2)

                            calc_winnings = round(calc_payout - stake_val, 2)
                            boosted_dec_odds = calc_payout / stake_val if stake_val > 0 else 1.0
                            calc_final_odds = decimal_to_american(boosted_dec_odds)

                        # Update Picks sheet
                        all_p_rows = picks_worksheet.get_all_values()
                        headers = [h.strip().lower() for h in all_p_rows[0]]
                        status_col_idx = headers.index("result") + 1 if "result" in headers else 8
                        
                        for idx_r, r_val in enumerate(all_p_rows[1:], start=2):
                            if len(r_val) >= 2 and r_val[0].strip() == selected_date_str.strip():
                                leg_user = r_val[1]
                                if leg_user in updated_statuses:
                                    picks_worksheet.update_cell(idx_r, status_col_idx, updated_statuses[leg_user])

                        # Update Parlays sheet & Running Pot
                        all_parl_rows = parlays_worksheet.get_all_values()
                        p_headers = [h.strip().lower() for h in all_parl_rows[0]]
                        p_status_idx = p_headers.index("status") + 1 if "status" in p_headers else 8
                        p_payout_idx = p_headers.index("total_payout") + 1 if "total_payout" in p_headers else 6
                        p_winnings_idx = p_headers.index("winnings") + 1 if "winnings" in p_headers else 7
                        p_odds_idx = p_headers.index("final_odds") + 1 if "final_odds" in p_headers else 5
                        p_pot_idx = p_headers.index("running_pot") + 1 if "running_pot" in p_headers else 9

                        BASE_POT = 101.38
                        running_pot_calc = BASE_POT
                        for idx_pr, pr_val in enumerate(all_parl_rows[1:], start=2):
                            row_date = pr_val[0].strip()
                            row_winnings = calc_winnings if row_date == selected_date_str.strip() else float(pr_val[p_winnings_idx - 1] or 0.0)
                            running_pot_calc += row_winnings
                            
                            if row_date == selected_date_str.strip():
                                parlays_worksheet.update_cell(idx_pr, p_status_idx, final_parlay_status)
                                parlays_worksheet.update_cell(idx_pr, p_payout_idx, f"{calc_payout:.2f}")
                                parlays_worksheet.update_cell(idx_pr, p_winnings_idx, f"{calc_winnings:.2f}")
                                parlays_worksheet.update_cell(idx_pr, p_odds_idx, calc_final_odds)
                                parlays_worksheet.update_cell(idx_pr, p_pot_idx, f"{running_pot_calc:.2f}")
                                break

                        st.success("Successfully saved!")
                        st.rerun()

        # SCENARIO 2: USER SUBMITTED PICK, WAITING/FINALIZING
        elif (not user_today_pick.empty or f"{selected_date_str}_{current_user}" in st.session_state.pick_submitted_cache) and not st.session_state.editing_pick:
            st.success(f"You have submitted your pick for {selected_date_str}.")
            
            st.markdown("### Your Submitted Pick")
            if not user_today_pick.empty:
                st.dataframe(user_today_pick, use_container_width=True)

            col_edit, col_del = st.columns(2)
            with col_edit:
                if st.button("✏️ Edit My Pick", use_container_width=True):
                    st.session_state.editing_pick = True
                    st.rerun()

            with col_del:
                if st.button("🗑️ Delete My Pick", type="secondary", use_container_width=True):
                    all_rows = picks_worksheet.get_all_values()
                    for idx, row in enumerate(all_rows[1:], start=2):
                        if len(row) >= 2 and row[0] == selected_date_str and row[1] == current_user:
                            picks_worksheet.delete_rows(idx)
                            break
                    st.success("Your pick has been deleted.")
                    st.rerun()

            st.divider()

            st.markdown(f"### All Picks for {selected_date_str}")
            if not date_all_picks.empty:
                st.dataframe(date_all_picks, use_container_width=True)
            else:
                st.info("No picks found for this date yet.")

           # --- ADMIN PARLAY FINALIZER SECTION ---
            if current_user == "Gavin":
                st.divider()
                st.subheader("⚡ Admin Parlay Finalizer")
                
                if len(date_all_picks) >= 3:
                    st.info(f"✅ All 3 picks submitted for {selected_date_str}! Ready to lock in.")
                    
                    # 1. Calculate Base Combined Odds
                    combined_dec_odds = 1.0
                    odds_col = [c for c in date_all_picks.columns if c.strip().lower() == "odds"]
                    if odds_col:
                        for o_val in date_all_picks[odds_col[0]]:
                            combined_dec_odds *= american_to_decimal(o_val)

                    base_american_odds = decimal_to_american(combined_dec_odds)

                    # 2. Input Controls (Wager, Boost Type, Boost Value, Base Odds)
                    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
                    
                    with col_f1:
                        stake_input = st.number_input("Wager ($)", value=3.00, step=0.50)
                    
                    with col_f2:
                        boost_type = st.radio("Boost Type", ["Percentage (%)", "Flat Dollar ($)"], horizontal=True)
                    
                    with col_f3:
                        if boost_type == "Percentage (%)":
                            boost_val = st.number_input("Boost (%)", value=0, min_value=0, max_value=500, step=5)
                        else:
                            boost_val = st.number_input("Bonus Payout ($)", value=0.00, min_value=0.00, max_value=100.00, step=0.50)
                    
                    with col_f4:
                        st.text_input("Base Combined Odds", value=base_american_odds, disabled=True)

                    # 3. Compute Boosted Values
                    base_payout = stake_input * combined_dec_odds
                    base_profit = base_payout - stake_input

                    if boost_type == "Percentage (%)":
                        boosted_profit = base_profit * (1.0 + (boost_val / 100.0))
                        total_payout = round(stake_input + boosted_profit, 2)
                        boost_display_str = f"{boost_val}%"
                    else:
                        total_payout = round(base_payout + boost_val, 2)
                        boost_display_str = f"+${boost_val:.2f}"

                    net_winnings = round(total_payout - stake_input, 2)
                    
                    # Effective Decimal & American Odds after Boost
                    boosted_dec_odds = total_payout / stake_input if stake_input > 0 else combined_dec_odds
                    final_american_odds = decimal_to_american(boosted_dec_odds)

                    st.markdown(f"**Final Boosted Odds:** `{final_american_odds}` | **Total Payout:** `${total_payout:.2f}` | **Net Winnings:** `${net_winnings:.2f}`")

                    if st.button("🔒 Finalize & Lock Parlay", type="primary", use_container_width=True):
                        parlay_row = [
                            selected_date_str,
                            str(stake_input),
                            boost_display_str,
                            base_american_odds,
                            final_american_odds,
                            f"{total_payout:.2f}",
                            f"{net_winnings:.2f}",
                            "Pending"
                        ]
                        parlays_worksheet.append_row(parlay_row)
                        st.success(f"Parlay finalized for {selected_date_str}!")
                        st.rerun()
                else:
                    st.warning(f"Waiting for all 3 users to log picks before finalizing ({len(date_all_picks)}/3 picks submitted).")

        # SCENARIO 3: ENTRY FORM
        else:
            if st.session_state.editing_pick:
                st.warning("⚠️ **Edit Mode:** Updating your existing pick.")

            sport = st.selectbox("Sport", list(sports_teams.keys()), key="input_sport")

            sport_bet_types = {
                "NHL": ["Money Line", "Puck Line", "Team Total", "Over/Under", "Game Total", "Player Prop"],
                "NBA": ["Money Line", "Spread", "Team Total", "Over/Under", "Game Total", "Player Prop"],
                "NFL": ["Money Line", "Spread", "Team Total", "Over/Under", "Game Total", "Player Prop"],
                "MLB": ["Money Line", "Run Line", "Team Total", "Over/Under", "Game Total", "Player Prop"],
                "CFL": ["Money Line", "Spread", "Team Total", "Over/Under", "Game Total", "Player Prop"],
                "NCAAF": ["Money Line", "Spread", "Team Total", "Over/Under", "Game Total", "Player Prop"],
                "NCAAB": ["Money Line", "Spread", "Team Total", "Over/Under", "Game Total", "Player Prop"],
                "WJHC": ["Money Line", "Puck Line", "Team Total", "Over/Under", "Game Total", "Player Prop"]
            }
            default_bet_types = ["Money Line", "Spread", "Over/Under", "Player Prop"]
            available_bet_types = sport_bet_types.get(sport, default_bet_types)

            bet_type = st.selectbox("Bet Type", available_bet_types, key="input_bet_type")

            # --- DYNAMIC CONDITIONAL UI FOR PLAYER PROPS VS TEAMS ---
            if bet_type == "Player Prop":
                try:
                    df_ref = load_ref_data(client)
                    df_ref.columns = df_ref.columns.str.strip()
                    df_ref["Sport"] = df_ref["Sport"].astype(str).str.strip().str.upper()
                    df_ref["Player_Name"] = df_ref["Player_Name"].astype(str).str.strip()
                    if "Prop_Type" in df_ref.columns:
                        df_ref["Prop_Type"] = df_ref["Prop_Type"].astype(str).str.strip()

                    current_sport_clean = str(sport).strip().upper()
                    df_sport_players = df_ref[(df_ref["Sport"] == current_sport_clean) & (df_ref["Player_Name"] != "") & (df_ref["Player_Name"].str.lower() != "nan")]
                    available_players = sorted(df_sport_players["Player_Name"].unique().tolist())
                except Exception as e:
                    st.error(f"Error loading Ref_Data: {e}")
                    available_players = []

                if available_players:
                    selected_player = st.selectbox("Select Player", available_players, key="input_player")

                    # Filter rows specifically for the chosen player to get their team and available prop types
                    player_rows = df_sport_players[df_sport_players["Player_Name"] == selected_player]
                    team = player_rows["Team"].values[0] if not player_rows.empty else ""

                    prop_options = sorted([p for p in player_rows["Prop_Type"].unique().tolist() if p and p.lower() != "nan"]) if "Prop_Type" in player_rows.columns else []
                    if not prop_options:
                        prop_options = ["Shots on Goal", "Points", "Anytime Goal Scorer"]

                    selected_prop = st.selectbox("Prop Type", prop_options, key="input_prop_type")
                else:
                    st.warning(f"No players found in Ref_Data sheet for Sport: '{sport}'.")
                    selected_player = ""
                    selected_prop = ""
                    team = ""
            else:
                team = st.selectbox("Team / Selection", sports_teams[sport], key="input_team")
                selected_player = ""
                selected_prop = ""

            spread_options = ["— Select Spread —"]
            for i in range(1, 91):
                spread_options.append(f"+{i * 0.5:g}")
            for i in range(1, 91):
                spread_options.append(f"-{i * 0.5:g}")

            spread_choice = "—"
            ou_choice = "—"
            value = ""

            if bet_type in ["Puck Line", "Run Line"]:
                spread_choice = st.selectbox("Line Option", ["— Select Line —", "-1.5", "+1.5", "-2.5", "+2.5"], key="input_line")
            elif bet_type in ["Spread"]:
                spread_choice = st.selectbox("Spread Line", spread_options, key="input_spread")
            elif bet_type in ["Team Total", "Game Total", "Over/Under", "Player Prop"]:
                ou_choice = st.selectbox("Over / Under", ["Over", "Under"], key="input_ou")
                value = st.text_input("Line Value (e.g., 0.5 SOG or 25.5 Pts)", key="input_val")

            odds = st.number_input("Odds (e.g., -117)", value=-110, key="input_odds")

            st.write("")
            btn_label = "Update Pick" if st.session_state.editing_pick else "Submit Pick"
            
            if st.button(btn_label, use_container_width=True, type="primary"):
                if bet_type == "Player Prop" and not selected_player:
                    st.warning("Please select a valid player.")
                elif bet_type != "Player Prop" and team == "— Select Team —":
                    st.warning("Please select a valid team.")
                elif bet_type in ["Puck Line", "Run Line"] and spread_choice == "— Select Line —":
                    st.warning("Please select a valid Line option (-1.5 / +1.5).")
                elif bet_type == "Spread" and spread_choice == "— Select Spread —":
                    st.warning("Please select a valid Spread line.")
                elif bet_type == "Player Prop" and not value:
                    st.warning("Please enter a line value (e.g., 0.5, 2.5).")
                else:
                    # Format final team/selection and value strings cleanly
                    # Format final team/selection and value strings cleanly
                    if bet_type == "Player Prop":
                        final_team_selection = f"{selected_player} ({selected_prop})"
                        final_value = f"{ou_choice} {value}" if value else ou_choice
                    else:
                        final_team_selection = team
                        final_value = value if value else spread_choice

                    # Build structured row dictionary
                    row_dict = {
                        "Date": selected_date_str,
                        "User": current_user,
                        "Sport": sport,
                        "Bet Type": bet_type,
                        "Team / Selection": final_team_selection,
                        "Over/Under": ou_choice,
                        "Value": final_value,
                        "Odds": str(odds),
                        "Status": "Pending"
                    }
                    row_data = list(row_dict.values())
                    
                    try:
                        # Use existing picks_worksheet variable from top of script
                        if st.session_state.get("editing_pick", False):
                            all_rows = picks_worksheet.get_all_values()
                            for idx, row in enumerate(all_rows[1:], start=2):
                                if len(row) >= 2 and str(row[0]).strip() == selected_date_str.strip() and str(row[1]).strip() == current_user.strip():
                                    picks_worksheet.delete_rows(idx)
                                    break
                            st.session_state.editing_pick = False

                        # Append row using the global worksheet connection
                        picks_worksheet.append_row(row_data)
                        
                        if "pick_submitted_cache" not in st.session_state:
                            st.session_state.pick_submitted_cache = {}
                        st.session_state.pick_submitted_cache[f"{selected_date_str}_{current_user}"] = row_dict
                        
                        st.success(f"Pick successfully submitted for {current_user}!")
                        st.rerun()
                    except Exception as e:
                        if "429" in str(e):
                            st.error("⏳ Google Sheets rate limit reached. Please wait ~30-60 seconds and try submitting again.")
                        else:
                            st.error(f"Error submitting pick: {e}")

            # Cancel Editing Option
            if st.session_state.get("editing_pick", False):
                if st.button("Cancel Editing", use_container_width=True, key=f"cancel_edit_{current_user}_{selected_date_str}"):
                    st.session_state.editing_pick = False
                    st.rerun()

# --- TAB 2: DASHBOARD ---
    with tab2:
        st.header("🏆 Standings & Dashboard")

        # --- SEASON TIMELINE CALCULATOR ---
        from datetime import date
        today_dt = date.today()
        
        # Determine current season start year (October 7th)
        if today_dt.month >= 10 and today_dt.day >= 7:
            season_start = date(today_dt.year, 10, 7)
            season_end = date(today_dt.year + 1, 6, 30)
        elif today_dt.month < 10 or (today_dt.month == 10 and today_dt.day < 7):
            season_start = date(today_dt.year - 1, 10, 7)
            season_end = date(today_dt.year, 6, 30)
            
        total_season_days = (season_end - season_start).days
        days_elapsed = max(0, (today_dt - season_start).days)
        days_remaining = max(0, (season_end - today_dt).days)
        season_progress_pct = min(1.0, max(0.0, days_elapsed / total_season_days if total_season_days > 0 else 0))

        # Simplified Header Banner
        st.subheader(f"📅 Season Start: {season_start.strftime('%b %d, %Y')}")
        

    # 1. GROUP PARLAY STANDINGS & LOSERVILLE POT
        
        BASE_POT = 101.38  # Initial starting baseline pot amount
        
        try:
            parl_raw = parlays_worksheet.get_all_records(numericise_ignore=['all'])
            df_parlays_master = pd.DataFrame(parl_raw)
            
            if not df_parlays_master.empty:
                df_parlays_master.columns = [str(c).strip().title() for c in df_parlays_master.columns]
                
                status_col = "Status" if "Status" in df_parlays_master.columns else None
                win_col = "Winnings" if "Winnings" in df_parlays_master.columns else None
                
                if status_col:
                    # Filter for completed parlays (exclude pending)
                    completed_parlays = df_parlays_master[df_parlays_master[status_col].astype(str).str.strip().isin(["Win", "Loss", "Void"])]
                    p_wins = len(completed_parlays[completed_parlays[status_col].astype(str).str.strip() == "Win"])
                    p_losses = len(completed_parlays[completed_parlays[status_col].astype(str).str.strip() == "Loss"])
                    
                    if win_col and not completed_parlays.empty:
                        # Convert winnings to numeric floats
                        winnings_series = pd.to_numeric(completed_parlays[win_col], errors='coerce').fillna(0.0)
                        net_profit = winnings_series.sum()
                        
                        # Get the most recent parlay change for the pot delta badge
                        last_parlay_change = winnings_series.iloc[-1]
                    else:
                        net_profit = 0.0
                        last_parlay_change = 0.0

                    # Calculate total pot including starting baseline
                    current_pot_total = round(BASE_POT + net_profit, 2)

                    # Format last result delta string cleanly (+ $X.XX or -$X.XX)
                    if last_parlay_change > 0:
                        delta_str = f"+${last_parlay_change:.2f} (Last Result)"
                    elif last_parlay_change < 0:
                        delta_str = f"-${abs(last_parlay_change):.2f} (Last Result)"
                    else:
                        delta_str = "$0.00 (Last Result)"

                    # Display Top Key Metrics
                    col_stat1, col_stat2, col_stat3 = st.columns(3)
                    col_stat1.metric("Parlay Record", f"{p_wins}W - {p_losses}L")
                    col_stat2.metric("Total Group Net Profit", f"${net_profit:.2f}")
                    
                    # Passing exact float to `delta` guarantees correct RED for negative and GREEN for positive
                    col_stat3.metric(
                        "Total Loserville Pot", 
                        f"${current_pot_total:.2f}", 
                        delta=delta_str,
                        delta_color="normal" # Green for positive, Red for negative
                    )

                else:
                    st.metric("Total Loserville Pot", f"${BASE_POT:.2f}")
            else:
                st.metric("Total Loserville Pot", f"${BASE_POT:.2f}")
                st.info("No finalized parlays found yet.")
                
        except Exception as e:
            st.metric("Total Loserville Pot", f"${BASE_POT:.2f}")
            st.info("Finalize parlays to track overall group standings and pot updates.")

        # 2. INDIVIDUAL USER STANDINGS
        st.subheader("👤 Individual User Performance")
        try:
            all_picks_raw = picks_worksheet.get_all_records(numericise_ignore=['all'])
            df_picks_master = pd.DataFrame(all_picks_raw)
            
            # Calculates standings & syncs to Google Sheets tab automatically
            user_standings_df = calculate_user_standings(df_picks_master, standings_worksheet=standings_worksheet)
            
            if not user_standings_df.empty:
                st.table(user_standings_df)
            else:
                st.info("No completed pick records found yet.")
        except Exception as e:
            st.info("Log picks and save results to view live user standings.")

        st.divider()

    

 # --- TAB 3: HISTORY & PAST RESULTS ---
    with tab3:
        st.header("📜 History & Past Results")

        # --- PAST SEASONS HALL OF FAME SUMMARY ---
        with st.expander("🏛️ View Past Seasons Summary (2024 & 2025)", expanded=True):
            col_2024, col_2025 = st.columns(2)
            
            with col_2024:
                st.subheader("🗓️ 2024 Season")
                df_2024 = pd.DataFrame([
                    {"User": "Edwin", "Wins": 67, "Losses": 52, "Push": 2, "Win %": "56.3%"},
                    {"User": "Chris", "Wins": 59, "Losses": 61, "Push": 1, "Win %": "49.2%"},
                    {"User": "Gavin", "Wins": 70, "Losses": 47, "Push": 4, "Win %": "59.8%"},
                    {"User": "Parlay", "Wins": 27, "Losses": 94, "Push": 0, "Win %": "22.3%"}
                ])
                st.table(df_2024)
                st.metric("2024 Net Profit", "$210.24")

            with col_2025:
                st.subheader("🗓️ 2025 Season")
                df_2025 = pd.DataFrame([
                    {"User": "Edwin", "Wins": 70, "Losses": 72, "Push": 3, "Win %": "49.3%"},
                    {"User": "Chris", "Wins": 63, "Losses": 79, "Push": 3, "Win %": "44.4%"},
                    {"User": "Gavin", "Wins": 79, "Losses": 63, "Push": 3, "Win %": "55.6%"},
                    {"User": "Parlay", "Wins": 21, "Losses": 124, "Push": 0, "Win %": "14.5%"}
                ])
                st.table(df_2025)
                st.metric("2025 Net Profit", "$199.44")

        st.divider()

        # --- CURRENT SEASON MASTER LOG & ADMIN EDITOR ---
        st.subheader("📋 Active Season Picks Log")
        try:
            all_picks = picks_worksheet.get_all_records(numericise_ignore=['all'])
            if all_picks:
                df_picks = pd.DataFrame(all_picks).astype(str)
                
                if current_user == "Gavin":
                    st.success("🛠️ **Admin Mode Active:** You can edit cell values directly in the table below and click 'Save Changes'.")
                    
                    edited_df = st.data_editor(
                        df_picks, 
                        num_rows="dynamic", 
                        use_container_width=True,
                        key="admin_picks_data_editor",
                        column_config={
                            col: st.column_config.TextColumn(col) for col in df_picks.columns
                        }
                    )
                    
                    if st.button("💾 Save Changes to Google Sheets", type="primary", key="save_admin_picks_btn"):
                        updated_rows = [edited_df.columns.values.tolist()] + edited_df.values.tolist()
                        picks_worksheet.clear()
                        picks_worksheet.update("A1", updated_rows)
                        st.success("Google Sheet successfully updated!")
                        st.rerun()
                else:
                    st.dataframe(df_picks, use_container_width=True)
            else:
                st.write("No picks logged yet.")
        except Exception as e:
            st.write("Could not load history records yet.")

        # --- PARLAYS MASTER LOG ---
        st.divider()
        st.subheader("🎰 Active Season Daily Parlays Log")
        try:
            all_parlays = parlays_worksheet.get_all_records(numericise_ignore=['all'])
            if all_parlays:
                df_parlays_log = pd.DataFrame(all_parlays).astype(str)
                st.dataframe(df_parlays_log, use_container_width=True)
            else:
                st.write("No daily parlays logged yet.")
        except Exception as e:
            st.write("Could not load parlay records yet.")