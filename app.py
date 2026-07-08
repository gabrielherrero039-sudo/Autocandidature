"""
app.py — Interface Streamlit pour l'outil de candidature automatique
Adapte votre CV et génère une lettre de motivation pour chaque offre d'emploi.
"""

import streamlit as st
from cv_loader import load_cv
from job_adapter import adapt_cv_stream, generate_cover_letter_stream

# Export DOCX optionnel — fonctionne si python-docx est installé
try:
    from cv_loader import export_to_docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

# ─── Configuration de la page ─────────────────────────────────────────────────

st.set_page_config(
    page_title="AutoCandidature IA",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS personnalisé ──────────────────────────────────────────────────────────

st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1a1a2e;
        margin-bottom: 0.2rem;
    }
    .subtitle {
        font-size: 1rem;
        color: #6c757d;
        margin-bottom: 2rem;
    }
    .section-header {
        font-size: 1.1rem;
        font-weight: 600;
        color: #16213e;
        border-bottom: 2px solid #e9ecef;
        padding-bottom: 0.3rem;
        margin-bottom: 1rem;
    }
    .success-box {
        background-color: #d4edda;
        border-left: 4px solid #28a745;
        padding: 0.75rem 1rem;
        border-radius: 4px;
        margin: 0.5rem 0;
    }
    .info-box {
        background-color: #d1ecf1;
        border-left: 4px solid #17a2b8;
        padding: 0.75rem 1rem;
        border-radius: 4px;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

# ─── Titre ────────────────────────────────────────────────────────────────────

st.markdown('<p class="main-title">📄 AutoCandidature IA</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Adaptez votre CV et générez une lettre de motivation personnalisée pour chaque offre d\'emploi grâce à l\'IA.</p>', unsafe_allow_html=True)

# ─── Barre latérale : Configuration ───────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ Configuration")

    api_key = st.text_input(
        "Clé API Anthropic",
        type="password",
        placeholder="sk-ant-...",
        help="Obtenez votre clé sur console.anthropic.com",
    )

    model = st.selectbox(
        "Modèle Claude",
        options=[
            "claude-sonnet-4-6",
            "claude-opus-4-6",
            "claude-haiku-4-5-20251001",
        ],
        index=0,
        help="Sonnet = équilibre qualité/rapidité | Opus = meilleure qualité | Haiku = plus rapide",
    )

    st.divider()
    st.header("👤 Informations candidat")

    applicant_name = st.text_input(
        "Votre nom complet",
        placeholder="Jean Dupont",
        help="Utilisé pour personnaliser la lettre de motivation",
    )

    company_name = st.text_input(
        "Nom de l'entreprise",
        placeholder="Exemple: Google, LVMH...",
        help="Optionnel — personnalise la lettre",
    )

    st.divider()
    st.markdown("### ℹ️ À propos")
    st.markdown("""
    Cet outil utilise Claude (Anthropic) pour :
    - ✅ Adapter votre CV à chaque offre
    - ✅ Générer une lettre personnalisée
    - ✅ Télécharger les documents en `.docx`

    **Vos données ne sont pas stockées.**
    """)

# ─── Colonnes principales ─────────────────────────────────────────────────────

col1, col2 = st.columns([1, 1], gap="large")

# ── Colonne gauche : Saisie ────────────────────────────────────────────────────

with col1:
    st.markdown('<p class="section-header">1. Votre CV</p>', unsafe_allow_html=True)

    cv_source = st.radio(
        "Source du CV",
        options=["Uploader un fichier", "Coller le texte"],
        horizontal=True,
        label_visibility="collapsed",
    )

    cv_content = ""

    if cv_source == "Uploader un fichier":
        uploaded_file = st.file_uploader(
            "Choisissez votre CV",
            type=["pdf", "docx", "txt"],
            help="Formats supportés : PDF, Word (.docx), texte (.txt)",
        )
        if uploaded_file:
            try:
                cv_content = load_cv(uploaded_file=uploaded_file)
                st.markdown(
                    f'<div class="success-box">✅ CV chargé ({len(cv_content)} caractères)</div>',
                    unsafe_allow_html=True,
                )
                with st.expander("Aperçu du CV chargé"):
                    st.text(cv_content[:2000] + ("..." if len(cv_content) > 2000 else ""))
            except Exception as e:
                st.error(f"Erreur lors du chargement : {e}")
    else:
        cv_content = st.text_area(
            "Collez votre CV ici",
            height=300,
            placeholder="Nom Prénom\nTitre professionnel\n\nEXPÉRIENCES\n...",
        )

    st.markdown('<p class="section-header" style="margin-top:1.5rem">2. Offre d\'emploi</p>', unsafe_allow_html=True)

    sector = st.text_input(
        "Secteur / Domaine",
        placeholder="Ex: Data Science, Marketing Digital, Finance, Ingénierie...",
    )

    job_posting = st.text_area(
        "Collez l'offre d'emploi complète",
        height=300,
        placeholder="Titre du poste : ...\nEntreprise : ...\nDescription : ...\nProfil recherché : ...\nCompétences requises : ...",
    )

# ── Bouton de génération ───────────────────────────────────────────────────────

st.divider()

generate_btn = st.button(
    "🚀 Générer le CV adapté et la lettre de motivation",
    type="primary",
    use_container_width=True,
    disabled=not (api_key and cv_content and job_posting and sector),
)

if not api_key:
    st.caption("⚠️ Entrez votre clé API Anthropic dans la barre latérale.")
elif not cv_content:
    st.caption("⚠️ Chargez ou collez votre CV.")
elif not sector:
    st.caption("⚠️ Précisez le secteur / domaine.")
elif not job_posting:
    st.caption("⚠️ Collez l'offre d'emploi.")

# ─── Génération et affichage des résultats ─────────────────────────────────────

if generate_btn:
    # Initialisation des variables de session
    if "adapted_cv" not in st.session_state:
        st.session_state.adapted_cv = ""
    if "cover_letter" not in st.session_state:
        st.session_state.cover_letter = ""

    col_cv, col_letter = st.columns(2, gap="large")

    # ── CV adapté ──────────────────────────────────────────────────────────────
    with col_cv:
        st.markdown("### 📋 CV Adapté")
        with st.spinner("Adaptation du CV en cours..."):
            cv_placeholder = st.empty()
            full_cv = ""
            try:
                for chunk in adapt_cv_stream(
                    cv_content=cv_content,
                    job_posting=job_posting,
                    sector=sector,
                    api_key=api_key,
                    model=model,
                ):
                    full_cv += chunk
                    cv_placeholder.markdown(full_cv)
                st.session_state.adapted_cv = full_cv
                st.success("✅ CV adapté généré !")
            except Exception as e:
                st.error(f"Erreur : {e}")

    # ── Lettre de motivation ───────────────────────────────────────────────────
    with col_letter:
        st.markdown("### ✉️ Lettre de Motivation")
        with st.spinner("Rédaction de la lettre en cours..."):
            letter_placeholder = st.empty()
            full_letter = ""
            try:
                for chunk in generate_cover_letter_stream(
                    cv_content=cv_content,
                    job_posting=job_posting,
                    sector=sector,
                    company_name=company_name,
                    applicant_name=applicant_name,
                    api_key=api_key,
                    model=model,
                ):
                    full_letter += chunk
                    letter_placeholder.markdown(full_letter)
                st.session_state.cover_letter = full_letter
                st.success("✅ Lettre de motivation générée !")
            except Exception as e:
                st.error(f"Erreur : {e}")

    # ── Téléchargements ────────────────────────────────────────────────────────
    if st.session_state.get("adapted_cv") and st.session_state.get("cover_letter"):
        st.divider()
        st.markdown("### 💾 Télécharger les documents")

        dl_col1, dl_col2, dl_col3, dl_col4 = st.columns(4)

        adapted_cv = st.session_state.adapted_cv
        cover_letter = st.session_state.cover_letter

        with dl_col1:
            if DOCX_AVAILABLE:
                try:
                    cv_docx = export_to_docx(adapted_cv, "cv_adapte.docx")
                    st.download_button(
                        label="📥 CV adapté (.docx)",
                        data=cv_docx,
                        file_name="cv_adapte.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                    )
                except Exception as e:
                    st.warning(f"Export DOCX indisponible : {e}")

        with dl_col2:
            st.download_button(
                label="📥 CV adapté (.txt)",
                data=adapted_cv.encode("utf-8"),
                file_name="cv_adapte.txt",
                mime="text/plain",
                use_container_width=True,
            )

        with dl_col3:
            if DOCX_AVAILABLE:
                try:
                    letter_docx = export_to_docx(cover_letter, "lettre_motivation.docx")
                    st.download_button(
                        label="📥 Lettre (.docx)",
                        data=letter_docx,
                        file_name="lettre_motivation.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                    )
                except Exception as e:
                    st.warning(f"Export DOCX indisponible : {e}")

        with dl_col4:
            st.download_button(
                label="📥 Lettre (.txt)",
                data=cover_letter.encode("utf-8"),
                file_name="lettre_motivation.txt",
                mime="text/plain",
                use_container_width=True,
            )

# ─── Affichage si résultats déjà en session (après régénération) ───────────────

elif st.session_state.get("adapted_cv") and st.session_state.get("cover_letter"):
    col_cv, col_letter = st.columns(2, gap="large")
    with col_cv:
        st.markdown("### 📋 CV Adapté (dernier résultat)")
        st.markdown(st.session_state.adapted_cv)
    with col_letter:
        st.markdown("### ✉️ Lettre de Motivation (dernier résultat)")
        st.markdown(st.session_state.cover_letter)
