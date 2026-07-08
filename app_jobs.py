"""
AutoCandidature IA — Recherche d'emploi sans clé API obligatoire
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sources GRATUITES sans inscription :
  • HelloWork     — emplois France (moteur principal)
  • France Travail— offres Pôle Emploi officielles
  • The Muse      — offres internationales
  • Remotive      — offres full remote
  • Arbeitnow     — offres Europe

Clés OPTIONNELLES pour plus de résultats :
  • Jooble        — 140 000 sites (LinkedIn, Indeed, WTTJ…)
  • Adzuna        — Indeed FR, Cadremploi, Monster

Claude IA : expansion du domaine + résumé de l'offre + candidature
"""

import io, re, json, time
import concurrent.futures
import requests
import streamlit as st
import anthropic

# ══════════════════════════════════════════════════════════════════
# UTILITAIRES
# ══════════════════════════════════════════════════════════════════

def clean_html(t: str) -> str:
    t = re.sub(r"<[^>]+>", " ", str(t))
    t = re.sub(r"&[a-zA-Z]+;", " ", t)
    return re.sub(r"\s+", " ", t).strip()

def fmt_salary(mn, mx, cur="€") -> str:
    try:
        if mn and mx:  return f"{int(float(mn)):,} – {int(float(mx)):,} {cur}/an"
        if mn:         return f"Dès {int(float(mn)):,} {cur}/an"
        if mx:         return f"Jusqu'à {int(float(mx)):,} {cur}/an"
    except Exception:  pass
    return ""

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/html, */*",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

def _job(source, title, company, location, description, url,
         salary="", contract="", posted="", is_remote=False):
    return {
        "source": source, "title": title, "company": company,
        "location": location, "description": clean_html(description),
        "url": url, "salary": salary, "contract": contract,
        "posted": str(posted)[:10], "is_remote": is_remote,
        "missions": [], "ai_summary": None,
    }

# ══════════════════════════════════════════════════════════════════
# SOURCES GRATUITES — SANS CLÉ API
# ══════════════════════════════════════════════════════════════════

# ── 1. HelloWork (France, sans clé) ──────────────────────────────

def search_hellowork(keywords: str, location: str, radius: int = 50) -> list[dict]:
    """Moteur d'emploi français — API publique, sans inscription."""
    results = []

    # Tentative 1 : API interne HelloWork
    try:
        r = requests.get(
            "https://www.hellowork.com/fr-fr/emploi/recherche.html",
            params={"k": keywords, "l": location, "ray": radius, "d": "a"},
            headers={**HEADERS, "Accept": "text/html"},
            timeout=12,
        )
        # Extraire le JSON embarqué dans le HTML (Next.js __NEXT_DATA__)
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r.text, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            # Naviguer dans la structure Next.js
            props = data.get("props", {}).get("pageProps", {})
            jobs_raw = (
                props.get("jobs") or
                props.get("initialData", {}).get("jobs") or
                props.get("searchResults", {}).get("jobs") or []
            )
            for item in jobs_raw[:20]:
                results.append(_job(
                    source      = "HelloWork",
                    title       = item.get("title") or item.get("name",""),
                    company     = item.get("companyName") or item.get("company",{}).get("name","N/A"),
                    location    = item.get("city") or item.get("location",""),
                    description = item.get("description") or item.get("excerpt",""),
                    url         = "https://www.hellowork.com" + (item.get("url") or item.get("slug","")),
                    salary      = item.get("salary") or item.get("salaryLabel",""),
                    contract    = item.get("contractType") or item.get("contract",""),
                    posted      = item.get("publishedAt") or item.get("postedAt",""),
                ))
    except Exception:
        pass

    # Tentative 2 : endpoint API alternatif
    if not results:
        try:
            r = requests.get(
                "https://www.hellowork.com/api/v1/search/jobs",
                params={"q": keywords, "location": location, "radius": radius, "page": 1},
                headers=HEADERS, timeout=10,
            )
            if r.status_code == 200:
                for item in r.json().get("jobs", r.json().get("results", []))[:20]:
                    results.append(_job(
                        source      = "HelloWork",
                        title       = item.get("title",""),
                        company     = item.get("company","N/A"),
                        location    = item.get("location",""),
                        description = item.get("description",""),
                        url         = item.get("url",""),
                        salary      = item.get("salary",""),
                        contract    = item.get("contractType",""),
                        posted      = item.get("publishedAt",""),
                    ))
        except Exception:
            pass

    return results

# ── 2. France Travail / Pôle Emploi (sans clé) ───────────────────

def search_france_travail(keywords: str, location: str) -> list[dict]:
    """Offres officielles France Travail via leur flux public."""
    results = []
    try:
        # Endpoint public (sans OAuth) via leur moteur de recherche
        r = requests.get(
            "https://www.francetravail.fr/offre/recherche/index.jspx",
            params={
                "motsCles": keywords,
                "lieuTravail": location,
                "typeContrat": "",
                "offresPartenaires": "true",
                "format": "json",
            },
            headers=HEADERS, timeout=12,
        )
        if r.status_code == 200:
            data = r.json() if r.headers.get("content-type","").startswith("application/json") else {}
            for item in data.get("resultats", [])[:20]:
                results.append(_job(
                    source      = "France Travail",
                    title       = item.get("intitule",""),
                    company     = item.get("entreprise",{}).get("nom","N/A"),
                    location    = item.get("lieuTravail",{}).get("libelle",""),
                    description = item.get("description",""),
                    url         = item.get("origineOffre",{}).get("urlOrigine",""),
                    salary      = item.get("salaire",{}).get("libelle",""),
                    contract    = item.get("typeContrat",""),
                    posted      = item.get("dateCreation",""),
                ))
    except Exception:
        pass

    # Fallback : flux RSS XML de France Travail
    if not results:
        try:
            r = requests.get(
                "https://candidat.francetravail.fr/offres/recherche/rss",
                params={"motsCles": keywords, "commune": location},
                headers=HEADERS, timeout=10,
            )
            items = re.findall(
                r"<item>(.*?)</item>", r.text, re.DOTALL
            )
            for block in items[:20]:
                title   = re.search(r"<title>(.*?)</title>", block)
                link    = re.search(r"<link>(.*?)</link>",   block)
                desc    = re.search(r"<description>(.*?)</description>", block, re.DOTALL)
                company = re.search(r"<author>(.*?)</author>|<enterprise>(.*?)</enterprise>", block)
                results.append(_job(
                    source      = "France Travail",
                    title       = clean_html(title.group(1) if title else ""),
                    company     = clean_html(company.group(1) if company else "N/A"),
                    location    = location,
                    description = clean_html(desc.group(1) if desc else ""),
                    url         = (link.group(1) if link else "").strip(),
                ))
        except Exception:
            pass

    return results

# ── 3. The Muse (international, sans clé) ────────────────────────

def search_the_muse(keywords: str, location: str) -> list[dict]:
    """The Muse — API ouverte, sans inscription, offres internationales."""
    try:
        params = {"page": 0, "descending": "true"}
        # Ajout de la localisation si précisée
        if location:
            params["location"] = location
        r = requests.get(
            "https://www.themuse.com/api/public/jobs",
            params=params,
            headers=HEADERS, timeout=10,
        )
        if r.status_code != 200:
            return []
        results = []
        for item in r.json().get("results", []):
            # Filtre par mots-clés (l'API The Muse ne filtre pas par keyword)
            name = item.get("name","").lower()
            if not any(kw.lower() in name for kw in keywords.split()[:3]):
                continue
            loc = ", ".join(
                l.get("name","") for l in item.get("locations",[]) if l.get("name")
            ) or "International"
            desc = " | ".join(
                c.get("body","") for c in item.get("contents",[])
            )
            results.append(_job(
                source      = "The Muse",
                title       = item.get("name",""),
                company     = item.get("company",{}).get("name","N/A"),
                location    = loc,
                description = clean_html(desc),
                url         = item.get("refs",{}).get("landing_page",""),
                contract    = item.get("type",""),
                posted      = item.get("publication_date",""),
            ))
        return results[:15]
    except Exception:
        return []

# ── 4. Remotive (remote mondial, sans clé) ───────────────────────

def search_remotive(keywords: str) -> list[dict]:
    try:
        r = requests.get(
            "https://remotive.com/api/remote-jobs",
            params={"search": keywords, "limit": 15},
            headers=HEADERS, timeout=10,
        )
        if r.status_code != 200:
            return []
        return [_job(
            source      = "Remotive (Remote)",
            title       = i.get("title",""),
            company     = i.get("company_name","N/A"),
            location    = "🌍 Remote — " + i.get("candidate_required_location","Mondial"),
            description = i.get("description",""),
            url         = i.get("url",""),
            salary      = i.get("salary",""),
            contract    = i.get("job_type",""),
            posted      = i.get("publication_date",""),
            is_remote   = True,
        ) for i in r.json().get("jobs",[])[:15]]
    except Exception:
        return []

# ── 5. Arbeitnow (Europe, sans clé) ──────────────────────────────

def search_arbeitnow(keywords: str, location: str) -> list[dict]:
    """Arbeitnow — Europe, sans clé. Filtre par localisation après."""
    try:
        r = requests.get(
            "https://www.arbeitnow.com/api/job-board-api",
            params={"search": f"{keywords} {location}"},
            headers=HEADERS, timeout=10,
        )
        if r.status_code != 200:
            return []
        results = []
        for i in r.json().get("data", [])[:20]:
            # Filtre : garder seulement si lieu contient la localisation ou "remote"
            loc = i.get("location","")
            results.append(_job(
                source      = "Arbeitnow",
                title       = i.get("title",""),
                company     = i.get("company_name","N/A"),
                location    = loc,
                description = i.get("description",""),
                url         = i.get("url",""),
                contract    = "Remote" if i.get("remote") else "",
                posted      = i.get("published_at",""),
                is_remote   = bool(i.get("remote")),
            ))
        return results
    except Exception:
        return []

# ══════════════════════════════════════════════════════════════════
# SOURCES OPTIONNELLES (avec clé gratuite)
# ══════════════════════════════════════════════════════════════════

def search_jooble(keywords, location, key, radius=50) -> list[dict]:
    if not key: return []
    try:
        payload = {
            "keywords": keywords,
            "location": location,
            "radius": int(radius),
            "resultonpage": 25,
            "page": 1,
        }
        r = requests.post(
            f"https://jooble.org/api/{key}",
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=15,
        )
        if r.status_code != 200: return []
        data = r.json()
        jobs_raw = data.get("jobs") or data.get("Jobs") or []
        return [_job(
            source      = "Jooble",
            title       = i.get("title",""),
            company     = i.get("company","N/A"),
            location    = i.get("location", location),
            description = i.get("snippet",""),
            url         = i.get("link",""),
            salary      = clean_html(i.get("salary","")),
            contract    = i.get("type",""),
            posted      = i.get("updated",""),
        ) for i in jobs_raw[:25]]
    except Exception: return []

def search_adzuna(keywords, location, country, app_id, app_key) -> list[dict]:
    if not app_id or not app_key: return []
    cc = {"France":"fr","Belgique":"be","Suisse":"ch","Canada":"ca",
          "USA":"us","UK":"gb","Allemagne":"de"}.get(country,"fr")
    try:
        r = requests.get(
            f"https://api.adzuna.com/v1/api/jobs/{cc}/search/1",
            params={"app_id":app_id,"app_key":app_key,
                    "results_per_page":20,"what":keywords,"where":location},
            headers=HEADERS, timeout=12,
        )
        if r.status_code != 200: return []
        return [_job(
            source   = "Adzuna",
            title    = i.get("title",""),
            company  = i.get("company",{}).get("display_name","N/A"),
            location = i.get("location",{}).get("display_name", location),
            description = i.get("description",""),
            url      = i.get("redirect_url",""),
            salary   = fmt_salary(i.get("salary_min"), i.get("salary_max")),
            contract = i.get("contract_time",""),
            posted   = i.get("created",""),
        ) for i in r.json().get("results",[])]
    except Exception: return []

# ══════════════════════════════════════════════════════════════════
# FILTRE GÉOGRAPHIQUE
# ══════════════════════════════════════════════════════════════════

COUNTRY_WORDS = {
    "France":    ["france","fr,","(fr)","paris","lyon","marseille","toulouse",
                  "orléans","orleans","bordeaux","lille","nantes","strasbourg",
                  "rennes","montpellier","nice","grenoble","nancy","rouen",
                  "toulon","saint-","ile-de-france","île-de-france","loiret"],
    "Belgique":  ["belgique","belgium","bruxelles","liège","gand","anvers"],
    "Suisse":    ["suisse","switzerland","genève","zurich","berne","lausanne"],
    "Canada":    ["canada","québec","montréal","toronto","vancouver","calgary"],
    "USA":       ["usa","united states","new york","california","texas","chicago"],
    "UK":        ["uk","united kingdom","london","england","manchester"],
    "Allemagne": ["germany","deutschland","berlin","munich","hamburg"],
}

def location_ok(job: dict, city: str, country: str, include_remote: bool) -> bool:
    loc = job.get("location","").lower()
    if job.get("is_remote") or "remote" in loc or "🌍" in job.get("location",""):
        return include_remote
    if not city and not country:
        return True
    if city and city.lower() in loc:
        return True
    for w in COUNTRY_WORDS.get(country, [country.lower()]):
        if w in loc:
            return True
    return False

# ══════════════════════════════════════════════════════════════════
# EXPANSION DU DOMAINE PAR CLAUDE
# ══════════════════════════════════════════════════════════════════

def expand_keywords(keyword: str, api_key: str, model: str) -> list[str]:
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model, max_tokens=120,
            messages=[{"role":"user","content":
                f"Donne 4 titres de postes alternatifs ou connexes à « {keyword} » "
                "pour une recherche d'emploi en France. "
                "Réponds UNIQUEMENT avec les titres séparés par des virgules."}]
        )
        return [k.strip() for k in msg.content[0].text.split(",") if k.strip()][:4]
    except Exception:
        return []

# ══════════════════════════════════════════════════════════════════
# RÉSUMÉ IA DE L'OFFRE
# ══════════════════════════════════════════════════════════════════

def summarize_job(job: dict, api_key: str, model: str) -> dict:
    if not api_key or not job.get("description"):
        return job
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model, max_tokens=500,
            messages=[{"role":"user","content":
                f"""Analyse cette offre et retourne UNIQUEMENT ce JSON :
{{"missions":["m1","m2","m3","m4"],"competences":["c1","c2","c3"],"profil":"profil en 1 phrase","avantages":["a1","a2"],"ambiance":"culture en 1 phrase"}}

Offre : {job['title']} chez {job['company']}
Description : {job['description'][:2500]}"""}]
        )
        m = re.search(r"\{[\s\S]+\}", msg.content[0].text)
        if m:
            job["ai_summary"] = json.loads(m.group())
    except Exception:
        pass
    return job

# ══════════════════════════════════════════════════════════════════
# MOTEUR PARALLÈLE
# ══════════════════════════════════════════════════════════════════

def run_searches(keywords, extra_kws, location, country, radius,
                 include_remote, jooble_key, adzuna_id, adzuna_key) -> list[dict]:

    all_terms = [keywords] + extra_kws
    tasks = []

    for term in all_terms:
        tasks += [
            ("hellowork",     term, location),
            ("france_travail", term, location),
            ("the_muse",      term, location),
            ("arbeitnow",     term, location),
        ]
        if jooble_key:
            tasks.append(("jooble", term, location))
        if adzuna_id and adzuna_key:
            tasks.append(("adzuna", term, location))

    if include_remote:
        tasks.append(("remotive", keywords, ""))

    def run(task):
        src, term, loc = task
        if src == "hellowork":     return search_hellowork(term, loc, radius)
        if src == "france_travail":return search_france_travail(term, loc)
        if src == "the_muse":      return search_the_muse(term, loc)
        if src == "arbeitnow":     return search_arbeitnow(term, loc)
        if src == "remotive":      return search_remotive(term)
        if src == "jooble":        return search_jooble(term, loc, jooble_key, radius)
        if src == "adzuna":        return search_adzuna(term, loc, country, adzuna_id, adzuna_key)
        return []

    raw: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(run, t): t for t in tasks}
        for f in concurrent.futures.as_completed(futs):
            try: raw.extend(f.result())
            except Exception: pass

    # Filtre géo
    filtered = [j for j in raw if location_ok(j, location, country, include_remote)]

    # Dédoublonnage
    seen: set = set()
    unique: list[dict] = []
    for j in filtered:
        key = (j["title"].lower()[:35], j["company"].lower()[:25])
        if key not in seen:
            seen.add(key)
            unique.append(j)

    return unique

# ══════════════════════════════════════════════════════════════════
# GÉNÉRATION CANDIDATURE
# ══════════════════════════════════════════════════════════════════

def load_cv_file(f):
    data = f.read()
    if f.name.lower().endswith(".pdf"):
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                return "\n\n".join(p.extract_text() or "" for p in pdf.pages)
        except Exception: pass
        try:
            import PyPDF2
            r = PyPDF2.PdfReader(io.BytesIO(data))
            return "\n\n".join(p.extract_text() or "" for p in r.pages)
        except Exception: return ""
    if f.name.lower().endswith(".docx"):
        try:
            import docx
            doc = docx.Document(io.BytesIO(data))
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception: return ""
    return data.decode("utf-8", errors="ignore")

def export_docx(content):
    try:
        import docx as dx
        doc = dx.Document()
        for line in content.split("\n"):
            s = line.strip()
            if   s.startswith("# "):  doc.add_heading(s[2:], level=1)
            elif s.startswith("## "): doc.add_heading(s[3:], level=2)
            elif s == "":             doc.add_paragraph("")
            else:
                p = doc.add_paragraph()
                for part in re.split(r"(\*\*[^*]+\*\*)", s):
                    if part.startswith("**") and part.endswith("**"):
                        p.add_run(part[2:-2]).bold = True
                    else: p.add_run(part)
        buf = io.BytesIO(); doc.save(buf); return buf.getvalue()
    except Exception: return None

def stream_cv(cv, job, api_key, model):
    client = anthropic.Anthropic(api_key=api_key)
    with client.messages.stream(
        model=model, max_tokens=4096,
        system="Expert en CV. Adapte le CV au poste. Garde TOUTES les infos réelles. Structure #/##. Français.",
        messages=[{"role":"user","content":
            f"CV:\n{cv}\n\nPoste: {job['title']} chez {job['company']}\nOffre:\n{job['description'][:3000]}\n\nAdapte le CV."}],
    ) as s:
        for t in s.text_stream: yield t

def stream_letter(cv, job, name, api_key, model):
    client = anthropic.Anthropic(api_key=api_key)
    with client.messages.stream(
        model=model, max_tokens=2048,
        system="Expert lettres de motivation. Accroche percutante, 3-4 paragraphes, appel à entretien. Français.",
        messages=[{"role":"user","content":
            f"Candidat: {name or '[Votre Nom]'}\nPoste: {job['title']} chez {job['company']}\nCV:\n{cv}\nOffre:\n{job['description'][:2000]}\n\nRédige la lettre."}],
    ) as s:
        for t in s.text_stream: yield t

# ══════════════════════════════════════════════════════════════════
# INTERFACE
# ══════════════════════════════════════════════════════════════════

st.set_page_config(page_title="AutoCandidature IA", page_icon="🔍",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.big-title{font-size:2rem;font-weight:800;color:#0f172a;margin-bottom:0}
.subtitle{font-size:.9rem;color:#64748b;margin-bottom:1rem}
.jcard{background:#fff;border:1.5px solid #e2e8f0;border-radius:12px;
       padding:.9rem 1.1rem;margin-bottom:.7rem;transition:border .15s}
.jtitle{font-size:1rem;font-weight:700;color:#1e293b;margin-bottom:2px}
.jmeta{font-size:.8rem;color:#64748b}
.badge{display:inline-block;border-radius:5px;padding:1px 8px;
       font-size:.7rem;font-weight:600;margin-right:3px;margin-bottom:2px}
.bblue{background:#dbeafe;color:#1d4ed8}
.bgreen{background:#dcfce7;color:#15803d}
.borange{background:#ffedd5;color:#c2410c}
.bpurple{background:#ede9fe;color:#7c3aed}
.bgray{background:#f1f5f9;color:#475569}
.bred{background:#fee2e2;color:#b91c1c}
.mli{margin:3px 0;padding-left:1rem;font-size:.85rem;color:#334155}
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="big-title">🔍 AutoCandidature IA</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Recherche sur HelloWork · France Travail · The Muse · Remotive · Arbeitnow — sans inscription · Résumé IA · Candidature personnalisée</p>', unsafe_allow_html=True)

# ── SIDEBAR ────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Claude IA")
    default_key = ""
    try:    default_key = st.secrets.get("ANTHROPIC_API_KEY","")
    except: pass
    if default_key:
        api_key = default_key; st.success("🔑 Clé Claude chargée")
    else:
        api_key = st.text_input("Clé API Anthropic", type="password", placeholder="sk-ant-...")

    model = st.selectbox("Modèle",
        ["claude-sonnet-4-6","claude-opus-4-6","claude-haiku-4-5-20251001"])

    st.divider()
    st.header("🔑 Clés optionnelles")
    st.caption("Ajoutez-les pour multiplier les résultats (toutes gratuites)")
    with st.expander("Jooble — 140 000 sites (recommandé)"):
        st.markdown("[→ Clé gratuite en 2 min](https://jooble.org/api/registered)")
        jooble_key = st.text_input("Clé Jooble", type="password", placeholder="xxxxxxxx-xxxx")
    with st.expander("Adzuna — Indeed FR, Cadremploi…"):
        st.markdown("[→ Clé gratuite](https://developer.adzuna.com/)")
        adzuna_id  = st.text_input("App ID",  placeholder="xxxxxxxx")
        adzuna_key_in = st.text_input("App Key", placeholder="xxxxxxxxxx", type="password")
    try: jooble_key
    except NameError: jooble_key=""
    try: adzuna_id; adzuna_key_in
    except NameError: adzuna_id=""; adzuna_key_in=""

    st.divider()
    st.header("👤 Mon profil")
    applicant_name = st.text_input("Nom complet", placeholder="Jean Dupont")
    cv_source = st.radio("Mon CV", ["📎 Uploader","✏️ Coller le texte"])
    cv_content = st.session_state.get("cv_content","")
    if "Uploader" in cv_source:
        up = st.file_uploader("PDF, DOCX ou TXT", type=["pdf","docx","txt"])
        if up:
            cv_content = load_cv_file(up)
            st.session_state["cv_content"] = cv_content
            st.success(f"✅ {len(cv_content)} caractères chargés")
    else:
        t = st.text_area("Texte du CV", value=cv_content, height=200,
                         placeholder="Expériences, compétences, formation…")
        if t: cv_content = t; st.session_state["cv_content"] = cv_content

# ── BARRE DE RECHERCHE ─────────────────────────────────────────────
st.markdown("### 🎯 Votre recherche")
c1,c2,c3,c4,c5 = st.columns([3,2,1.5,1,1.2])
with c1: keywords = st.text_input("Métier", placeholder="Développeur Python · Data Analyst · Chef de projet…", label_visibility="collapsed")
with c2: location = st.text_input("Ville",  placeholder="Orléans · Paris · Lyon · Remote…",                 label_visibility="collapsed")
with c3: country  = st.selectbox("Pays", ["France","Belgique","Suisse","Canada","USA","UK","Allemagne"],      label_visibility="collapsed")
with c4: radius   = st.selectbox("Rayon", [10,25,50,100,200], index=2,
                                  format_func=lambda x:f"{x} km",                                            label_visibility="collapsed")
with c5: search_btn = st.button("🔍 Rechercher", type="primary", use_container_width=True, disabled=not keywords)

opt1, opt2, opt3 = st.columns(3)
with opt1: include_remote = st.checkbox("Inclure le remote")
with opt2: expand_domain  = st.checkbox("Élargir au domaine (IA)", value=True,
                help="Claude génère 4 titres connexes et les recherche en parallèle")
with opt3: auto_sum       = st.checkbox("Résumé IA de l'offre", value=True)

# ── LANCEMENT ──────────────────────────────────────────────────────
if search_btn and keywords:
    extra_kws = []
    if expand_domain and api_key:
        with st.spinner("🧠 Claude analyse le domaine…"):
            extra_kws = expand_keywords(keywords, api_key, model)
        if extra_kws:
            st.info(f"🔎 Recherches : **{keywords}** + {' · '.join(extra_kws)}")

    prog = st.progress(0, text="Lancement des recherches parallèles…")
    jobs = run_searches(
        keywords, extra_kws, location, country, radius, include_remote,
        jooble_key, adzuna_id, adzuna_key_in,
    )
    prog.progress(100, text=f"✅ {len(jobs)} offres trouvées !")
    time.sleep(0.5); prog.empty()

    st.session_state.update({
        "jobs": jobs, "search_done": True,
        "selected_job": None, "generated_cv": "", "generated_letter": "",
    })

# ── AFFICHAGE ──────────────────────────────────────────────────────
BADGE_MAP = {
    "hellowork":    ("bblue",   "HelloWork"),
    "france travail":("bblue",  "France Travail"),
    "the muse":     ("bpurple", "The Muse"),
    "remotive":     ("bred",    "Remote"),
    "arbeitnow":    ("bgray",   "Arbeitnow"),
    "jooble":       ("bpurple", "Jooble"),
    "adzuna":       ("bgreen",  "Adzuna"),
}

def make_badge(src):
    k = src.lower()
    for key,(cls,lbl) in BADGE_MAP.items():
        if key in k: return f'<span class="badge {cls}">{lbl}</span>'
    return f'<span class="badge bgray">{src[:12]}</span>'

if st.session_state.get("search_done"):
    jobs: list[dict] = st.session_state.get("jobs",[])
    st.divider()

    if not jobs:
        st.warning(
            "Aucune offre trouvée pour cette localisation. "
            "Essayez une ville plus grande (ex: Paris, Lyon) ou élargissez le rayon. "
            "Les résultats peuvent aussi varier selon la disponibilité des sites."
        )
    else:
        # Stats sources
        srcs: dict = {}
        for j in jobs:
            s = j["source"].split("(")[0].strip()
            srcs[s] = srcs.get(s,0)+1
        st.markdown(f"**{len(jobs)} offres** — " + " · ".join(f"{k} ({v})" for k,v in srcs.items()))

        col_list, col_detail = st.columns([1,1.4], gap="large")

        with col_list:
            st.markdown("#### Offres")
            for i, job in enumerate(jobs[:60]):
                rem  = '<span class="badge bgreen">🌍 Remote</span>' if job.get("is_remote") else ""
                sal  = f'<div class="jmeta">💰 {job["salary"]}</div>' if job.get("salary") else ""
                ctr  = f'<span class="badge bgray">{job["contract"]}</span>' if job.get("contract") else ""
                post = f'<span class="jmeta"> · {job["posted"]}</span>' if job.get("posted") else ""
                st.markdown(f"""<div class="jcard">
{make_badge(job['source'])}{rem}{ctr}
<div class="jtitle">{job['title']}</div>
<div class="jmeta">🏢 {job['company']} &nbsp;·&nbsp; 📍 {job['location']}{post}</div>
{sal}</div>""", unsafe_allow_html=True)
                b1,b2 = st.columns(2)
                with b1:
                    if st.button("📄 Voir & Postuler", key=f"s{i}", use_container_width=True):
                        st.session_state.update({
                            "selected_job": job,
                            "generated_cv": "", "generated_letter": "",
                        })
                with b2:
                    if job.get("url"):
                        st.link_button("🔗 Offre", job["url"], use_container_width=True)

        with col_detail:
            sel = st.session_state.get("selected_job")
            if not sel:
                st.info("👈 Cliquez sur une offre pour voir le récapitulatif et générer votre candidature.")
            else:
                # ── Récapitulatif ─────────────────────────────────
                st.markdown(f"## {sel['title']}")
                m1,m2,m3 = st.columns(3)
                m1.markdown(f"🏢 **{sel['company']}**")
                m2.markdown(f"📍 {sel['location']}")
                if sel.get("salary"): m3.markdown(f"💰 {sel['salary']}")
                if sel.get("contract"): st.markdown(f"*{sel['contract']}*")
                if sel.get("posted"):   st.caption(f"Publiée le {sel['posted']}")
                if sel.get("url"):      st.link_button("🔗 Voir l'offre", sel["url"])
                st.divider()

                # ── Résumé IA ─────────────────────────────────────
                ai = sel.get("ai_summary")
                if auto_sum and not ai and api_key:
                    with st.spinner("🧠 Claude analyse l'offre…"):
                        sel = summarize_job(sel, api_key, model)
                        st.session_state["selected_job"] = sel
                        ai = sel.get("ai_summary")

                if ai:
                    st.markdown("#### 📋 Récapitulatif de l'offre")
                    if ai.get("missions"):
                        st.markdown("**🎯 Missions**")
                        for m in ai["missions"]:
                            st.markdown(f'<div class="mli">• {m}</div>', unsafe_allow_html=True)
                    if ai.get("competences"):
                        st.markdown("**🛠️ Compétences**")
                        st.markdown("".join(f'<span class="badge bblue">{c}</span>' for c in ai["competences"]), unsafe_allow_html=True)
                    if ai.get("profil"):
                        st.markdown(f"**👤 Profil** : {ai['profil']}")
                    if ai.get("avantages"):
                        st.markdown("**✨ Avantages**")
                        for a in ai["avantages"]:
                            st.markdown(f'<div class="mli">✓ {a}</div>', unsafe_allow_html=True)
                    if ai.get("ambiance"):
                        st.markdown(f"**🏠 Culture** : *{ai['ambiance']}*")
                else:
                    with st.expander("📃 Description", expanded=True):
                        desc = sel.get("description","")
                        st.markdown(desc[:4000] + ("…" if len(desc)>4000 else "") or "*Non disponible*")

                st.divider()

                # ── Candidature ───────────────────────────────────
                if not cv_content:
                    st.warning("⚠️ Chargez votre CV dans la barre latérale.")
                elif not api_key:
                    st.warning("⚠️ Entrez votre clé Anthropic dans la barre latérale.")
                else:
                    if st.button("🚀 Générer CV + Lettre de motivation",
                                 type="primary", use_container_width=True):
                        t1,t2 = st.tabs(["📋 CV Adapté","✉️ Lettre"])
                        with t1:
                            box,txt = st.empty(),""
                            try:
                                for c in stream_cv(cv_content, sel, api_key, model):
                                    txt+=c; box.markdown(txt)
                                st.session_state["generated_cv"]=txt
                            except Exception as e: st.error(f"Erreur: {e}")
                        with t2:
                            box2,txt2 = st.empty(),""
                            try:
                                for c in stream_letter(cv_content, sel, applicant_name, api_key, model):
                                    txt2+=c; box2.markdown(txt2)
                                st.session_state["generated_letter"]=txt2
                            except Exception as e: st.error(f"Erreur: {e}")

                gcv = st.session_state.get("generated_cv","")
                glm = st.session_state.get("generated_letter","")
                if gcv or glm:
                    st.markdown("**💾 Télécharger**")
                    d1,d2,d3,d4 = st.columns(4)
                    if gcv:
                        dx=export_docx(gcv)
                        if dx: d1.download_button("📥 CV .docx",dx,"cv.docx",
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True)
                        d2.download_button("📥 CV .txt",gcv.encode(),"cv.txt","text/plain",use_container_width=True)
                    if glm:
                        dl=export_docx(glm)
                        if dl: d3.download_button("📥 Lettre .docx",dl,"lettre.docx",
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True)
                        d4.download_button("📥 Lettre .txt",glm.encode(),"lettre.txt","text/plain",use_container_width=True)

st.divider()
st.caption("AutoCandidature IA · HelloWork · France Travail · The Muse · Remotive · Arbeitnow · Jooble · Adzuna · Propulsé par Claude (Anthropic)")
