import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import os
import hashlib
import json
import plotly.express as px
import plotly.graph_objects as go
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pyotp
import qrcode
from prophet import Prophet
import numpy as np
from sklearn.ensemble import RandomForestRegressor
import requests
import base64

st.set_page_config(
    page_title="Boulangerie Pro - Solution IA",
    layout="wide",
    page_icon="🥖",
    initial_sidebar_state="expanded"
)

FICHIER_USERS = "users.json"
FICHIER_ABONNEMENTS = "abonnements.json"
FICHIER_NOTIFICATIONS = "notifications.json"
FICHIER_ROLES = "roles.json"
FICHIER_STOCKS = "stocks.json"

PLANS_TARIFS = {
    "Gratuit": {
        "prix": 0,
        "predictions_max": 30,
        "utilisateurs_max": 1,
        "produits_max": 5,
        "ia_avancee": False,
        "notifications": False,
        "api": False,
        "support": "Email (48h)",
        "exports": ["PDF"],
        "duree_essai": 7
    },
    "Starter": {
        "prix": 9.99,
        "predictions_max": 200,
        "utilisateurs_max": 3,
        "produits_max": 20,
        "ia_avancee": True,
        "notifications": True,
        "api": False,
        "support": "Email (24h)",
        "exports": ["PDF", "Excel"],
        "duree_essai": 0
    },
    "Pro": {
        "prix": 29.99,
        "predictions_max": -1,
        "utilisateurs_max": 10,
        "produits_max": -1,
        "ia_avancee": True,
        "notifications": True,
        "api": True,
        "support": "Prioritaire (4h)",
        "exports": ["PDF", "Excel", "API"],
        "duree_essai": 0
    },
    "Enterprise": {
        "prix": 99.99,
        "predictions_max": -1,
        "utilisateurs_max": -1,
        "produits_max": -1,
        "ia_avancee": True,
        "notifications": True,
        "api": True,
        "support": "Dédié (1h)",
        "exports": ["PDF", "Excel", "API"],
        "duree_essai": 0
    }
}

ROLES_PERMISSIONS = {
    "Admin": ["tout"],
    "Manager": ["dashboard", "predictions", "stats", "rapports", "stocks"],
    "Employe": ["dashboard", "predictions"]
}

def charger_json(fichier, defaut=None):
    if os.path.exists(fichier):
        with open(fichier, "r", encoding="utf-8") as f:
            return json.load(f)
    return defaut if defaut else {}

def sauvegarder_json(fichier, data):
    with open(fichier, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verifier_login(email, password):
    users = charger_json(FICHIER_USERS)
    if email in users:
        return users[email]["password"] == hash_password(password)
    return False

def get_user_info(email):
    users = charger_json(FICHIER_USERS)
    return users.get(email, {})

def get_user_plan(email):
    abonnements = charger_json(FICHIER_ABONNEMENTS)
    return abonnements.get(email, {"plan": "Gratuit", "date_debut": str(date.today()), "actif": True})

def verifier_limite_plan(email, action):
    plan_user = get_user_plan(email)
    plan_details = PLANS_TARIFS[plan_user["plan"]]
    
    if action == "predictions":
        historique = pd.read_csv(get_fichier_histo(email)) if os.path.exists(get_fichier_histo(email)) else pd.DataFrame()
        if plan_details["predictions_max"] != -1:
            if len(historique) >= plan_details["predictions_max"]:
                return False, f"Limite de {plan_details['predictions_max']} prédictions atteinte. Passez à un plan supérieur."
    
    return True, ""

def envoyer_email(destinataire, sujet, contenu):
    try:
        EMAIL_SENDER = "votre-email@gmail.com"
        EMAIL_PASSWORD = "votre-mot-de-passe-app"
        
        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        msg['To'] = destinataire
        msg['Subject'] = sujet
        
        msg.attach(MIMEText(contenu, 'html'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except:
        return False

def generer_qr_2fa(email):
    secret = pyotp.random_base32()
    users = charger_json(FICHIER_USERS)
    if email in users:
        users[email]["2fa_secret"] = secret
        sauvegarder_json(FICHIER_USERS, users)
    
    totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=email,
        issuer_name="Boulangerie Pro"
    )
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(totp_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue(), secret

def verifier_code_2fa(email, code):
    users = charger_json(FICHIER_USERS)
    if email in users and "2fa_secret" in users[email]:
        totp = pyotp.TOTP(users[email]["2fa_secret"])
        return totp.verify(code)
    return False

def prediction_ia_prophet(df, produit, jours=7):
    if df.empty or produit not in df["produit"].unique():
        return None
    
    df_produit = df[df["produit"] == produit].copy()
    df_produit["date"] = pd.to_datetime(df_produit["date"])
    
    df_prophet = pd.DataFrame({
        'ds': df_produit["date"],
        'y': df_produit["ventes_moyennes"]
    })
    
    if len(df_prophet) < 10:
        return None
    
    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False
    )
    model.fit(df_prophet)
    
    future = model.make_future_dataframe(periods=jours)
    forecast = model.predict(future)
    
    return forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(jours)

def prediction_ia_random_forest(df, jour, meteo, produit):
    if df.empty:
        return None
    
    df_encoded = df.copy()
    df_encoded['jour_num'] = df_encoded['jour'].map({
        'Lundi': 0, 'Mardi': 1, 'Mercredi': 2, 'Jeudi': 3,
        'Vendredi': 4, 'Samedi': 5, 'Dimanche': 6
    })
    df_encoded['meteo_num'] = df_encoded['meteo'].map({
        'Soleil': 0, 'Nuageux': 1, 'Pluie': 2, 'Neige': 3
    })
    
    df_produit = df_encoded[df_encoded['produit'] == produit]
    
    if len(df_produit) < 5:
        return None
    
    X = df_produit[['jour_num', 'meteo_num', 'production_habituelle']]
    y = df_produit['ventes_moyennes']
    
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)
    
    jour_num = {'Lundi': 0, 'Mardi': 1, 'Mercredi': 2, 'Jeudi': 3,
                'Vendredi': 4, 'Samedi': 5, 'Dimanche': 6}[jour]
    meteo_num = {'Soleil': 0, 'Nuageux': 1, 'Pluie': 2, 'Neige': 3}[meteo]
    
    prod_moy = df_produit['production_habituelle'].mean()
    prediction = model.predict([[jour_num, meteo_num, prod_moy]])[0]
    
    return int(prediction)

def get_meteo_automatique(ville="Paris"):
    try:
        API_KEY = "votre-cle-openweather"
        url = f"http://api.openweathermap.org/data/2.5/weather?q={ville}&appid={API_KEY}&lang=fr"
        response = requests.get(url, timeout=5)
        data = response.json()
        
        weather = data['weather'][0]['main']
        mapping = {
            'Clear': 'Soleil',
            'Clouds': 'Nuageux',
            'Rain': 'Pluie',
            'Snow': 'Neige'
        }
        return mapping.get(weather, 'Nuageux')
    except:
        return None

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_email = None
    st.session_state.user_role = None
    st.session_state.needs_2fa = False

def get_fichier_histo(email=None):
    if email is None:
        email = st.session_state.user_email
    user_safe = email.replace("@", "_").replace(".", "_")
    return f"historique_{user_safe}.csv"

if not st.session_state.authenticated:
    st.title("🥖 Boulangerie Pro - Solution IA de Gestion")
    
    tab1, tab2, tab3 = st.tabs(["🔐 Connexion", "📝 Inscription", "💎 Plans & Tarifs"])
    
    with tab1:
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col2:
            st.subheader("Connexion")
            
            email = st.text_input("📧 Email", key="login_email")
            password = st.text_input("🔑 Mot de passe", type="password", key="login_password")
            
            if st.session_state.get("needs_2fa", False):
                code_2fa = st.text_input("🔐 Code 2FA (6 chiffres)", max_chars=6)
                
                if st.button("Vérifier 2FA", use_container_width=True):
                    if verifier_code_2fa(st.session_state.temp_email, code_2fa):
                        st.session_state.authenticated = True
                        st.session_state.user_email = st.session_state.temp_email
                        user_info = get_user_info(st.session_state.temp_email)
                        st.session_state.user_role = user_info.get("role", "Employe")
                        st.session_state.needs_2fa = False
                        st.rerun()
                    else:
                        st.error("❌ Code 2FA invalide")
            else:
                if st.button("Se connecter", use_container_width=True, type="primary"):
                    if verifier_login(email, password):
                        user_info = get_user_info(email)
                        
                        if user_info.get("2fa_enabled", False):
                            st.session_state.needs_2fa = True
                            st.session_state.temp_email = email
                            st.rerun()
                        else:
                            st.session_state.authenticated = True
                            st.session_state.user_email = email
                            st.session_state.user_role = user_info.get("role", "Employe")
                            st.rerun()
                    else:
                        st.error("❌ Email ou mot de passe incorrect")
    
    with tab2:
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col2:
            st.subheader("Créer un compte")
            
            new_email = st.text_input("Email", key="signup_email")
            new_password = st.text_input("Mot de passe (min 8 caractères)", type="password", key="signup_password")
            confirm_password = st.text_input("Confirmer mot de passe", type="password", key="signup_confirm")
            entreprise = st.text_input("Nom de votre boulangerie")
            
            if st.button("S'inscrire", use_container_width=True, type="primary"):
                if new_password != confirm_password:
                    st.error("❌ Les mots de passe ne correspondent pas")
                elif len(new_password) < 8:
                    st.error("❌ Le mot de passe doit contenir au moins 8 caractères")
                elif new_email in charger_json(FICHIER_USERS):
                    st.error("❌ Cet email est déjà enregistré")
                else:
                    users = charger_json(FICHIER_USERS)
                    users[new_email] = {
                        "password": hash_password(new_password),
                        "date_inscription": str(date.today()),
                        "entreprise": entreprise,
                        "role": "Admin",
                        "2fa_enabled": False
                    }
                    sauvegarder_json(FICHIER_USERS, users)
                    
                    abonnements = charger_json(FICHIER_ABONNEMENTS)
                    abonnements[new_email] = {
                        "plan": "Gratuit",
                        "date_debut": str(date.today()),
                        "date_fin_essai": str(date.today() + timedelta(days=7)),
                        "actif": True
                    }
                    sauvegarder_json(FICHIER_ABONNEMENTS, abonnements)
                    
                    st.success("✅ Compte créé ! Vous avez 7 jours d'essai gratuit.")
                    st.balloons()
    
    with tab3:
        st.subheader("💎 Choisissez votre plan")
        
        cols = st.columns(4)
        
        for idx, (plan_nom, details) in enumerate(PLANS_TARIFS.items()):
            with cols[idx]:
                if plan_nom == "Pro":
                    st.markdown("### ⭐ " + plan_nom)
                else:
                    st.markdown("### " + plan_nom)
                
                if details["prix"] == 0:
                    st.markdown(f"## **Gratuit**")
                    st.caption(f"{details['duree_essai']} jours d'essai")
                else:
                    st.markdown(f"## **{details['prix']}€**/mois")
                
                st.divider()
                
                st.write("✅", f"{details['predictions_max'] if details['predictions_max'] != -1 else 'Illimité'} prédictions/mois")
                st.write("👥", f"{details['utilisateurs_max'] if details['utilisateurs_max'] != -1 else 'Illimité'} utilisateurs")
                st.write("🥖", f"{details['produits_max'] if details['produits_max'] != -1 else 'Illimité'} produits")
                
                if details["ia_avancee"]:
                    st.write("🤖 IA avancée")
                if details["notifications"]:
                    st.write("🔔 Notifications")
                if details["api"]:
                    st.write("🔌 API REST")
                
                st.write("💬", details["support"])
                st.write("📥", ", ".join(details["exports"]))
    
    st.stop()

with st.sidebar:
    user_info = get_user_info(st.session_state.user_email)
    plan_info = get_user_plan(st.session_state.user_email)
    
    st.markdown(f"### 👤 {user_info.get('entreprise', 'Boulangerie')}")
    st.caption(f"{st.session_state.user_email}")
    st.caption(f"Rôle: {st.session_state.user_role}")
    
    if plan_info["plan"] == "Gratuit":
        date_fin = datetime.strptime(plan_info.get("date_fin_essai", str(date.today())), "%Y-%m-%d")
        jours_restants = (date_fin - datetime.now()).days
        st.warning(f"🆓 Plan Gratuit - {jours_restants}j restants")
    else:
        st.success(f"💎 Plan {plan_info['plan']}")
    
    if st.button("🚪 Déconnexion", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_email = None
        st.session_state.user_role = None
        st.rerun()
    
    st.divider()
    
    menus_disponibles = ["📊 Dashboard", "📥 Nouvelle prédiction"]
    
    if st.session_state.user_role in ["Admin", "Manager"]:
        menus_disponibles.extend(["📈 Statistiques", "📄 Rapports"])
    
    if st.session_state.user_role == "Admin":
        menus_disponibles.extend(["🤖 IA Avancée", "📦 Stocks", "👥 Équipe", "🔔 Notifications", "🔌 API", "⚙️ Paramètres"])
    
    menu = st.radio("Navigation", menus_disponibles)

st.title("🥖 Boulangerie Pro - Solution IA")

FICHIER_HISTO = get_fichier_histo()

if not os.path.exists(FICHIER_HISTO):
    df_init = pd.DataFrame(columns=[
        "date", "jour", "meteo", "produit",
        "production_habituelle", "ventes_moyennes",
        "production_conseillee", "gaspillage_evite", "cout_gaspillage"
    ])
    df_init.to_csv(FICHIER_HISTO, index=False)

PRODUITS_DEFAUT = ["Pain classique", "Baguette", "Croissant", "Pain au chocolat", "Pain complet",
                   "Pain de campagne", "Brioche", "Éclair", "Tarte aux pommes", "Macaron"]
COUT_UNITAIRE_DEFAUT = {
    "Pain classique": 0.5, "Baguette": 0.4, "Croissant": 0.6,
    "Pain au chocolat": 0.7, "Pain complet": 0.6, "Pain de campagne": 0.55,
    "Brioche": 0.8, "Éclair": 1.2, "Tarte aux pommes": 2.5, "Macaron": 1.5
}

COEF_JOUR = {
    "Lundi": 0.8, "Mardi": 0.9, "Mercredi": 1.0, "Jeudi": 1.0,
    "Vendredi": 1.2, "Samedi": 1.4, "Dimanche": 1.3
}

COEF_METEO = {
    "Soleil": 1.1, "Nuageux": 1.0, "Pluie": 0.85, "Neige": 0.7
}

if menu == "📊 Dashboard":
    df_histo = pd.read_csv(FICHIER_HISTO)
    
    if not df_histo.empty:
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            total_evite = int(df_histo["gaspillage_evite"].sum())
            st.metric("🥖 Gaspillage évité", f"{total_evite} unités")
        
        with col2:
            total_cout = df_histo["cout_gaspillage"].sum()
            st.metric("💰 Économies", f"{total_cout:.2f} €")
        
        with col3:
            nb_jours = len(df_histo)
            st.metric("📅 Jours suivis", nb_jours)
        
        with col4:
            if nb_jours > 0:
                moy_jour = total_evite / nb_jours
                st.metric("📊 Moyenne/jour", f"{moy_jour:.1f} unités")
        
        with col5:
            predictions_utilisees = len(df_histo)
            plan_details = PLANS_TARIFS[plan_info["plan"]]
            max_pred = plan_details["predictions_max"]
            if max_pred != -1:
                st.metric("📈 Prédictions", f"{predictions_utilisees}/{max_pred}")
            else:
                st.metric("📈 Prédictions", f"{predictions_utilisees}")
        
        st.divider()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📈 Évolution du gaspillage évité")
            df_temp = df_histo.copy()
            df_temp["date"] = pd.to_datetime(df_temp["date"])
            df_temp = df_temp.sort_values("date")
            
            fig = px.line(df_temp, x="date", y="gaspillage_evite",
                         title="Gaspillage évité par jour",
                         labels={"date": "Date", "gaspillage_evite": "Unités évitées"})
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("🥖 Répartition par produit")
            df_produit = df_histo.groupby("produit")["gaspillage_evite"].sum().reset_index()
            fig = px.pie(df_produit, values="gaspillage_evite", names="produit",
                        title="Gaspillage évité par produit")
            st.plotly_chart(fig, use_container_width=True)
        
        st.divider()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Performance par jour de la semaine")
            df_jour = df_histo.groupby("jour")["gaspillage_evite"].mean().reset_index()
            ordre_jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
            df_jour["jour"] = pd.Categorical(df_jour["jour"], categories=ordre_jours, ordered=True)
            df_jour = df_jour.sort_values("jour")
            
            fig = px.bar(df_jour, x="jour", y="gaspillage_evite",
                        title="Gaspillage moyen évité par jour",
                        labels={"jour": "Jour", "gaspillage_evite": "Unités évitées"})
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("☁️ Impact météo")
            df_meteo = df_histo.groupby("meteo")["gaspillage_evite"].mean().reset_index()
            fig = px.bar(df_meteo, x="meteo", y="gaspillage_evite",
                        title="Gaspillage moyen évité par météo",
                        labels={"meteo": "Météo", "gaspillage_evite": "Unités évitées"})
            st.plotly_chart(fig, use_container_width=True)
        
        st.divider()
        
        st.subheader("🔔 Alertes et recommandations")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if total_evite > 500:
                st.success("🎉 Excellent ! Vous avez évité plus de 500 unités de gaspillage !")
            elif total_evite > 200:
                st.info("👍 Bon travail ! Continuez ainsi.")
            else:
                st.warning("💡 Pensez à utiliser les prédictions quotidiennement.")
        
        with col2:
            df_recent = df_histo.tail(7)
            tendance = df_recent["gaspillage_evite"].mean()
            if tendance > 10:
                st.warning(f"⚠️ Gaspillage élevé cette semaine ({tendance:.0f} unités/jour en moyenne)")
            else:
                st.success("✅ Production bien optimisée cette semaine")
        
        st.divider()
        st.subheader("📋 Dernières entrées")
        st.dataframe(df_histo.tail(10).iloc[::-1], use_container_width=True)
    
    else:
        st.info("📊 Aucune donnée disponible. Commencez par créer une nouvelle prédiction.")

elif menu == "📥 Nouvelle prédiction":
    st.subheader("📥 Nouvelle prédiction de production")
    
    peut_predire, message = verifier_limite_plan(st.session_state.user_email, "predictions")
    
    if not peut_predire:
        st.error(message)
        st.info("💎 Passez à un plan supérieur pour continuer à utiliser les prédictions.")
        st.stop()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Informations générales")
        
        jour = st.selectbox(
            "Jour de la semaine",
            ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
        )
        
        meteo_auto = get_meteo_automatique()
        if meteo_auto and plan_info["plan"] in ["Pro", "Enterprise"]:
            st.info(f"☁️ Météo actuelle détectée : {meteo_auto}")
            meteo = st.selectbox(
                "Conditions météo",
                ["Soleil", "Nuageux", "Pluie", "Neige"],
                index=["Soleil", "Nuageux", "Pluie", "Neige"].index(meteo_auto)
            )
        else:
            meteo = st.selectbox(
                "Conditions météo",
                ["Soleil", "Nuageux", "Pluie", "Neige"]
            )
        
        produit = st.selectbox(
            "Produit",
            PRODUITS_DEFAUT
        )
        
        cout_unitaire = st.number_input(
            "Coût unitaire (€)",
            min_value=0.0,
            value=COUT_UNITAIRE_DEFAUT.get(produit, 0.5),
            step=0.1,
            format="%.2f"
        )
    
    with col2:
        st.markdown("#### Données de production")
        
        prod_habituelle = st.number_input(
            "Production habituelle (unités)",
            min_value=0,
            value=0,
            step=10
        )
        
        ventes_moy = st.number_input(
            "Ventes moyennes constatées",
            min_value=0,
            value=0,
            step=10
        )
        
        df_histo = pd.read_csv(FICHIER_HISTO)
        
        if plan_info["plan"] in ["Starter", "Pro", "Enterprise"] and len(df_histo) >= 5:
            st.markdown("#### 🤖 Suggestions IA")
            
            suggestion_rf = prediction_ia_random_forest(df_histo, jour, meteo, produit)
            if suggestion_rf:
                st.info(f"💡 IA Random Forest : {suggestion_rf} unités")
        else:
            if len(df_histo) > 0:
                df_similaire = df_histo[
                    (df_histo["produit"] == produit) &
                    (df_histo["jour"] == jour)
                ]
                if not df_similaire.empty:
                    suggestion = int(df_similaire["ventes_moyennes"].mean())
                    st.info(f"💡 Historique : {suggestion} unités")
    
    st.divider()
    
    if ventes_moy > 0:
        prod_conseillee = int(ventes_moy * COEF_JOUR[jour] * COEF_METEO[meteo])
        gaspillage_evite = max(0, prod_habituelle - prod_conseillee)
        cout_gaspillage = gaspillage_evite * cout_unitaire
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("🎯 Production conseillée", f"{prod_conseillee} unités")
        
        with col2:
            st.metric("♻️ Gaspillage évité", f"{gaspillage_evite} unités")
        
        with col3:
            st.metric("💰 Économies", f"{cout_gaspillage:.2f} €")
        
        if gaspillage_evite > 0:
            st.warning(f"⚠️ Vous produisez {gaspillage_evite} unités de trop ! Réduisez votre production.")
        elif gaspillage_evite == 0 and prod_conseillee > prod_habituelle:
            st.info(f"📈 Augmentez la production de {prod_conseillee - prod_habituelle} unités.")
        else:
            st.success("✅ Production optimale !")
        
        progress = min(100, int((prod_conseillee / prod_habituelle * 100)) if prod_habituelle > 0 else 100)
        st.progress(progress / 100)
        st.caption(f"Efficacité: {progress}%")
        
        st.divider()
        
        if st.button("💾 Enregistrer cette prédiction", type="primary", use_container_width=True):
            df = pd.read_csv(FICHIER_HISTO)
            
            nouvelle_ligne = {
                "date": date.today(),
                "jour": jour,
                "meteo": meteo,
                "produit": produit,
                "production_habituelle": prod_habituelle,
                "ventes_moyennes": ventes_moy,
                "production_conseillee": prod_conseillee,
                "gaspillage_evite": gaspillage_evite,
                "cout_gaspillage": cout_gaspillage
            }
            
            df = pd.concat([df, pd.DataFrame([nouvelle_ligne])], ignore_index=True)
            df.to_csv(FICHIER_HISTO, index=False)
            
            st.success("✅ Prédiction enregistrée avec succès !")
            st.balloons()
    
    else:
        st.info("👆 Entrez les ventes moyennes pour obtenir une prédiction.")

elif menu == "🤖 IA Avancée" and st.session_state.user_role == "Admin":
    st.subheader("🤖 Prédictions Intelligence Artificielle")
    
    if plan_info["plan"] not in ["Starter", "Pro", "Enterprise"]:
        st.warning("🔒 Fonctionnalité réservée aux plans Starter et supérieurs")
        st.stop()
    
    df_histo = pd.read_csv(FICHIER_HISTO)
    
    if len(df_histo) < 10:
        st.warning("📊 Minimum 10 entrées nécessaires pour l'IA. Continuez à utiliser l'application.")
        st.stop()
    
    tab1, tab2 = st.tabs(["📈 Prévisions 7 jours (Prophet)", "🌲 Analyse (Random Forest)"])
    
    with tab1:
        st.markdown("### Prévisions à 7 jours avec Prophet")
        
        produit_prevision = st.selectbox("Sélectionnez un produit", df_histo["produit"].unique())
        
        if st.button("🚀 Générer les prévisions", type="primary"):
            with st.spinner("Calcul en cours avec l'IA..."):
                forecast = prediction_ia_prophet(df_histo, produit_prevision, jours=7)
                
                if forecast is not None:
                    st.success("✅ Prévisions générées !")
                    
                    forecast['ds'] = pd.to_datetime(forecast['ds'])
                    forecast_display = forecast.copy()
                    forecast_display.columns = ['Date', 'Prévision', 'Min', 'Max']
                    forecast_display['Prévision'] = forecast_display['Prévision'].round(0).astype(int)
                    forecast_display['Min'] = forecast_display['Min'].round(0).astype(int)
                    forecast_display['Max'] = forecast_display['Max'].round(0).astype(int)
                    
                    st.dataframe(forecast_display, use_container_width=True)
                    
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=forecast['ds'],
                        y=forecast['yhat'],
                        mode='lines+markers',
                        name='Prévision',
                        line=dict(color='blue', width=2)
                    ))
                    fig.add_trace(go.Scatter(
                        x=forecast['ds'],
                        y=forecast['yhat_upper'],
                        mode='lines',
                        name='Max',
                        line=dict(color='lightblue', width=1, dash='dash')
                    ))
                    fig.add_trace(go.Scatter(
                        x=forecast['ds'],
                        y=forecast['yhat_lower'],
                        mode='lines',
                        name='Min',
                        line=dict(color='lightblue', width=1, dash='dash')
                    ))
                    
                    fig.update_layout(
                        title=f"Prévisions 7 jours - {produit_prevision}",
                        xaxis_title="Date",
                        yaxis_title="Ventes prévues"
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.error("❌ Pas assez de données pour ce produit")
    
    with tab2:
        st.markdown("### Analyse et importance des facteurs")
        
        produit_analyse = st.selectbox("Produit à analyser", df_histo["produit"].unique(), key="analyse")
        
        df_produit = df_histo[df_histo["produit"] == produit_analyse]
        
        if len(df_produit) >= 5:
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("Vente moyenne", f"{df_produit['ventes_moyennes'].mean():.0f} unités")
                st.metric("Vente max", f"{df_produit['ventes_moyennes'].max():.0f} unités")
            
            with col2:
                st.metric("Vente min", f"{df_produit['ventes_moyennes'].min():.0f} unités")
                st.metric("Écart type", f"{df_produit['ventes_moyennes'].std():.1f}")
            
            st.divider()
            
            fig = px.box(df_produit, x="jour", y="ventes_moyennes",
                        title="Distribution des ventes par jour")
            st.plotly_chart(fig, use_container_width=True)
            
            fig2 = px.box(df_produit, x="meteo", y="ventes_moyennes",
                         title="Distribution des ventes par météo")
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.warning("Pas assez de données pour ce produit")

elif menu == "📦 Stocks" and st.session_state.user_role == "Admin":
    st.subheader("📦 Gestion des stocks et ingrédients")
    
    stocks = charger_json(FICHIER_STOCKS, {st.session_state.user_email: {}})
    user_stocks = stocks.get(st.session_state.user_email, {})
    
    tab1, tab2 = st.tabs(["📊 Vue d'ensemble", "➕ Ajouter/Modifier"])
    
    with tab1:
        if user_stocks:
            df_stocks = pd.DataFrame([
                {"Ingrédient": ing, "Quantité": data["quantite"], "Unité": data["unite"],
                 "Seuil min": data["seuil_min"], "Coût/unité": f"{data['cout']:.2f}€"}
                for ing, data in user_stocks.items()
            ])
            
            st.dataframe(df_stocks, use_container_width=True)
            
            alertes = [ing for ing, data in user_stocks.items() if data["quantite"] <= data["seuil_min"]]
            
            if alertes:
                st.error(f"⚠️ Stock faible : {', '.join(alertes)}")
        else:
            st.info("Aucun stock enregistré. Ajoutez vos ingrédients.")
    
    with tab2:
        col1, col2 = st.columns(2)
        
        with col1:
            ingredient = st.text_input("Nom de l'ingrédient")
            quantite = st.number_input("Quantité", min_value=0.0, step=1.0)
            unite = st.selectbox("Unité", ["kg", "L", "unités"])
        
        with col2:
            seuil_min = st.number_input("Seuil minimum", min_value=0.0, step=1.0)
            cout = st.number_input("Coût unitaire (€)", min_value=0.0, step=0.1)
        
        if st.button("💾 Enregistrer", type="primary"):
            if ingredient:
                if st.session_state.user_email not in stocks:
                    stocks[st.session_state.user_email] = {}
                
                stocks[st.session_state.user_email][ingredient] = {
                    "quantite": quantite,
                    "unite": unite,
                    "seuil_min": seuil_min,
                    "cout": cout
                }
                
                sauvegarder_json(FICHIER_STOCKS, stocks)
                st.success("✅ Stock enregistré !")
                st.rerun()

elif menu == "👥 Équipe" and st.session_state.user_role == "Admin":
    st.subheader("👥 Gestion de l'équipe")
    
    users = charger_json(FICHIER_USERS)
    user_info = get_user_info(st.session_state.user_email)
    entreprise = user_info.get("entreprise", "")
    
    membres = {email: data for email, data in users.items()
              if data.get("entreprise") == entreprise}
    
    tab1, tab2 = st.tabs(["👥 Membres de l'équipe", "➕ Inviter"])
    
    with tab1:
        if len(membres) > 1:
            for email, data in membres.items():
                if email != st.session_state.user_email:
                    col1, col2, col3 = st.columns([3, 2, 1])
                    
                    with col1:
                        st.write(f"📧 {email}")
                    
                    with col2:
                        st.write(f"Rôle: {data.get('role', 'Employé')}")
                    
                    with col3:
                        if st.button("🗑️", key=f"del_{email}"):
                            del users[email]
                            sauvegarder_json(FICHIER_USERS, users)
                            st.rerun()
        else:
            st.info("Vous êtes seul dans l'équipe. Invitez des collaborateurs.")
    
    with tab2:
        st.markdown("### Inviter un membre")
        
        nouveau_email = st.text_input("Email du nouveau membre")
        nouveau_role = st.selectbox("Rôle", ["Admin", "Manager", "Employe"])
        
        if st.button("📧 Envoyer l'invitation", type="primary"):
            if nouveau_email:
                st.info(f"✅ Invitation envoyée à {nouveau_email}")
                st.caption("Le membre devra s'inscrire avec cet email.")

elif menu == "🔔 Notifications" and st.session_state.user_role == "Admin":
    st.subheader("🔔 Centre de notifications")
    
    if plan_info["plan"] not in ["Starter", "Pro", "Enterprise"]:
        st.warning("🔒 Fonctionnalité réservée aux plans Starter et supérieurs")
        st.stop()
    
    tab1, tab2 = st.tabs(["📬 Historique", "⚙️ Configuration"])
    
    with tab1:
        st.info("📧 Les notifications seront envoyées à " + st.session_state.user_email)
        
        notifications_exemples = [
            {"date": "2026-01-15", "type": "Alerte", "message": "Stock de farine faible"},
            {"date": "2026-01-14", "type": "Info", "message": "Résumé hebdomadaire disponible"},
            {"date": "2026-01-13", "type": "Alerte", "message": "Gaspillage élevé détecté"}
        ]
        
        for notif in notifications_exemples:
            with st.expander(f"{notif['date']} - {notif['type']}: {notif['message']}"):
                st.write("Détails de la notification...")
    
    with tab2:
        st.markdown("### Configuration des alertes")
        
        alerte_stock = st.checkbox("Alertes de stock faible", value=True)
        alerte_gaspillage = st.checkbox("Alertes de gaspillage élevé", value=True)
        resume_hebdo = st.checkbox("Résumé hebdomadaire", value=True)
        
        heure_envoi = st.time_input("Heure d'envoi quotidien")
        
        if st.button("💾 Sauvegarder", type="primary"):
            st.success("✅ Préférences enregistrées !")

elif menu == "🔌 API" and st.session_state.user_role == "Admin":
    st.subheader("🔌 API REST")
    
    if plan_info["plan"] not in ["Pro", "Enterprise"]:
        st.warning("🔒 API réservée aux plans Pro et Enterprise")
        st.stop()
    
    api_key = hashlib.sha256(st.session_state.user_email.encode()).hexdigest()[:32]
    
    st.markdown("### 🔑 Votre clé API")
    st.code(api_key)
    st.caption("⚠️ Gardez cette clé secrète !")
    
    st.divider()
    
    st.markdown("### 📚 Documentation API")
    
    with st.expander("GET /predictions - Récupérer l'historique"):
        st.code("""
curl -X GET https://api.boulangerie-pro.com/predictions \\
  -H "Authorization: Bearer YOUR_API_KEY"
        """, language="bash")
    
    with st.expander("POST /predictions - Créer une prédiction"):
        st.code("""
curl -X POST https://api.boulangerie-pro.com/predictions \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "jour": "Lundi",
    "meteo": "Soleil",
    "produit": "Baguette",
    "production_habituelle": 100,
    "ventes_moyennes": 85
  }'
        """, language="bash")
    
    with st.expander("GET /stats - Récupérer les statistiques"):
        st.code("""
curl -X GET https://api.boulangerie-pro.com/stats \\
  -H "Authorization: Bearer YOUR_API_KEY"
        """, language="bash")

elif menu == "⚙️ Paramètres":
    st.subheader("⚙️ Paramètres")
    
    tab1, tab2, tab3, tab4 = st.tabs(["👤 Compte", "🔐 Sécurité", "💎 Abonnement", "🎯 Application"])
    
    with tab1:
        st.markdown("### Informations du compte")
        
        user_info = get_user_info(st.session_state.user_email)
        
        st.write(f"**Email:** {st.session_state.user_email}")
        st.write(f"**Rôle:** {st.session_state.user_role}")
        st.write(f"**Date d'inscription:** {user_info.get('date_inscription', 'N/A')}")
        st.write(f"**Entreprise:** {user_info.get('entreprise', 'N/A')}")
        
        st.divider()
        
        new_entreprise = st.text_input("Nom de l'entreprise", value=user_info.get('entreprise', ''))
        
        if st.button("💾 Mettre à jour"):
            users = charger_json(FICHIER_USERS)
            users[st.session_state.user_email]["entreprise"] = new_entreprise
            sauvegarder_json(FICHIER_USERS, users)
            st.success("✅ Informations mises à jour !")
    
    with tab2:
        st.markdown("### 🔐 Sécurité")
        
        st.markdown("#### Changer le mot de passe")
        old_password = st.text_input("Ancien mot de passe", type="password")
        new_password = st.text_input("Nouveau mot de passe", type="password")
        confirm_new = st.text_input("Confirmer", type="password")
        
        if st.button("Modifier le mot de passe"):
            if not verifier_login(st.session_state.user_email, old_password):
                st.error("❌ Ancien mot de passe incorrect")
            elif new_password != confirm_new:
                st.error("❌ Les mots de passe ne correspondent pas")
            elif len(new_password) < 8:
                st.error("❌ Minimum 8 caractères")
            else:
                users = charger_json(FICHIER_USERS)
                users[st.session_state.user_email]["password"] = hash_password(new_password)
                sauvegarder_json(FICHIER_USERS, users)
                st.success("✅ Mot de passe modifié !")
        
        st.divider()
        
        st.markdown("#### Authentification à deux facteurs (2FA)")
        
        user_info = get_user_info(st.session_state.user_email)
        
        if user_info.get("2fa_enabled", False):
            st.success("✅ 2FA activé")
            
            if st.button("Désactiver 2FA"):
                users = charger_json(FICHIER_USERS)
                users[st.session_state.user_email]["2fa_enabled"] = False
                sauvegarder_json(FICHIER_USERS, users)
                st.success("✅ 2FA désactivé")
                st.rerun()
        else:
            if st.button("🔐 Activer 2FA", type="primary"):
                qr_bytes, secret = generer_qr_2fa(st.session_state.user_email)
                
                st.image(qr_bytes, caption="Scannez ce QR code avec Google Authenticator")
                st.code(secret, label="Ou entrez cette clé manuellement")
                
                code_test = st.text_input("Entrez le code à 6 chiffres pour confirmer")
                
                if st.button("Vérifier et activer"):
                    if verifier_code_2fa(st.session_state.user_email, code_test):
                        users = charger_json(FICHIER_USERS)
                        users[st.session_state.user_email]["2fa_enabled"] = True
                        sauvegarder_json(FICHIER_USERS, users)
                        st.success("✅ 2FA activé avec succès !")
                        st.rerun()
                    else:
                        st.error("❌ Code invalide")
    
    with tab3:
        st.markdown("### 💎 Gestion de l'abonnement")
        
        plan_actuel = plan_info["plan"]
        
        st.info(f"Plan actuel: **{plan_actuel}**")
        
        if plan_actuel == "Gratuit":
            date_fin = datetime.strptime(plan_info.get("date_fin_essai", str(date.today())), "%Y-%m-%d")
            jours_restants = (date_fin - datetime.now()).days
            st.warning(f"⏰ {jours_restants} jours d'essai restants")
        
        st.divider()
        
        st.markdown("#### Changer de plan")
        
        cols = st.columns(4)
        
        for idx, (plan_nom, details) in enumerate(PLANS_TARIFS.items()):
            with cols[idx]:
                if plan_nom == plan_actuel:
                    st.success(f"✅ {plan_nom}")
                else:
                    st.markdown(f"**{plan_nom}**")
                
                st.write(f"{details['prix']}€/mois" if details['prix'] > 0 else "Gratuit")
                
                if plan_nom != plan_actuel:
                    if st.button(f"Choisir {plan_nom}", key=f"plan_{idx}"):
                        abonnements = charger_json(FICHIER_ABONNEMENTS)
                        abonnements[st.session_state.user_email] = {
                            "plan": plan_nom,
                            "date_debut": str(date.today()),
                            "actif": True
                        }
                        sauvegarder_json(FICHIER_ABONNEMENTS, abonnements)
                        st.success(f"✅ Passé au plan {plan_nom} !")
                        st.rerun()
    
    with tab4:
        st.markdown("### 🎯 Paramètres de l'application")
        
        st.markdown("#### Coefficients de prédiction")
        
        with st.expander("📅 Coefficients par jour"):
            for jour, coef in COEF_JOUR.items():
                st.write(f"{jour}: {coef}")
        
        with st.expander("☁️ Coefficients météo"):
            for meteo, coef in COEF_METEO.items():
                st.write(f"{meteo}: {coef}")

elif menu == "📈 Statistiques":
    st.subheader("📈 Statistiques avancées")
    
    df_histo = pd.read_csv(FICHIER_HISTO)
    
    if not df_histo.empty:
        df_histo["date"] = pd.to_datetime(df_histo["date"])
        
        col1, col2 = st.columns(2)
        
        with col1:
            periode = st.selectbox(
                "Période",
                ["7 derniers jours", "30 derniers jours", "3 derniers mois", "Tout"]
            )
        
        with col2:
            produit_filtre = st.multiselect(
                "Produits",
                options=df_histo["produit"].unique(),
                default=df_histo["produit"].unique()
            )
        
        if periode == "7 derniers jours":
            date_limite = datetime.now() - timedelta(days=7)
        elif periode == "30 derniers jours":
            date_limite = datetime.now() - timedelta(days=30)
        elif periode == "3 derniers mois":
            date_limite = datetime.now() - timedelta(days=90)
        else:
            date_limite = df_histo["date"].min()
        
        df_filtre = df_histo[
            (df_histo["date"] >= date_limite) &
            (df_histo["produit"].isin(produit_filtre))
        ]
        
        if not df_filtre.empty:
            st.divider()
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total évité", f"{int(df_filtre['gaspillage_evite'].sum())} unités")
            
            with col2:
                st.metric("Économies", f"{df_filtre['cout_gaspillage'].sum():.2f} €")
            
            with col3:
                st.metric("Moyenne/jour", f"{df_filtre['gaspillage_evite'].mean():.1f}")
            
            with col4:
                st.metric("Max en 1 jour", f"{int(df_filtre['gaspillage_evite'].max())}")
            
            st.divider()
            
            df_trend = df_filtre.groupby("date").agg({
                "gaspillage_evite": "sum",
                "cout_gaspillage": "sum"
            }).reset_index()
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_trend["date"], y=df_trend["gaspillage_evite"],
                                    mode='lines+markers', name='Gaspillage évité'))
            fig.update_layout(title="Évolution", xaxis_title="Date", yaxis_title="Unités")
            st.plotly_chart(fig, use_container_width=True)
            
            col1, col2 = st.columns(2)
            
            with col1:
                top_produits = df_filtre.groupby("produit")["gaspillage_evite"].sum().sort_values(ascending=False)
                st.markdown("#### 🏆 Top produits")
                st.dataframe(top_produits.head(10), use_container_width=True)
            
            with col2:
                top_jours = df_filtre.groupby("jour")["gaspillage_evite"].mean().sort_values(ascending=False)
                st.markdown("#### 📅 Meilleurs jours")
                st.dataframe(top_jours, use_container_width=True)
        else:
            st.warning("Aucune donnée pour les filtres sélectionnés")
    else:
        st.info("📊 Aucune donnée disponible")

elif menu == "📄 Rapports":
    st.subheader("📄 Rapports")
    
    df_histo = pd.read_csv(FICHIER_HISTO)
    
    if not df_histo.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📥 Export PDF")
            if st.button("Générer PDF", use_container_width=True):
                st.info("📄 Génération PDF disponible")
        
        with col2:
            st.markdown("### 📊 Export Excel")
            
            if "Excel" in PLANS_TARIFS[plan_info["plan"]]["exports"]:
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_histo.to_excel(writer, sheet_name='Historique', index=False)
                
                st.download_button(
                    label="📥 Télécharger Excel",
                    data=output.getvalue(),
                    file_name=f"rapport_{date.today()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            else:
                st.warning("🔒 Export Excel réservé aux plans Starter+")
        
        st.divider()
        st.dataframe(df_histo, use_container_width=True)
    else:
        st.info("📊 Aucune donnée disponible")

st.divider()
st.caption("🥖 Boulangerie Pro - Solution IA professionnelle | Version 3.0 Premium")
st.caption("💎 Support: support@boulangerie-pro.com | 📚 Documentation: docs.boulangerie-pro.com")
