import vault.index as index_module


def test_indexes_canonical_name(vault_dir, monkeypatch):
    monkeypatch.setattr(index_module, "VAULT_PATH", vault_dir)
    (vault_dir / "ppl" / "John Smith.md").write_text(
        "---\nName: John Smith\naliases: []\n---\n\nJOURNAL:\n"
    )
    idx = index_module.build_contact_index()
    assert idx["John Smith"] == "John Smith.md"


def test_indexes_aliases(vault_dir, monkeypatch):
    monkeypatch.setattr(index_module, "VAULT_PATH", vault_dir)
    (vault_dir / "ppl" / "John Smith.md").write_text(
        "---\nName: John Smith\naliases: [john, johnny]\n---\n"
    )
    idx = index_module.build_contact_index()
    assert idx["John Smith"] == "John Smith.md"
    assert idx["john"] == "John Smith.md"
    assert idx["johnny"] == "John Smith.md"


def test_handles_missing_aliases_field(vault_dir, monkeypatch):
    monkeypatch.setattr(index_module, "VAULT_PATH", vault_dir)
    (vault_dir / "ppl" / "Jane Doe.md").write_text(
        "---\nName: Jane Doe\n---\n"
    )
    idx = index_module.build_contact_index()
    assert idx["Jane Doe"] == "Jane Doe.md"


def test_handles_empty_aliases_value(vault_dir, monkeypatch):
    # "aliases:" with no value parses to None — must not drop the contact.
    monkeypatch.setattr(index_module, "VAULT_PATH", vault_dir)
    (vault_dir / "ppl" / "Jane Doe.md").write_text(
        "---\nName: Jane Doe\naliases:\n---\n"
    )
    idx = index_module.build_contact_index()
    assert idx["Jane Doe"] == "Jane Doe.md"


def test_falls_back_to_stem_when_no_name(vault_dir, monkeypatch):
    monkeypatch.setattr(index_module, "VAULT_PATH", vault_dir)
    (vault_dir / "ppl" / "Jane Doe.md").write_text("---\n---\n")
    idx = index_module.build_contact_index()
    assert idx["Jane Doe"] == "Jane Doe.md"


def test_handles_malformed_frontmatter_without_crash(vault_dir, monkeypatch):
    monkeypatch.setattr(index_module, "VAULT_PATH", vault_dir)
    (vault_dir / "ppl" / "Bad.md").write_text("not: valid: yaml: {{{")
    # should not raise
    index_module.build_contact_index()


def test_multiple_contacts(vault_dir, monkeypatch):
    monkeypatch.setattr(index_module, "VAULT_PATH", vault_dir)
    (vault_dir / "ppl" / "Alice Brown.md").write_text(
        "---\nName: Alice Brown\naliases: [alice]\n---\n"
    )
    (vault_dir / "ppl" / "Bob White.md").write_text(
        "---\nName: Bob White\naliases: [bob]\n---\n"
    )
    idx = index_module.build_contact_index()
    assert idx["Alice Brown"] == "Alice Brown.md"
    assert idx["alice"] == "Alice Brown.md"
    assert idx["Bob White"] == "Bob White.md"
    assert idx["bob"] == "Bob White.md"


def test_empty_ppl_dir(vault_dir, monkeypatch):
    monkeypatch.setattr(index_module, "VAULT_PATH", vault_dir)
    assert index_module.build_contact_index() == {}


def test_missing_ppl_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(index_module, "VAULT_PATH", tmp_path)
    assert index_module.build_contact_index() == {}
