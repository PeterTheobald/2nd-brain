import logging

import frontmatter

from config import VAULT_PATH

logger = logging.getLogger(__name__)


def build_contact_index() -> dict[str, str]:
    """Scan ppl/ and return a dict of {name_or_alias: filename} for all contacts."""
    index: dict[str, str] = {}
    ppl_dir = VAULT_PATH / "ppl"
    if not ppl_dir.exists():
        return index

    for path in sorted(ppl_dir.glob("*.md")):
        try:
            post = frontmatter.load(str(path))
        except Exception:
            # A malformed contact file must not drop the whole index silently.
            logger.warning("Skipping unparseable contact file: %s", path, exc_info=True)
            continue

        filename = path.name
        index[str(post.metadata.get("Name") or path.stem)] = filename

        # `aliases:` with no value parses to None, not []; guard against it.
        for alias in post.metadata.get("aliases") or []:
            index[str(alias)] = filename

    return index
