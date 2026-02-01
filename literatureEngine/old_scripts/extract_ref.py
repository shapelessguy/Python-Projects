import re


def escape_latex(s):
    """Escape LaTeX special characters"""
    if not s:
        return s
    replacements = {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\^{}",
        "\\": r"\textbackslash{}"
    }
    for k, v in replacements.items():
        s = s.replace(k, v)
    return s


def extract_year(m):
    for key in [
        "published-print",
        "published-online",
        "issued",
        "created"
    ]:
        if key in m:
            candidate = m[key]["date-parts"][0][0]
            if candidate:
                return candidate
    return None


def extract_venue(m):
    t = m.get("type")

    if t in ("journal-article", "proceedings-article"):
        return ", ".join(m.get("container-title", []))

    if t == "book-chapter":
        return ", ".join(m.get("container-title", []))  # book title

    if t in ("book", "edited-book", "monograph"):
        return m.get("title", [""])[0]

    if t in ("report", "dissertation"):
        return m.get("publisher") or m.get("institution", {}).get("name")

    if t == "posted-content":
        return m.get("group-title") or "Preprint"

    return None


def extract_authors(m):
    if m.get("author"):
        try:
            opt = [f"{a['family']}, {a.get('given', '')}" for a in m["author"]]
        except:
            opt = [f"{a.get('name')}" for a in m["author"]]
        return opt
    if m.get("editor"):
        return [f"{e.get('family')}, {e.get('given', '')} (ed.)" for e in m["editor"]]
    return []


def clean_title(title):
    title = re.sub(r'<scp>(.*?)</scp>', lambda m: m.group(1), title)
    title = re.sub(r'\s+', ' ', title)
    return title.strip()


def extract_reference(doi_md: dict[str, any]):
    return {
        "authors": extract_authors(doi_md),
        "title": clean_title(doi_md.get("title", [""])[0]),
        "year": extract_year(doi_md),
        "venue": extract_venue(doi_md),
        "publisher": doi_md.get("publisher"),
        "volume": doi_md.get("volume"),
        "issue": doi_md.get("issue"),
        "pages": doi_md.get("page"),
        "doi": doi_md.get("DOI"),
        "url": doi_md.get("URL"),
        "type": doi_md.get("type")
    }


def extract_reference_latex(doi_md):
    ref = extract_reference(doi_md)

    # Clean up authors: join for BibTeX & strip weird chars
    authors = ref.get("authors", [])
    authors = [a.strip() for a in authors if a]
    ref["authors"] = " and ".join(authors) if authors else "Unknown"

    # Escape LaTeX special characters in title and venue
    for key in ["title", "venue", "publisher"]:
        if ref.get(key):
            ref[key] = escape_latex(ref[key])

    # Map 'issue' → BibTeX 'number'
    if "issue" in ref:
        ref["number"] = ref.pop("issue")

    # Remove None values
    ref = {k: v for k, v in ref.items() if v not in [None, ""]}

    return ref


if __name__ == "__main__":
    pass