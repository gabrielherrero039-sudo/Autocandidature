"""
job_adapter.py — Adaptation IA du CV et génération de lettre de motivation
via l'API Anthropic (Claude)
"""

import anthropic


def adapt_cv(
    cv_content: str,
    job_posting: str,
    sector: str,
    api_key: str,
    model: str = "claude-sonnet-4-6",
) -> str:
    """
    Adapte le CV de l'utilisateur en fonction de l'offre d'emploi.
    Retourne le CV adapté sous forme de texte formaté (Markdown-like).
    """
    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = """Tu es un expert en recrutement et en rédaction de CV professionnels.
Tu aides les candidats à adapter leur CV pour maximiser leurs chances d'obtenir un entretien.
Tu dois :
- Conserver toutes les informations factuelles (expériences, diplômes, compétences réelles)
- Réorganiser et reformuler pour mettre en valeur ce qui est le plus pertinent pour le poste
- Utiliser les mots-clés de l'offre d'emploi
- Adopter un ton professionnel et concis
- Structurer clairement avec des sections bien définies
- Répondre en français
- Utiliser des marqueurs simples : # pour le nom/titre, ## pour les sections, ** pour les éléments importants"""

    user_prompt = f"""Voici mon CV actuel :

{cv_content}

---

Voici l'offre d'emploi à laquelle je postule (secteur : {sector}) :

{job_posting}

---

Adapte mon CV pour cette offre spécifique.
- Garde toutes mes informations réelles (ne rien inventer)
- Réorganise et reformule pour coller au maximum aux exigences du poste
- Mets en avant les compétences et expériences les plus pertinentes
- Utilise les termes et mots-clés de l'offre
- Structure avec des sections claires : Profil, Expériences, Compétences, Formation, etc.

Retourne uniquement le CV adapté, sans commentaires."""

    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return message.content[0].text


def adapt_cv_stream(
    cv_content: str,
    job_posting: str,
    sector: str,
    api_key: str,
    model: str = "claude-sonnet-4-6",
):
    """
    Version streaming — retourne un générateur de chunks de texte.
    À utiliser avec st.write_stream() de Streamlit.
    """
    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = """Tu es un expert en recrutement et en rédaction de CV professionnels.
Tu aides les candidats à adapter leur CV pour maximiser leurs chances d'obtenir un entretien.
Tu dois :
- Conserver toutes les informations factuelles (expériences, diplômes, compétences réelles)
- Réorganiser et reformuler pour mettre en valeur ce qui est le plus pertinent pour le poste
- Utiliser les mots-clés de l'offre d'emploi
- Adopter un ton professionnel et concis
- Structurer clairement avec des sections bien définies
- Répondre en français
- Utiliser des marqueurs simples : # pour le nom/titre, ## pour les sections, ** pour les éléments importants"""

    user_prompt = f"""Voici mon CV actuel :

{cv_content}

---

Voici l'offre d'emploi à laquelle je postule (secteur : {sector}) :

{job_posting}

---

Adapte mon CV pour cette offre spécifique.
- Garde toutes mes informations réelles (ne rien inventer)
- Réorganise et reformule pour coller au maximum aux exigences du poste
- Mets en avant les compétences et expériences les plus pertinentes
- Utilise les termes et mots-clés de l'offre
- Structure avec des sections claires : Profil, Expériences, Compétences, Formation, etc.

Retourne uniquement le CV adapté, sans commentaires."""

    with client.messages.stream(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text


def generate_cover_letter_stream(
    cv_content: str,
    job_posting: str,
    sector: str,
    company_name: str,
    applicant_name: str,
    api_key: str,
    model: str = "claude-sonnet-4-6",
):
    """
    Génère une lettre de motivation personnalisée en streaming.
    """
    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = """Tu es un expert en recrutement et en rédaction de lettres de motivation.
Tu rédiges des lettres percutantes, personnalisées et professionnelles en français.
La lettre doit :
- Être structurée classiquement (introduction accrochante, développement, conclusion avec appel à l'action)
- Montrer une vraie connaissance du poste et de l'entreprise
- Mettre en lien les compétences du candidat avec les besoins du poste
- Avoir un ton chaleureux mais professionnel
- Faire environ 3-4 paragraphes (300-400 mots)
- Ne pas répéter mot pour mot le CV mais le compléter"""

    company_info = f" chez {company_name}" if company_name else ""
    name_info = f"Le candidat s'appelle {applicant_name}." if applicant_name else "Le nom du candidat n'est pas précisé (utilise [Votre Prénom Nom])."

    user_prompt = f"""Voici le CV du candidat :

{cv_content}

---

Voici l'offre d'emploi{company_info} (secteur : {sector}) :

{job_posting}

---

{name_info}

Rédige une lettre de motivation personnalisée et percutante pour ce poste.
- Accroche originale liée au poste ou à l'entreprise
- Montre pourquoi ce poste est fait pour ce candidat
- Cite 2-3 réalisations/compétences clés du CV en lien direct avec l'offre
- Conclusion avec appel à l'entretien
- Format lettre formelle avec date, objet, formule de politesse"""

    with client.messages.stream(
        model=model,
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text


def generate_cover_letter(
    cv_content: str,
    job_posting: str,
    sector: str,
    company_name: str,
    applicant_name: str,
    api_key: str,
    model: str = "claude-sonnet-4-6",
) -> str:
    """Version non-streaming de la génération de lettre de motivation."""
    client = anthropic.Anthropic(api_key=api_key)

    company_info = f" chez {company_name}" if company_name else ""
    name_info = f"Le candidat s'appelle {applicant_name}." if applicant_name else "Le nom du candidat n'est pas précisé (utilise [Votre Prénom Nom])."

    message = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": f"""CV :\n{cv_content}\n\nOffre{company_info} ({sector}) :\n{job_posting}\n\n{name_info}\n\nRédige une lettre de motivation professionnelle et personnalisée.""",
            }
        ],
    )
    return message.content[0].text
