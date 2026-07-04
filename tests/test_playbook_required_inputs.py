"""Tests for playbook required_inputs frontmatter parsing."""


def test_playbook_parser_reads_required_inputs():
    from playbook_runner import PlaybookParser
    pb = PlaybookParser.parse("playbooks/story-frameworks-starter.md")
    assert "admired_examples" in pb.required_inputs
    assert "operator_stories" in pb.required_inputs
    assert "voice_summary" in pb.required_inputs


def test_playbook_parser_required_inputs_all_playbooks():
    from playbook_runner import PlaybookParser
    import os
    pb_dir = "playbooks"
    for fname in sorted(os.listdir(pb_dir)):
        if not fname.endswith(".md"):
            continue
        pb = PlaybookParser.parse(os.path.join(pb_dir, fname))
        assert isinstance(pb.required_inputs, list)


def test_playbook_required_inputs_viral_patterns():
    from playbook_runner import PlaybookParser
    pb = PlaybookParser.parse("playbooks/viral-patterns-starter.md")
    assert "admired_links" in pb.required_inputs
    assert "anti_examples" in pb.required_inputs
    assert "top_performers" in pb.required_inputs


def test_playbook_required_inputs_business_profile():
    from playbook_runner import PlaybookParser
    pb = PlaybookParser.parse("playbooks/business-profile-intake.md")
    assert "business_qa" in pb.required_inputs