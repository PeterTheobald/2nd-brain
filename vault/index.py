import frontmatter
from config import VAULT_PATH


def build_contact_index() -> dict[str, str]:
    """Scan ppl/ and return a dict of {name_or_alias: filename} for all contacts."""
    index = {}
    ppl_dir = VAULT_PATH / "ppl"
    if not ppl_dir.exists():
        return index

    for path in ppl_dir.glob("*.md"):
        try:
            post = frontmatter.load(str(path))
        except Exception:
            continue

        canonical = post.metadata.get("Name") or path.stem
        filename = path.name
        index[canonical] = filename

        for alias in post.metadata.get("aliases", []):
            index[str(alias)] = filename

    return index
