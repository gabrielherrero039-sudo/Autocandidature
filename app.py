"""
app.py — AutoCandidature
Recherche d'offres · Adaptation IA · Édition · Envoi automatique
"""

import os
import time
import streamlit as st

st.set_page_config(
    page_title="AutoCandidature",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS (compatible mode clair ET sombre) ─────────────────────────────────────

st.markdown("""
<style>
/* ── Header ── */
.app-header {
    background: linear-gradient(135deg, #1E40AF 0%, #3B82F6 100%);
    border-radius: 16px; padding: 1.6rem 2rem; margin-bottom: 1.5rem;
    display: flex; align-items: center; gap: 1.2rem;
}
.app-header h1 { color: white !important; margin: 0; font-size: 1.7rem; font-weight: 700; }
.app-header p  { color: #BFDBFE !important; margin: 0.2rem 0 0; font-size: 0.9rem; }
.badge { background:#FCD34D; color:#1E3A8A; border-radius:99px; padding:2px 10px; font-size:0.72rem; font-weight:700; }

/* ── Cards : fond adaptatif (fonctionne clair + sombre) ── */
.card {
    background: var(--secondary-background-color);
    border-radius: 12px; padding: 1.2rem 1.4rem;
    margin-bottom: 0.8rem;
    border-left: 4px solid #3B82F6;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}
.card-green  { border-left-color: #22C55E; }
.card-amber  { border-left-color: #F59E0B; }
.card-purple { border-left-color: #8B5CF6; }

/* ── Job cards ── */
.job-title { font-size: 0.97rem; font-weight: 700; margin: 0 0 0.2rem; }
.job-meta  { font-size: 0.82rem; opacity: 0.65; margin: 0; }

/* ── Pills / badges ── */
.pill {
    display: inline-block; border-radius: 99px;
    padding: 2px 9px; font-size: 0.73rem; font-weight: 600;
    margin-right: 3px; margin-top: 3px;
}
/* Couleurs de pills avec fond + texte explicites pour lisibilité dans les deux modes */
.pill-blue   { background: #DBEAFE; color: #1E40AF; }
.pill-green  { background: #DCFCE7; color: #15803D; }
.pill-amber  { background: #FEF3C7; color: #92400E; }
.pill-rose   { background: #FFE4E6; color: #BE123C; }
.pill-slate  { background: #E2E8F0; color: #334155; }
.pill-email  { background: #D1FAE5; color: #065F46; }

/* ── Stat tiles ── */
.stat-tile {
    background: var(--secondary-background-color);
    border-radius: 12px; padding: 0.9rem 0.5rem;
    text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.stat-tile .num { font-size: 1.9rem; font-weight: 800; line-height: 1; }
.stat-tile .lbl { font-size: 0.72rem; opacity: 0.6; margin-top: 0.2rem; }

/* ── Status boxes (notifications) ── */
.sbox { border-radius: 8px; padding: 0.5rem 0.9rem; font-size: 0.87rem; margin: 0.3rem 0; }
.sbox-ok   { background: #DCFCE7; color: #14532D; border: 1px solid #86EFAC; }
.sbox-warn { background: #FEF9C3; color: #713F12; border: 1px solid #FDE047; }
.sbox-info { background: #DBEAFE; color: #1E3A8A; border: 1px solid #93C5FD; }
.sbox-err  { background: #FFE4E6; color: #9F1239; border: 1px solid #FCA5A5; }

/* ── Labels éditeur ── */
.editor-label {
    font-size: 0.78rem; font-weight: 700; opacity: 0.55;
    letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 0.3rem;
}

/* ── Séparateur de job ── */
.job-sep { border: none; border-top: 1px solid rgba(128,128,128,0.15); margin: 0.5rem 0; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="app-header">
  <span style="font-size:2.8rem">🎯</span>
  <div>
    <h1>AutoCandidature &nbsp;<span class="badge">100 % GRATUIT</span></h1>
    <p>Recherchez des offres · Adaptez votre CV par IA · Éditez · Postulez automatiquement</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────

def _init(key, val):
    if key not in st.session_state:
        st.session_state[key] = val

_init("cv_content", "")
_init("search_results", [])
_init("selected_jobs", [])
_init("generated_docs", {})
_init("provider", "ollama")
_init("ollama_models", [])
_init("ollama_ok", None)
_init("ollama_url", "http://localhost:11434")
_init("ollama_model_sel", "")
_init("groq_key", "")
_init("groq_model_sel", "llama-3.3-70b-versatile")
_init("sender_name", "")
_init("sender_email", "")
_init("sender_phone", "")
_init("smtp_host", "smtp.gmail.com")
_init("smtp_port", 587)
_init("smtp_user", "")
_init("smtp_password", "")
_init("smtp_ok", None)

@st.cache_resource
def get_tracker():
    from auto_apply import ApplicationTracker
    return ApplicationTracker("candidatures.json")

tracker = get_tracker()

# ── Petits helpers ────────────────────────────────────────────────────────────

def pill(text, style="slate"):
    return f'<span class="pill pill-{style}">{text}</span>'

def sbox(text, kind="info"):
    st.markdown(f'<div class="sbox sbox-{kind}">{text}</div>', unsafe_allow_html=True)

def contract_style(ct):
    ct_l = ct.lower()
    if "cdi" in ct_l:                        return "green"
    if "cdd" in ct_l:                        return "amber"
    if "stage" in ct_l or "alter" in ct_l:  return "blue"
    if "inter" in ct_l or "mis" in ct_l:    return "rose"
    return "slate"

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚙️ Configuration")

    # CV
    st.markdown("---")
    st.markdown("### 📄 Votre CV")
    uploaded = st.file_uploader("CV", type=["pdf", "docx", "doc", "txt"], label_visibility="collapsed")
    if uploaded:
        try:
            from cv_loader import load_cv
            content = load_cv(uploaded.read(), uploaded.name)
            if content.strip():
                st.session_state.cv_content = content
                sbox(f"✅ CV chargé ({len(content)} car.)", "ok")
            else:
                sbox("⚠️ Aucun texte extrait", "warn")
        except Exception as e:
            sbox(f"❌ {e}", "err")

    if st.session_state.cv_content:
        st.caption(f"✅ CV prêt — {len(st.session_state.cv_content)} caractères")
    else:
        sbox("Importez votre CV pour commencer", "warn")

    # IA
    st.markdown("---")
    st.markdown("### 🤖 Moteur IA")
    prov = st.radio("IA", ["ollama", "groq"],
        format_func=lambda x: "🖥️ Ollama (local)" if x == "ollama" else "☁️ Groq (gratuit)",
        index=0 if st.session_state.provider == "ollama" else 1,
        label_visibility="collapsed")
    st.session_state.provider = prov

    if prov == "ollama":
        st.session_state.ollama_url = st.text_input(
            "URL Ollama", value=st.session_state.ollama_url,
            label_visibility="collapsed", placeholder="http://localhost:11434")
        if st.button("🔍 Vérifier Ollama", use_container_width=True):
            import requests as _r
            try:
                r = _r.get(st.session_state.ollama_url.rstrip("/") + "/api/tags", timeout=3)
                if r.status_code == 200:
                    st.session_state.ollama_models = [m["name"] for m in r.json().get("models", [])]
                    st.session_state.ollama_ok = True
                else:
                    st.session_state.ollama_ok = False
            except Exception:
                st.session_state.ollama_ok = False

        if st.session_state.ollama_ok is True:
            sbox(f"✅ {len(st.session_state.ollama_models)} modèle(s) disponible(s)", "ok")
        elif st.session_state.ollama_ok is False:
            sbox("❌ Ollama non trouvé — ollama.com", "err")

        opts = st.session_state.ollama_models or ["llama3.2", "mistral", "llama3.1", "gemma2"]
        idx  = opts.index(st.session_state.ollama_model_sel) if st.session_state.ollama_model_sel in opts else 0
        st.session_state.ollama_model_sel = st.selectbox("Modèle", opts, index=idx, label_visibility="collapsed")

    else:
        st.session_state.groq_key = st.text_input(
            "Clé API Groq", type="password",
            value=st.session_state.groq_key, placeholder="gsk_...",
            label_visibility="collapsed")
        from job_adapter import GROQ_MODELS
        idx = GROQ_MODELS.index(st.session_state.groq_model_sel) if st.session_state.groq_model_sel in GROQ_MODELS else 0
        st.session_state.groq_model_sel = st.selectbox("Modèle Groq", GROQ_MODELS, index=idx, label_visibility="collapsed")
        if st.session_state.groq_key:
            sbox("✅ Clé renseignée", "ok")

    # Email
    st.markdown("---")
    st.markdown("### 📧 Expéditeur")
    st.session_state.sender_name  = st.text_input("Nom complet",  value=st.session_state.sender_name,  placeholder="Jean Dupont",      label_visibility="collapsed")
    st.session_state.sender_email = st.text_input("Votre email",  value=st.session_state.sender_email, placeholder="jean@gmail.com",   label_visibility="collapsed")
    st.session_state.sender_phone = st.text_input("Téléphone",    value=st.session_state.sender_phone, placeholder="06 12 34 56 78",   label_visibility="collapsed")

    from auto_apply import SMTP_PRESETS
    preset_name = st.selectbox("Fournisseur", list(SMTP_PRESETS.keys()), label_visibility="collapsed")
    p = SMTP_PRESETS[preset_name]
    smtp_host = p["host"] or st.text_input("Serveur SMTP", value=st.session_state.smtp_host, label_visibility="collapsed")
    smtp_port = p["port"]
    smtp_user = st.text_input("Login",       value=st.session_state.smtp_user,     label_visibility="collapsed")
    smtp_pass = st.text_input("Mot de passe", type="password", value=st.session_state.smtp_password, label_visibility="collapsed")
    if p.get("info"):
        st.caption(f"ℹ️ {p['info']}")
    if st.button("🔌 Tester la connexion", use_container_width=True):
        from auto_apply import test_smtp_connection
        ok, err = test_smtp_connection(smtp_host, smtp_port, smtp_user, smtp_pass)
        if ok:
            st.session_state.smtp_ok       = True
            st.session_state.smtp_host     = smtp_host
            st.session_state.smtp_port     = smtp_port
            st.session_state.smtp_user     = smtp_user
            st.session_state.smtp_password = smtp_pass
            sbox("✅ Email configuré", "ok")
        else:
            st.session_state.smtp_ok = False
            sbox(f"❌ {err}", "err")
    if st.session_state.smtp_ok:
        sbox("✅ Email prêt à l'envoi", "ok")

# ── Onglets ───────────────────────────────────────────────────────────────────

tab_search, tab_apply, tab_track = st.tabs([
    "🔍  Recherche & Sélection",
    "✏️  Révision & Candidature",
    "📊  Suivi",
])

# ══════════════════════════════════════════════════════════════════
# ONGLET 1 — RECHERCHE & SÉLECTION
# ══════════════════════════════════════════════════════════════════

with tab_search:

    # Formulaire
    c1, c2, c3 = st.columns([3, 2, 1])
    with c1: keywords = st.text_input("🔎 Métier / mots-clés", placeholder="Ex : data analyst, comptable, développeur…")
    with c2: location = st.text_input("📍 Ville ou région",    placeholder="Ex : Paris, Lyon, Bordeaux…")
    with c3: distance = st.selectbox("📏 Rayon (km)", [10, 20, 30, 50, 100], index=2)

    with st.expander("⚙️ Filtres avancés"):
        a1, a2, a3 = st.columns(3)
        with a1:
            from job_scraper import CONTRACT_TYPES, JOBSPY_SITES
            contract = st.selectbox("Type de contrat", list(CONTRACT_TYPES.keys()))
        with a2:
            max_res = st.selectbox("Offres par site", [20, 50, 100, 200], index=1)
        with a3:
            site_choice = st.selectbox("Sites de recherche", list(JOBSPY_SITES.keys()), index=4)

    if st.button("🚀 Lancer la recherche", type="primary", use_container_width=True):
        if not keywords.strip():
            sbox("⚠️ Saisissez des mots-clés.", "warn")
        else:
            from job_scraper import JOBSPY_SITES, CONTRACT_TYPES, search_with_jobspy, deduplicate
            sites = JOBSPY_SITES[site_choice]
            job_type = CONTRACT_TYPES.get(contract, "")

            with st.spinner(f"Recherche sur {site_choice}…"):
                try:
                    raw, counts, errs = search_with_jobspy(
                        keywords=keywords,
                        location=location or "France",
                        sites=sites,
                        max_results=max_res,
                        job_type=job_type,
                        distance=distance,
                    )
                    st.session_state.search_results = deduplicate(raw)
                    st.session_state.selected_jobs  = []

                    # Résumé par site
                    total = len(st.session_state.search_results)
                    detail = "  ·  ".join(f"{s} : {n}" for s, n in counts.items())
                    if total > 0:
                        sbox(f"✅ {total} offre(s) après dédoublonnage — {detail}", "ok")
                    else:
                        sbox(f"⚠️ Aucun résultat — {detail}", "warn")
                    for e in errs:
                        sbox(f"⚠️ {e}", "warn")
                except ImportError:
                    sbox("❌ Installez python-jobspy : pip install python-jobspy --break-system-packages", "err")
                except Exception as e:
                    sbox(f"⚠️ {e}", "warn")
            st.rerun()

    # Résultats
    results     = st.session_state.search_results
    selected_ids = {j.id for j in st.session_state.selected_jobs}

    if results:
        n_total = len(results)
        n_sel   = len(st.session_state.selected_jobs)
        n_email = sum(1 for j in results if j.contact_email)

        k1, k2, k3, k4 = st.columns(4)
        for col, num, lbl, color in [
            (k1, n_total,           "Offres trouvées",  "#3B82F6"),
            (k2, n_email,           "Avec email",        "#22C55E"),
            (k3, n_sel,             "Sélectionnées",     "#8B5CF6"),
            (k4, n_total - n_sel,   "Non sélectionnées","#94A3B8"),
        ]:
            with col:
                st.markdown(f'<div class="stat-tile"><div class="num" style="color:{color}">{num}</div><div class="lbl">{lbl}</div></div>', unsafe_allow_html=True)

        st.markdown("")

        # Actions rapides
        qa1, qa2, qa3, qa4 = st.columns([2, 2, 1, 1])
        with qa1: view       = st.radio("Vue", ["Liste", "Par contrat", "Par source"], horizontal=True, label_visibility="collapsed")
        with qa2: email_only = st.checkbox("Avec email uniquement")
        with qa3:
            if st.button("✅ Tout", use_container_width=True):
                st.session_state.selected_jobs = [j for j in results if not email_only or j.contact_email]
                st.rerun()
        with qa4:
            if st.button("❌ Aucun", use_container_width=True):
                st.session_state.selected_jobs = []
                st.rerun()

        filtered = [j for j in results if not email_only or j.contact_email]

        from job_scraper import group_by_contract, group_by_source
        if   view == "Par contrat": groups = group_by_contract(filtered)
        elif view == "Par source":  groups = group_by_source(filtered)
        else:                       groups = {"Toutes les offres": filtered}

        gi = 0
        for grp_name, grp_jobs in groups.items():
            with st.expander(f"**{grp_name}** — {len(grp_jobs)} offre(s)", expanded=True):
                for job in grp_jobs:
                    is_sel = job.id in selected_ids
                    cb_col, main_col, link_col = st.columns([0.06, 0.78, 0.16])

                    with cb_col:
                        checked = st.checkbox("", value=is_sel, key=f"chk_{job.id}_{gi}")
                        if checked and not is_sel:
                            st.session_state.selected_jobs.append(job)
                            st.rerun()
                        elif not checked and is_sel:
                            st.session_state.selected_jobs = [j for j in st.session_state.selected_jobs if j.id != job.id]
                            st.rerun()

                    with main_col:
                        ct_sty   = contract_style(job.contract_type)
                        email_p  = pill("✉️ Email", "email") if job.contact_email else ""
                        salary_p = pill(f"💰 {job.salary}", "slate") if job.salary else ""
                        st.markdown(
                            f'<p class="job-title">{job.title}</p>'
                            f'<p class="job-meta">🏢 {job.company} · 📍 {job.location} · 🏷️ {job.source}'
                            + (f' · 📅 {job.date_posted}' if job.date_posted else '') + '</p>'
                            f'<div style="margin-top:4px">{pill(job.contract_type, ct_sty)}{email_p}{salary_p}</div>'
                            f'<p style="font-size:0.82rem;opacity:0.7;margin:0.4rem 0 0">{job.short_description(160)}</p>',
                            unsafe_allow_html=True)

                    with link_col:
                        st.markdown(f'<a href="{job.url}" target="_blank" style="font-size:0.82rem;color:#3B82F6">🔗 Voir l\'offre</a>', unsafe_allow_html=True)

                    st.markdown('<hr class="job-sep">', unsafe_allow_html=True)
                    gi += 1

        if n_sel > 0:
            st.success(f"**{n_sel} offre(s) sélectionnée(s)** — allez dans l'onglet ✏️ Révision & Candidature")
    else:
        st.markdown('<div style="text-align:center;padding:3rem;opacity:0.45"><div style="font-size:3rem">🔍</div><p>Lancez une recherche pour trouver des offres</p></div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
# ONGLET 2 — RÉVISION & CANDIDATURE
# ══════════════════════════════════════════════════════════════════

with tab_apply:
    selected = st.session_state.selected_jobs

    if not selected:
        sbox("ℹ️ Sélectionnez des offres dans l'onglet 🔍 Recherche & Sélection", "info")
        st.stop()
    if not st.session_state.cv_content.strip():
        sbox("⚠️ Importez votre CV dans la barre latérale", "warn")
        st.stop()

    n_sel   = len(selected)
    n_gen   = sum(1 for j in selected if j.id in st.session_state.generated_docs)
    n_email = sum(1 for j in selected if j.contact_email)

    k1, k2, k3, k4 = st.columns(4)
    for col, num, lbl, color in [
        (k1, n_sel,           "Sélectionnées",    "#3B82F6"),
        (k2, n_gen,           "Docs générés",      "#22C55E"),
        (k3, n_email,         "Avec email",        "#8B5CF6"),
        (k4, n_sel - n_email, "Via navigateur",    "#F59E0B"),
    ]:
        with col:
            st.markdown(f'<div class="stat-tile"><div class="num" style="color:{color}">{num}</div><div class="lbl">{lbl}</div></div>', unsafe_allow_html=True)

    st.markdown("")

    # ── Génération IA ─────────────────────────────────────────────────────────
    provider  = st.session_state.provider
    model     = st.session_state.ollama_model_sel if provider == "ollama" else st.session_state.groq_model_sel
    api_key   = st.session_state.groq_key if provider == "groq" else ""
    ai_url    = st.session_state.ollama_url.rstrip("/") + "/v1" if provider == "ollama" else ""

    not_yet = [j for j in selected if j.id not in st.session_state.generated_docs]

    with st.expander("⚡ Générer les documents IA", expanded=(n_gen == 0)):
        sector_hint = st.text_input("Secteur / domaine *(optionnel)*",
            placeholder="Ex : Informatique, Finance, Marketing…")

        gc1, gc2 = st.columns([3, 1])
        with gc1:
            lbl_gen = f"⚡ Générer pour les {len(not_yet)} offre(s) restante(s)" if not_yet else "✅ Tout déjà généré"
            gen_new = st.button(lbl_gen, type="primary", use_container_width=True,
                                disabled=(not model or not not_yet))
        with gc2:
            gen_all = st.button("🔄 Tout regénérer", use_container_width=True, disabled=not model)

        jobs_to_do = selected if gen_all else (not_yet if gen_new else [])

        if jobs_to_do:
            if not model:
                sbox("⚠️ Sélectionnez un modèle dans la barre latérale", "warn")
            else:
                from job_adapter import adapt_cv_streamed, generate_cover_letter_streamed, generate_canva_guide_streamed
                from cv_loader import generate_docx_from_text
                from cv_formatter import convert_docx_to_pdf

                progress  = st.progress(0, text="Démarrage…")
                status_ph = st.empty()

                for i, job in enumerate(jobs_to_do):
                    progress.progress(i / len(jobs_to_do),
                        text=f"[{i+1}/{len(jobs_to_do)}] {job.title} — {job.company}")

                    common_args = dict(
                        cv_content=st.session_state.cv_content,
                        job_posting=job.description,
                        job_sector=sector_hint or job.domain or "général",
                        provider=provider, model=model,
                        api_key=api_key, ollama_url=ai_url,
                    )

                    # Adaptation CV
                    cv_text = ""
                    try:
                        for chunk in adapt_cv_streamed(**common_args):
                            cv_text += chunk
                    except Exception as e:
                        status_ph.warning(f"⚠️ CV '{job.title}' : {e}")
                        cv_text = st.session_state.cv_content

                    # Lettre de motivation
                    letter = ""
                    try:
                        for chunk in generate_cover_letter_streamed(**common_args):
                            letter += chunk
                    except Exception as e:
                        status_ph.warning(f"⚠️ Lettre '{job.title}' : {e}")

                    # Guide Canva
                    canva_guide = ""
                    try:
                        for chunk in generate_canva_guide_streamed(**common_args):
                            canva_guide += chunk
                    except Exception as e:
                        status_ph.warning(f"⚠️ Guide Canva '{job.title}' : {e}")

                    # DOCX + PDF
                    cv_docx, cv_pdf, letter_docx, guide_docx = None, None, None, None
                    try:
                        cv_docx = generate_docx_from_text("CV Adapté", cv_text)
                        cv_pdf, _ = convert_docx_to_pdf(cv_docx)
                    except Exception:
                        pass
                    try:
                        letter_docx = generate_docx_from_text("Lettre de Motivation", letter)
                    except Exception:
                        pass
                    try:
                        if canva_guide:
                            guide_docx = generate_docx_from_text(
                                f"Guide modifications CV — {job.title} ({job.company})", canva_guide)
                    except Exception:
                        pass

                    st.session_state.generated_docs[job.id] = {
                        "cv_text": cv_text, "cv_docx": cv_docx, "cv_pdf": cv_pdf,
                        "letter": letter, "letter_docx": letter_docx,
                        "canva_guide": canva_guide, "guide_docx": guide_docx,
                    }
                    tracker.add_or_update(job, "generated", cv_text, letter)

                progress.progress(1.0, text="✅ Terminé !")
                time.sleep(0.4)
                progress.empty()
                status_ph.empty()
                st.success(f"✅ {len(jobs_to_do)} jeu(x) de documents générés !")
                st.rerun()

    # ── Révision par offre ────────────────────────────────────────────────────
    st.markdown("### 📝 Révision — offre par offre")

    from auto_apply import send_email_application, open_in_browser, build_email_subject, build_email_body, extract_email_from_text

    for job in selected:
        doc           = st.session_state.generated_docs.get(job.id)
        ct_sty        = contract_style(job.contract_type)
        contact_email = job.contact_email or (extract_email_from_text(job.description) if doc else "")

        is_done = job.id in st.session_state.generated_docs
        icon    = "✅" if is_done else "⏳"

        with st.expander(f"{icon}  **{job.title}** — {job.company}  ·  {job.location}",
                         expanded=(is_done and n_sel <= 3)):

            # Info
            top_l, top_r = st.columns([4, 1])
            with top_l:
                st.markdown(
                    pill(job.contract_type, ct_sty)
                    + (pill("✉️ " + contact_email, "email") if contact_email else pill("Pas d'email", "slate"))
                    + (pill(f"💰 {job.salary}", "slate") if job.salary else ""),
                    unsafe_allow_html=True)
            with top_r:
                st.markdown(f'<a href="{job.url}" target="_blank" style="color:#3B82F6;font-size:0.85rem">🔗 Offre</a>', unsafe_allow_html=True)

            if not doc:
                sbox("Documents non générés — utilisez le bouton ⚡ ci-dessus", "info")
                continue

            # ── Onglets éditeur ──────────────────────────────────────────────
            ed_cv, ed_letter, ed_canva = st.tabs(["📋 CV adapté", "✉️ Lettre de motivation", "📌 Guide Canva"])

            with ed_cv:
                st.markdown('<div class="editor-label">Éditez le CV — les modifications seront prises en compte au téléchargement</div>', unsafe_allow_html=True)
                edited_cv = st.text_area("CV", value=doc.get("cv_text", ""),
                    height=340, key=f"ecv_{job.id}", label_visibility="collapsed")

                sv1, sv2, sv3 = st.columns([1, 1, 3])
                with sv1:
                    if st.button("💾 Sauvegarder", key=f"scv_{job.id}", use_container_width=True):
                        with st.spinner("Mise à jour…"):
                            try:
                                from cv_loader import generate_docx_from_text
                                from cv_formatter import convert_docx_to_pdf
                                new_docx = generate_docx_from_text("CV Adapté", edited_cv)
                                new_pdf, _ = convert_docx_to_pdf(new_docx)
                                st.session_state.generated_docs[job.id]["cv_text"] = edited_cv
                                st.session_state.generated_docs[job.id]["cv_docx"] = new_docx
                                st.session_state.generated_docs[job.id]["cv_pdf"]  = new_pdf
                                sbox("✅ CV mis à jour", "ok")
                            except Exception as e:
                                sbox(f"❌ {e}", "err")

            with ed_letter:
                st.markdown('<div class="editor-label">Éditez la lettre de motivation</div>', unsafe_allow_html=True)
                edited_letter = st.text_area("Lettre", value=doc.get("letter", ""),
                    height=340, key=f"el_{job.id}", label_visibility="collapsed")

                sl1, sl2 = st.columns([1, 3])
                with sl1:
                    if st.button("💾 Sauvegarder", key=f"sl_{job.id}", use_container_width=True):
                        with st.spinner("Mise à jour…"):
                            try:
                                from cv_loader import generate_docx_from_text
                                new_ldocx = generate_docx_from_text("Lettre de Motivation", edited_letter)
                                st.session_state.generated_docs[job.id]["letter"]      = edited_letter
                                st.session_state.generated_docs[job.id]["letter_docx"] = new_ldocx
                                sbox("✅ Lettre mise à jour", "ok")
                            except Exception as e:
                                sbox(f"❌ {e}", "err")

            with ed_canva:
                canva_guide = doc.get("canva_guide", "")
                guide_docx  = st.session_state.generated_docs[job.id].get("guide_docx")

                if canva_guide:
                    st.markdown(
                        '<div class="sbox sbox-info" style="margin-bottom:0.8rem">'
                        '📌 <strong>Guide personnalisé</strong> — liste des modifications à apporter directement dans Canva pour adapter votre CV à cette offre.'
                        '</div>', unsafe_allow_html=True)
                    st.markdown(canva_guide)

                    if guide_docx:
                        safe_g = job.company.replace(" ", "_")[:20]
                        st.download_button(
                            "📥 Télécharger le guide (.docx)", guide_docx,
                            file_name=f"guide_canva_{safe_g}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"dguide_{job.id}", use_container_width=True)
                else:
                    sbox("Guide non généré — utilisez le bouton ⚡ ci-dessus", "info")

            st.markdown("---")

            # ── Téléchargements ──────────────────────────────────────────────
            st.markdown('<div class="editor-label">Télécharger</div>', unsafe_allow_html=True)
            safe     = job.company.replace(" ", "_")[:20]
            cv_docx  = st.session_state.generated_docs[job.id].get("cv_docx")
            cv_pdf   = st.session_state.generated_docs[job.id].get("cv_pdf")
            ltr_docx = st.session_state.generated_docs[job.id].get("letter_docx")
            gde_docx = st.session_state.generated_docs[job.id].get("guide_docx")

            d1, d2, d3, d4 = st.columns(4)
            with d1:
                if cv_docx:
                    st.download_button("📥 CV .docx", cv_docx,
                        file_name=f"cv_{safe}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"dcvd_{job.id}", use_container_width=True)
            with d2:
                if cv_pdf:
                    st.download_button("📥 CV .pdf", cv_pdf,
                        file_name=f"cv_{safe}.pdf", mime="application/pdf",
                        key=f"dcvp_{job.id}", use_container_width=True)
                elif cv_docx:
                    st.caption("PDF : Fichier → Exporter dans Word")
            with d3:
                if ltr_docx:
                    st.download_button("📥 Lettre .docx", ltr_docx,
                        file_name=f"lettre_{safe}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"dltrd_{job.id}", use_container_width=True)
            with d4:
                if gde_docx:
                    st.download_button("📌 Guide Canva .docx", gde_docx,
                        file_name=f"guide_{safe}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"dguided_{job.id}", use_container_width=True)

            # ── Postuler ─────────────────────────────────────────────────────
            st.markdown('<div class="editor-label" style="margin-top:0.8rem">Postuler</div>', unsafe_allow_html=True)
            ap1, ap2 = st.columns(2)

            with ap1:
                if contact_email:
                    if st.session_state.smtp_ok and st.session_state.smtp_user:
                        if st.button(f"✉️ Envoyer à {contact_email}", key=f"send_{job.id}",
                                     use_container_width=True, type="primary"):
                            cur_letter = st.session_state.generated_docs[job.id].get("letter", "")
                            ok, err = send_email_application(
                                to_email=contact_email,
                                subject=build_email_subject(job, st.session_state.sender_name),
                                body_text=build_email_body(job, cur_letter,
                                    st.session_state.sender_name,
                                    st.session_state.sender_email,
                                    st.session_state.sender_phone),
                                smtp_host=st.session_state.smtp_host,
                                smtp_port=st.session_state.smtp_port,
                                smtp_user=st.session_state.smtp_user,
                                smtp_password=st.session_state.smtp_password,
                                cv_bytes=st.session_state.generated_docs[job.id].get("cv_docx"),
                                cv_filename=f"CV_{st.session_state.sender_name.replace(' ','_')}.docx",
                                letter_bytes=st.session_state.generated_docs[job.id].get("letter_docx"),
                                letter_filename=f"Lettre_{st.session_state.sender_name.replace(' ','_')}.docx",
                            )
                            if ok:
                                tracker.update_status(job.id, "sent")
                                sbox(f"✅ Email envoyé à {contact_email} !", "ok")
                            else:
                                sbox(f"❌ {err}", "err")
                    else:
                        sbox(f"Configurez l'email (barre latérale) pour envoyer à {contact_email}", "info")
                else:
                    sbox("Aucun email de contact détecté", "info")

            with ap2:
                if st.button("🌐 Ouvrir dans le navigateur", key=f"open_{job.id}", use_container_width=True):
                    open_in_browser(job.url)
                    tracker.update_status(job.id, "opened")
                    sbox("✅ Offre ouverte dans le navigateur", "ok")


# ══════════════════════════════════════════════════════════════════
# ONGLET 3 — SUIVI
# ══════════════════════════════════════════════════════════════════

with tab_track:
    STATUS_MAP = {
        "pending":   ("⏳", "En attente",   "#94A3B8"),
        "generated": ("📄", "Docs générés", "#3B82F6"),
        "sent":      ("✉️",  "Envoyée",      "#22C55E"),
        "opened":    ("🌐", "Ouvert",        "#F59E0B"),
        "rejected":  ("❌", "Refusée",       "#EF4444"),
        "interview": ("🎯", "Entretien",     "#8B5CF6"),
        "offer":     ("🎉", "Offre reçue",  "#F59E0B"),
    }

    stats    = tracker.get_stats()
    all_apps = tracker.get_all()

    # KPIs
    kcols = st.columns(7)
    for col, (key, (icon, label, color)) in zip(kcols, STATUS_MAP.items()):
        with col:
            st.markdown(
                f'<div class="stat-tile">'
                f'<div class="num" style="color:{color}">{stats.get(key, 0)}</div>'
                f'<div class="lbl">{icon} {label}</div></div>',
                unsafe_allow_html=True)

    st.markdown("")

    if not all_apps:
        sbox("Aucune candidature enregistrée. Commencez par rechercher des offres !", "info")
    else:
        fc1, fc2 = st.columns([4, 1])
        with fc1:
            status_filter = st.multiselect(
                "Statuts", list(STATUS_MAP.keys()),
                format_func=lambda x: f"{STATUS_MAP[x][0]} {STATUS_MAP[x][1]}",
                default=list(STATUS_MAP.keys()),
                label_visibility="collapsed")
        with fc2:
            if st.button("📥 CSV", use_container_width=True):
                import csv, io as _io
                buf = _io.StringIO()
                w = csv.DictWriter(buf, fieldnames=["title","company","location","contract_type","status","contact_email","url","updated_at"])
                w.writeheader()
                [w.writerow({k: a.get(k,"") for k in w.fieldnames}) for a in all_apps]
                st.download_button("Télécharger", buf.getvalue().encode(), "candidatures.csv", "text/csv")

        for app in sorted(all_apps, key=lambda x: x.get("updated_at",""), reverse=True):
            st_key = app.get("status", "pending")
            if st_key not in status_filter:
                continue
            icon, label, color = STATUS_MAP.get(st_key, ("❓", st_key, "#94A3B8"))

            with st.expander(f"{icon} **{app.get('title','')}** — {app.get('company','')}  |  {label}"):
                ci1, ci2 = st.columns([3, 1])
                with ci1:
                    st.markdown(
                        f"📍 {app.get('location','')} &nbsp;·&nbsp; 📋 {app.get('contract_type','')}"
                        + (f"<br>✉️ {app.get('contact_email','')}" if app.get('contact_email') else "")
                        + f"<br><small>Mis à jour : {app.get('updated_at','')[:10]}</small>",
                        unsafe_allow_html=True)
                    if app.get("url"):
                        _url = app["url"]
                        st.markdown(f'<a href="{_url}" target="_blank">🔗 Voir l\'offre</a>', unsafe_allow_html=True)
                with ci2:
                    new_s = st.selectbox("Statut",
                        list(STATUS_MAP.keys()),
                        format_func=lambda x: f"{STATUS_MAP[x][0]} {STATUS_MAP[x][1]}",
                        index=list(STATUS_MAP.keys()).index(st_key),
                        key=f"ts_{app.get('job_id','')}",
                        label_visibility="collapsed")
                    sc1, sc2 = st.columns(2)
                    with sc1:
                        if st.button("💾", key=f"sv_{app.get('job_id','')}", use_container_width=True):
                            tracker.update_status(app.get("job_id",""), new_s)
                            st.rerun()
                    with sc2:
                        if st.button("🗑️", key=f"dl_{app.get('job_id','')}", use_container_width=True):
                            tracker.delete(app.get("job_id",""))
                            st.rerun()

                # ── Consultation des documents ────────────────────────────────
                adapted_cv   = app.get("adapted_cv", "")
                cover_letter = app.get("cover_letter", "")
                if adapted_cv or cover_letter:
                    st.markdown('<div class="editor-label" style="margin-top:0.6rem">Documents générés</div>', unsafe_allow_html=True)
                    doc_tabs = []
                    tab_labels = []
                    if adapted_cv:   tab_labels.append("📋 CV adapté")
                    if cover_letter: tab_labels.append("✉️ Lettre de motivation")
                    doc_tabs = st.tabs(tab_labels)

                    tab_idx = 0
                    if adapted_cv:
                        with doc_tabs[tab_idx]:
                            st.text_area("CV", value=adapted_cv, height=280,
                                key=f"track_cv_{app.get('job_id','')}",
                                label_visibility="collapsed", disabled=True)
                            try:
                                from cv_loader import generate_docx_from_text
                                _safe = app.get("company","job").replace(" ","_")[:20]
                                _cv_docx = generate_docx_from_text("CV Adapté", adapted_cv)
                                st.download_button("📥 Télécharger CV .docx", _cv_docx,
                                    file_name=f"cv_{_safe}.docx",
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    key=f"tdl_cv_{app.get('job_id','')}", use_container_width=True)
                            except Exception:
                                pass
                        tab_idx += 1

                    if cover_letter:
                        with doc_tabs[tab_idx]:
                            st.text_area("Lettre", value=cover_letter, height=280,
                                key=f"track_ltr_{app.get('job_id','')}",
                                label_visibility="collapsed", disabled=True)
                            try:
                                from cv_loader import generate_docx_from_text
                                _safe = app.get("company","job").replace(" ","_")[:20]
                                _ltr_docx = generate_docx_from_text("Lettre de Motivation", cover_letter)
                                st.download_button("📥 Télécharger Lettre .docx", _ltr_docx,
                                    file_name=f"lettre_{_safe}.docx",
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    key=f"tdl_ltr_{app.get('job_id','')}", use_container_width=True)
                            except Exception:
                                pass
