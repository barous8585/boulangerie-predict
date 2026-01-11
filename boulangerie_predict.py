import streamlit as st
import pandas as pd
from datetime import date
import os

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# --------------------------------------------------
# CONFIG
# --------------------------------------------------
st.set_page_config(
    page_title="Prédicteur de production – Boulangerie",
    layout="centered"
)

st.title("🥖 Prédicteur de production – Boulangerie")

# --------------------------------------------------
# ACCÈS PRO (ABONNEMENT SIMPLE)
# --------------------------------------------------
EMAILS_AUTORISES = [
    "test@gmail.com",      # ← remplace par les emails clients
]

email = st.text_input("📧 Email professionnel")

if email not in EMAILS_AUTORISES:
    st.warning("🔒 Accès réservé aux abonnés")
    st.info("Contactez-nous pour activer l’abonnement.")
    st.stop()

st.success("✅ Accès professionnel activé")

# --------------------------------------------------
# FICHIER HISTORIQUE
# --------------------------------------------------
FICHIER_HISTO = "historique_production.csv"

if not os.path.exists(FICHIER_HISTO):
    df_init = pd.DataFrame(columns=[
        "date",
        "jour",
        "meteo",
        "production_habituelle",
        "ventes_moyennes",
        "production_conseillee",
        "gaspillage_evite"
    ])
    df_init.to_csv(FICHIER_HISTO, index=False)

# --------------------------------------------------
# SAISIE
# --------------------------------------------------
st.subheader("📥 Données du jour")

jour = st.selectbox(
    "Jour",
    ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
)

meteo = st.selectbox(
    "Météo",
    ["Soleil","Nuageux","Pluie"]
)

prod_habituelle = st.number_input(
    "Production habituelle (unités)",
    min_value=0,
    step=10
)

ventes_moy = st.number_input(
    "Ventes moyennes constatées",
    min_value=0,
    step=10
)

# --------------------------------------------------
# COEFFICIENTS
# --------------------------------------------------
coef_jour = {
    "Lundi": 0.8,
    "Mardi": 0.9,
    "Mercredi": 1.0,
    "Jeudi": 1.0,
    "Vendredi": 1.2,
    "Samedi": 1.4,
    "Dimanche": 1.3
}

coef_meteo = {
    "Soleil": 1.1,
    "Nuageux": 1.0,
    "Pluie": 0.85
}

# --------------------------------------------------
# CALCUL
# --------------------------------------------------
st.divider()
st.subheader("📊 Résultat")

if ventes_moy > 0:
    prod_conseillee = int(
        ventes_moy * coef_jour[jour] * coef_meteo[meteo]
    )

    gaspillage_evite = max(0, prod_habituelle - prod_conseillee)

    st.success(f"Production conseillée : {prod_conseillee} unités")

    if gaspillage_evite > 0:
        st.warning(f"⚠️ Gaspillage évité estimé : {gaspillage_evite} unités")
    else:
        st.info("✅ Production optimisée")

    if st.button("💾 Enregistrer la journée"):
        df = pd.read_csv(FICHIER_HISTO)

        nouvelle_ligne = {
            "date": date.today(),
            "jour": jour,
            "meteo": meteo,
            "production_habituelle": prod_habituelle,
            "ventes_moyennes": ventes_moy,
            "production_conseillee": prod_conseillee,
            "gaspillage_evite": gaspillage_evite
        }

        df = pd.concat([df, pd.DataFrame([nouvelle_ligne])], ignore_index=True)
        df.to_csv(FICHIER_HISTO, index=False)

        st.success("Journée enregistrée ✅")

else:
    st.info("Entrez les ventes moyennes pour continuer.")

# --------------------------------------------------
# HISTORIQUE
# --------------------------------------------------
st.divider()
st.subheader("📈 Historique")

df_histo = pd.read_csv(FICHIER_HISTO)

if not df_histo.empty:
    st.dataframe(df_histo, use_container_width=True)

    total_evite = int(df_histo["gaspillage_evite"].sum())
    st.success(f"🥖 Total gaspillage évité : {total_evite} unités")
else:
    st.info("Aucune donnée enregistrée.")

# --------------------------------------------------
# RAPPORT PDF
# --------------------------------------------------
st.divider()
st.subheader("📄 Rapport PDF mensuel")

def generer_pdf(df):
    nom_fichier = "rapport_boulangerie.pdf"
    c = canvas.Canvas(nom_fichier, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "Rapport de production – Boulangerie")

    c.setFont("Helvetica", 11)
    c.drawString(50, height - 90, f"Total gaspillage évité : {int(df['gaspillage_evite'].sum())} unités")
    c.drawString(50, height - 110, f"Nombre de jours analysés : {len(df)}")

    y = height - 150
    for _, row in df.tail(15).iterrows():
        ligne = f"{row['date']} | {row['jour']} | évité : {int(row['gaspillage_evite'])}"
        c.drawString(50, y, ligne)
        y -= 15
        if y < 50:
            c.showPage()
            y = height - 50

    c.save()
    return nom_fichier

if not df_histo.empty:
    if st.button("📥 Générer le rapport PDF"):
        pdf = generer_pdf(df_histo)
        with open(pdf, "rb") as f:
            st.download_button(
                label="📄 Télécharger le rapport PDF",
                data=f,
                file_name=pdf,
                mime="application/pdf"
            )
