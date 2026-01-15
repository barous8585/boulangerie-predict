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

# --------------------------------------------------
# CONFIG
# --------------------------------------------------
st.set_page_config(
    page_title="Prédicteur de production – Boulangerie Pro",
    layout="wide",
    page_icon="🥖"
)

# --------------------------------------------------
# GESTION DES UTILISATEURS
# --------------------------------------------------
FICHIER_USERS = "users.json"

def charger_users():
    if os.path.exists(FICHIER_USERS):
        with open(FICHIER_USERS, "r") as f:
            return json.load(f)
    return {}

def sauvegarder_users(users):
    with open(FICHIER_USERS, "w") as f:
        json.dump(users, f)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verifier_login(email, password):
    users = charger_users()
    if email in users:
        return users[email]["password"] == hash_password(password)
    return False

# Initialiser la session
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_email = None

# --------------------------------------------------
# AUTHENTIFICATION
# --------------------------------------------------
if not st.session_state.authenticated:
    st.title("🥖 Prédicteur de production – Boulangerie Pro")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.subheader("🔐 Connexion")
        
        email = st.text_input("📧 Email professionnel", key="login_email")
        password = st.text_input("🔑 Mot de passe", type="password", key="login_password")
        
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            if st.button("Se connecter", use_container_width=True):
                if verifier_login(email, password):
                    st.session_state.authenticated = True
                    st.session_state.user_email = email
                    st.rerun()
                else:
                    st.error("❌ Email ou mot de passe incorrect")
        
        with col_btn2:
            if st.button("Créer un compte", use_container_width=True):
                st.session_state.show_signup = True
        
        if st.session_state.get("show_signup", False):
            st.divider()
            st.subheader("📝 Nouveau compte")
            new_email = st.text_input("Email", key="signup_email")
            new_password = st.text_input("Mot de passe", type="password", key="signup_password")
            confirm_password = st.text_input("Confirmer mot de passe", type="password", key="signup_confirm")
            
            if st.button("S'inscrire"):
                if new_password != confirm_password:
                    st.error("❌ Les mots de passe ne correspondent pas")
                elif len(new_password) < 6:
                    st.error("❌ Le mot de passe doit contenir au moins 6 caractères")
                elif new_email in charger_users():
                    st.error("❌ Cet email est déjà enregistré")
                else:
                    users = charger_users()
                    users[new_email] = {
                        "password": hash_password(new_password),
                        "date_inscription": str(date.today())
                    }
                    sauvegarder_users(users)
                    st.success("✅ Compte créé avec succès ! Vous pouvez maintenant vous connecter.")
                    st.session_state.show_signup = False
    
    st.stop()

# --------------------------------------------------
# INTERFACE PRINCIPALE
# --------------------------------------------------
st.title("🥖 Prédicteur de production – Boulangerie Pro")

# Sidebar avec menu
with st.sidebar:
    st.header(f"👤 {st.session_state.user_email}")
    if st.button("🚪 Déconnexion"):
        st.session_state.authenticated = False
        st.session_state.user_email = None
        st.rerun()
    
    st.divider()
    
    menu = st.radio(
        "Navigation",
        ["📊 Dashboard", "📥 Nouvelle prédiction", "📈 Statistiques", "📄 Rapports", "⚙️ Paramètres"]
    )

# --------------------------------------------------
# FICHIER HISTORIQUE PAR UTILISATEUR
# --------------------------------------------------
def get_fichier_histo():
    user_safe = st.session_state.user_email.replace("@", "_").replace(".", "_")
    return f"historique_{user_safe}.csv"

FICHIER_HISTO = get_fichier_histo()

if not os.path.exists(FICHIER_HISTO):
    df_init = pd.DataFrame(columns=[
        "date",
        "jour",
        "meteo",
        "produit",
        "production_habituelle",
        "ventes_moyennes",
        "production_conseillee",
        "gaspillage_evite",
        "cout_gaspillage"
    ])
    df_init.to_csv(FICHIER_HISTO, index=False)

# --------------------------------------------------
# PARAMÈTRES PAR DÉFAUT
# --------------------------------------------------
PRODUITS_DEFAUT = ["Pain classique", "Baguette", "Croissant", "Pain au chocolat", "Pain complet"]
COUT_UNITAIRE_DEFAUT = {"Pain classique": 0.5, "Baguette": 0.4, "Croissant": 0.6, "Pain au chocolat": 0.7, "Pain complet": 0.6}

COEF_JOUR = {
    "Lundi": 0.8,
    "Mardi": 0.9,
    "Mercredi": 1.0,
    "Jeudi": 1.0,
    "Vendredi": 1.2,
    "Samedi": 1.4,
    "Dimanche": 1.3
}

COEF_METEO = {
    "Soleil": 1.1,
    "Nuageux": 1.0,
    "Pluie": 0.85,
    "Neige": 0.7
}

# --------------------------------------------------
# FONCTIONS UTILITAIRES
# --------------------------------------------------
def calculer_prediction_intelligente(df, produit, jour, meteo):
    if df.empty:
        return None
    
    df_produit = df[df["produit"] == produit]
    
    if df_produit.empty:
        return None
    
    df_similaire = df_produit[
        (df_produit["jour"] == jour) & 
        (df_produit["meteo"] == meteo)
    ]
    
    if not df_similaire.empty:
        return int(df_similaire["ventes_moyennes"].mean())
    
    df_jour = df_produit[df_produit["jour"] == jour]
    if not df_jour.empty:
        return int(df_jour["ventes_moyennes"].mean())
    
    return int(df_produit["ventes_moyennes"].mean())

def generer_pdf_ameliore(df):
    nom_fichier = f"rapport_boulangerie_{date.today()}.pdf"
    c = canvas.Canvas(nom_fichier, pagesize=letter)
    width, height = letter
    
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 50, "Rapport de production - Boulangerie Pro")
    
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 70, f"Généré le {date.today().strftime('%d/%m/%Y')}")
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 100, "Résumé global")
    
    c.setFont("Helvetica", 10)
    total_evite = int(df["gaspillage_evite"].sum())
    total_cout = df["cout_gaspillage"].sum()
    c.drawString(50, height - 120, f"Total gaspillage évité : {total_evite} unités")
    c.drawString(50, height - 135, f"Économies réalisées : {total_cout:.2f} €")
    c.drawString(50, height - 150, f"Nombre de jours analysés : {len(df)}")
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 180, "Détail par produit")
    
    y = height - 200
    c.setFont("Helvetica", 9)
    
    for produit in df["produit"].unique():
        df_produit = df[df["produit"] == produit]
        evite = int(df_produit["gaspillage_evite"].sum())
        cout = df_produit["cout_gaspillage"].sum()
        c.drawString(50, y, f"{produit}: {evite} unités évitées ({cout:.2f} €)")
        y -= 15
        if y < 100:
            c.showPage()
            y = height - 50
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y - 20, "Dernières entrées")
    
    y -= 40
    c.setFont("Helvetica", 8)
    
    for _, row in df.tail(20).iterrows():
        ligne = f"{row['date']} | {row['jour']} | {row['produit']} | Évité: {int(row['gaspillage_evite'])} | Coût: {row['cout_gaspillage']:.2f}€"
        c.drawString(50, y, ligne)
        y -= 12
        if y < 50:
            c.showPage()
            y = height - 50
    
    c.save()
    return nom_fichier

def exporter_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Historique', index=False)
        
        resume = pd.DataFrame({
            'Produit': df.groupby('produit')['gaspillage_evite'].sum().index,
            'Gaspillage évité': df.groupby('produit')['gaspillage_evite'].sum().values,
            'Économies (€)': df.groupby('produit')['cout_gaspillage'].sum().values
        })
        resume.to_excel(writer, sheet_name='Résumé', index=False)
    
    return output.getvalue()

# --------------------------------------------------
# MENU 1: DASHBOARD
# --------------------------------------------------
if menu == "📊 Dashboard":
    df_histo = pd.read_csv(FICHIER_HISTO)
    
    if not df_histo.empty:
        col1, col2, col3, col4 = st.columns(4)
        
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
        st.subheader("📋 Dernières entrées")
        st.dataframe(df_histo.tail(10).iloc[::-1], use_container_width=True)
    
    else:
        st.info("📊 Aucune donnée disponible. Commencez par créer une nouvelle prédiction.")

# --------------------------------------------------
# MENU 2: NOUVELLE PRÉDICTION
# --------------------------------------------------
elif menu == "📥 Nouvelle prédiction":
    st.subheader("📥 Nouvelle prédiction de production")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Informations générales")
        
        jour = st.selectbox(
            "Jour de la semaine",
            ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
        )
        
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
        suggestion = calculer_prediction_intelligente(df_histo, produit, jour, meteo)
        
        if suggestion:
            st.info(f"💡 Suggestion basée sur l'historique : {suggestion} unités")
    
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

# --------------------------------------------------
# MENU 3: STATISTIQUES
# --------------------------------------------------
elif menu == "📈 Statistiques":
    st.subheader("📈 Statistiques avancées")
    
    df_histo = pd.read_csv(FICHIER_HISTO)
    
    if not df_histo.empty:
        df_histo["date"] = pd.to_datetime(df_histo["date"])
        
        col1, col2 = st.columns(2)
        
        with col1:
            periode = st.selectbox(
                "Période d'analyse",
                ["7 derniers jours", "30 derniers jours", "3 derniers mois", "Tout l'historique"]
            )
        
        with col2:
            produit_filtre = st.multiselect(
                "Filtrer par produit",
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
                st.metric("Total gaspillage évité", f"{int(df_filtre['gaspillage_evite'].sum())} unités")
            
            with col2:
                st.metric("Total économies", f"{df_filtre['cout_gaspillage'].sum():.2f} €")
            
            with col3:
                st.metric("Moyenne journalière", f"{df_filtre['gaspillage_evite'].mean():.1f} unités")
            
            with col4:
                st.metric("Maximum en 1 jour", f"{int(df_filtre['gaspillage_evite'].max())} unités")
            
            st.divider()
            
            st.subheader("📊 Tendances")
            
            df_trend = df_filtre.groupby("date").agg({
                "gaspillage_evite": "sum",
                "cout_gaspillage": "sum"
            }).reset_index()
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_trend["date"], y=df_trend["gaspillage_evite"],
                                    mode='lines+markers', name='Gaspillage évité'))
            fig.update_layout(title="Évolution du gaspillage évité",
                            xaxis_title="Date", yaxis_title="Unités")
            st.plotly_chart(fig, use_container_width=True)
            
            st.divider()
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("🏆 Top produits optimisés")
                top_produits = df_filtre.groupby("produit")["gaspillage_evite"].sum().sort_values(ascending=False)
                st.dataframe(top_produits.head(10), use_container_width=True)
            
            with col2:
                st.subheader("📅 Meilleurs jours")
                top_jours = df_filtre.groupby("jour")["gaspillage_evite"].mean().sort_values(ascending=False)
                st.dataframe(top_jours, use_container_width=True)
            
            st.divider()
            
            st.subheader("🔍 Analyse détaillée")
            st.dataframe(df_filtre.sort_values("date", ascending=False), use_container_width=True)
        
        else:
            st.warning("Aucune donnée pour les filtres sélectionnés.")
    
    else:
        st.info("📊 Aucune donnée disponible.")

# --------------------------------------------------
# MENU 4: RAPPORTS
# --------------------------------------------------
elif menu == "📄 Rapports":
    st.subheader("📄 Génération de rapports")
    
    df_histo = pd.read_csv(FICHIER_HISTO)
    
    if not df_histo.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📥 Export PDF")
            st.write("Générez un rapport PDF complet avec statistiques et graphiques.")
            
            if st.button("📄 Générer le rapport PDF", use_container_width=True):
                with st.spinner("Génération en cours..."):
                    pdf = generer_pdf_ameliore(df_histo)
                    with open(pdf, "rb") as f:
                        st.download_button(
                            label="📥 Télécharger le PDF",
                            data=f,
                            file_name=pdf,
                            mime="application/pdf",
                            use_container_width=True
                        )
                st.success("✅ Rapport PDF généré avec succès !")
        
        with col2:
            st.markdown("### 📊 Export Excel")
            st.write("Exportez toutes vos données au format Excel pour analyse approfondie.")
            
            if st.button("📊 Générer le rapport Excel", use_container_width=True):
                with st.spinner("Génération en cours..."):
                    excel_data = exporter_excel(df_histo)
                    st.download_button(
                        label="📥 Télécharger Excel",
                        data=excel_data,
                        file_name=f"rapport_boulangerie_{date.today()}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                st.success("✅ Rapport Excel généré avec succès !")
        
        st.divider()
        
        st.subheader("📊 Aperçu des données")
        st.dataframe(df_histo, use_container_width=True)
        
        st.divider()
        
        st.subheader("🗑️ Gestion des données")
        st.warning("⚠️ Attention : Cette action est irréversible !")
        
        if st.button("🗑️ Supprimer tout l'historique", type="secondary"):
            if st.checkbox("Je confirme vouloir supprimer toutes les données"):
                df_init = pd.DataFrame(columns=[
                    "date", "jour", "meteo", "produit",
                    "production_habituelle", "ventes_moyennes",
                    "production_conseillee", "gaspillage_evite", "cout_gaspillage"
                ])
                df_init.to_csv(FICHIER_HISTO, index=False)
                st.success("✅ Historique supprimé")
                st.rerun()
    
    else:
        st.info("📊 Aucune donnée disponible pour générer des rapports.")

# --------------------------------------------------
# MENU 5: PARAMÈTRES
# --------------------------------------------------
elif menu == "⚙️ Paramètres":
    st.subheader("⚙️ Paramètres de l'application")
    
    tab1, tab2, tab3 = st.tabs(["🎯 Coefficients", "🥖 Produits", "👤 Compte"])
    
    with tab1:
        st.markdown("### Coefficients de prédiction")
        
        st.markdown("#### 📅 Coefficients par jour")
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Jours actuels :**")
            for jour, coef in COEF_JOUR.items():
                st.write(f"{jour}: {coef}")
        
        with col2:
            st.info("💡 Ces coefficients influencent la prédiction selon le jour de la semaine.")
        
        st.divider()
        
        st.markdown("#### ☁️ Coefficients météo")
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Météo actuelle :**")
            for meteo, coef in COEF_METEO.items():
                st.write(f"{meteo}: {coef}")
        
        with col2:
            st.info("💡 Ces coefficients ajustent la prédiction selon la météo.")
    
    with tab2:
        st.markdown("### 🥖 Gestion des produits")
        
        st.write("**Produits disponibles :**")
        for produit in PRODUITS_DEFAUT:
            st.write(f"- {produit} (coût: {COUT_UNITAIRE_DEFAUT.get(produit, 0.5)}€)")
        
        st.info("💡 Ajoutez vos propres produits lors de la création d'une prédiction.")
    
    with tab3:
        st.markdown("### 👤 Informations du compte")
        
        st.write(f"**Email :** {st.session_state.user_email}")
        
        users = charger_users()
        if st.session_state.user_email in users:
            st.write(f"**Date d'inscription :** {users[st.session_state.user_email].get('date_inscription', 'N/A')}")
        
        st.divider()
        
        st.markdown("### 🔐 Modifier le mot de passe")
        
        old_password = st.text_input("Ancien mot de passe", type="password")
        new_password = st.text_input("Nouveau mot de passe", type="password")
        confirm_new = st.text_input("Confirmer nouveau mot de passe", type="password")
        
        if st.button("Modifier le mot de passe"):
            if not verifier_login(st.session_state.user_email, old_password):
                st.error("❌ Ancien mot de passe incorrect")
            elif new_password != confirm_new:
                st.error("❌ Les mots de passe ne correspondent pas")
            elif len(new_password) < 6:
                st.error("❌ Le mot de passe doit contenir au moins 6 caractères")
            else:
                users[st.session_state.user_email]["password"] = hash_password(new_password)
                sauvegarder_users(users)
                st.success("✅ Mot de passe modifié avec succès !")

# --------------------------------------------------
# FOOTER
# --------------------------------------------------
st.divider()
st.caption("🥖 Boulangerie Pro - Optimisez votre production et réduisez le gaspillage | Version 2.0")
