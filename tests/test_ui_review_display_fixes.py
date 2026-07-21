"""Regression tests for operator UI review display fixes.

These tests render the affected templates directly so the bugs stay fixed:
- reel scripts stored as a single post must show the full script, not summary text
- asset review must show approved per-platform script from platform_content
- story_series assets must show every frame/image pair
- reel video step numbering starts at 1 when there is no image step
- list pages should not add manual ellipses/truncate titles at 80 chars
"""

import os
import sys
from types import SimpleNamespace

import pytest
from flask import Flask, render_template

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class AttrDict(dict):
    """dict with attribute access, matching sqlite rows parsed for templates."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


@pytest.fixture
def template_app():
    app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "..", "src", "templates"))

    @app.template_filter("relative_time")
    def relative_time(value):
        return "just now"

    return app


def test_draft_page_shows_single_post_reel_script(template_app):
    full_script = "HOOK: Caribbean savers are not wrong.\nBEAT 1: Saving is the instinct.\nBEAT 2: Hoarding is the trap."
    draft = AttrDict(
        id=1,
        draft_state="draft_ready",
        draft_version=1,
        format="Instagram Reel Script",
        draft_text="Summary only — should not be the visible script",
        platform_content_parsed=[{
            "platform": "Instagram",
            "variant_type": "reel",
            "content": "Summary only — should not be the visible script",
            "posts": [full_script],
            "image_prompts": ["none"],
        }],
        self_audit_flags_parsed=[],
        review_history_parsed=[],
        review_converged="true",
        visual_direction_parsed={},
    )
    card = AttrDict(id=8, idea="Saving culture vs money in motion")

    with template_app.test_request_context("/create/draft/8"):
        html = render_template(
            "draft.html",
            business_name="TestBiz",
            card=card,
            treatment={},
            hook_options=[],
            evidence_links=[],
            source_refs=[],
            capture_tasks=[],
            draft=draft,
            draft_visuals=[],
            scope_labels={},
            trail=[],
        )

    assert full_script in html
    assert "Summary only — should not be the visible script</div>" not in html
    assert "AI Format" not in html
    assert "Original idea card" in html


def test_assets_page_approved_script_uses_platform_content_not_draft_summary(template_app):
    full_script = "FULL REEL SCRIPT\nBeat 1\nBeat 2\nBeat 3"
    draft = AttrDict(
        id=1,
        draft_state="shipped",
        format="Instagram Reel Script",
        draft_text="Summary only — wrong approved script",
        platform_content_parsed=[{
            "platform": "Instagram",
            "variant_type": "reel",
            "content": "Summary only — wrong approved script",
            "posts": [full_script],
        }],
    )
    asset = AttrDict(
        id=1,
        platform="Instagram",
        variant_type="reel",
        asset_state="pending",
        content="Asset summary",
        posts_parsed=[full_script],
        image_prompts_parsed=["none"],
        post_images=[],
        images=[],
        generated_images_parsed=[],
        videos=[],
        final_cuts=[],
        edit_plans=[],
    )

    with template_app.test_request_context("/create/assets/1"):
        html = render_template(
            "assets.html",
            business_name="TestBiz",
            idea_card=AttrDict(idea="Original idea"),
            draft=draft,
            assets=[asset],
            platforms=[],
            trail=[],
        )

    assert full_script in html
    assert "Summary only — wrong approved script</div>" not in html


def test_assets_page_story_series_shows_all_frames_and_images(template_app):
    posts = [f"Story frame {i}" for i in range(1, 6)]
    images = [AttrDict(path=f"data/media/2/image_{i}.png") for i in range(1, 6)]
    asset = AttrDict(
        id=2,
        platform="Instagram",
        variant_type="story_series",
        asset_state="pending",
        content="Summary only",
        posts_parsed=posts,
        image_prompts_parsed=[f"prompt {i}" for i in range(1, 6)],
        post_images=images,
        images=images,
        generated_images_parsed=[],
        videos=[],
        final_cuts=[],
        edit_plans=[],
    )
    draft = AttrDict(
        id=2,
        draft_state="shipped",
        format="Instagram Story Series",
        draft_text="Summary only",
        platform_content_parsed=[{
            "platform": "Instagram",
            "variant_type": "story_series",
            "content": "Summary only",
            "posts": posts,
        }],
    )

    with template_app.test_request_context("/create/assets/2"):
        html = render_template(
            "assets.html",
            business_name="TestBiz",
            idea_card=AttrDict(idea="Original idea"),
            draft=draft,
            assets=[asset],
            platforms=[],
            trail=[],
        )

    for i in range(1, 6):
        assert f"Story frame {i}" in html
        assert f"image_{i}.png" in html
    assert "1/5" in html
    assert "5/5" in html


def test_reel_video_generation_step_is_numbered_one(template_app):
    asset = AttrDict(
        id=1,
        platform="Instagram",
        variant_type="reel",
        asset_state="pending",
        content="Reel summary",
        posts_parsed=["Full reel script"],
        image_prompts_parsed=["none"],
        post_images=[],
        images=[],
        generated_images_parsed=[],
        videos=[],
        final_cuts=[],
        edit_plans=[],
    )
    draft = AttrDict(id=1, draft_state="shipped", format="Instagram Reel Script", draft_text="summary", platform_content_parsed=[])

    with template_app.test_request_context("/create/assets/1"):
        html = render_template(
            "assets.html",
            business_name="TestBiz",
            idea_card=AttrDict(idea="Original idea"),
            draft=draft,
            assets=[asset],
            platforms=[],
            trail=[],
        )

    assert '<span class="step-num active">1</span>' in html
    assert '<span class="step-num active">2</span>' not in html


def test_reel_approved_soundtrack_label_matches_render_action(template_app):
    asset = AttrDict(
        id=7,
        platform="Instagram",
        variant_type="reel",
        asset_state="pending",
        content="Reel summary",
        posts_parsed=["Full reel script"],
        image_prompts_parsed=["none"],
        post_images=[],
        images=[],
        generated_images_parsed=[],
        videos=[],
        final_cuts=[],
        edit_plans=[AttrDict(id=71)],
        soundtrack_review=AttrDict(
            mode="vo_only",
            emotional_register="direct",
            rationale="The approved voice stands alone.",
            preview=AttrDict(instructions="Listen first.", tracks=[]),
            approval=AttrDict(approved=True),
            preview_acknowledged=True,
            alternatives=[],
        ),
    )
    draft = AttrDict(
        id=11,
        draft_state="shipped",
        format="Instagram Reel Script",
        draft_text="summary",
        platform_content_parsed=[],
    )

    with template_app.test_request_context("/create/assets/11"):
        html = render_template(
            "assets.html",
            business_name="TestBiz",
            idea_card=AttrDict(idea="Original idea"),
            draft=draft,
            assets=[asset],
            platforms=[],
            trail=[],
        )

    assert "Approved plan ready to render" in html
    assert 'onclick="renderFinalCut(7, 71, this)"' in html
    assert ">Render final cut</button>" in html


def test_reel_without_final_cut_does_not_show_active_approve(template_app):
    """A reel cannot be approved until a final cut exists for human review."""
    asset = AttrDict(
        id=1,
        platform="Instagram",
        variant_type="reel",
        asset_state="pending",
        content="Reel summary",
        posts_parsed=["Full reel script"],
        image_prompts_parsed=["none"],
        post_images=[],
        images=[],
        generated_images_parsed=[],
        videos=[],
        final_cuts=[],
        edit_plans=[],
    )
    draft = AttrDict(id=1, draft_state="shipped", format="Instagram Reel Script", draft_text="summary", platform_content_parsed=[])

    with template_app.test_request_context("/create/assets/1"):
        html = render_template(
            "assets.html",
            business_name="TestBiz",
            idea_card=AttrDict(idea="Original idea"),
            draft=draft,
            assets=[asset],
            platforms=[],
            trail=[],
        )

    assert 'assetGate(1, \'approve\'' not in html
    assert "Approve locked until final cut exists" in html


def test_list_pages_do_not_manually_ellipsis_long_titles(template_app):
    long_idea = "This is a long idea title that needs at least two lines so the operator can understand what the card is about without clicking first."
    base_card = SimpleNamespace(
        id=1,
        idea=long_idea,
        idea_short=long_idea[:80],
        display_state="ready_review",
        trail=[],
        state_changed_at=None,
        production_error=None,
    )
    assembler_card = SimpleNamespace(
        **base_card.__dict__,
        draft={"id": 1},
        asset_count=1,
        approved_assets=[],
        pending_assets=[1],
    )

    with template_app.test_request_context("/create"):
        create_html = render_template(
            "create.html",
            business_name="TestBiz",
            unified_cards=[base_card],
            state_counts={"ready_review": 1},
        )
    with template_app.test_request_context("/assemble"):
        assemble_html = render_template(
            "assemble.html",
            business_name="TestBiz",
            assembler_cards=[assembler_card],
            state_counts={"pending": 1},
        )

    assert "...</a>" not in create_html
    assert "...</a>" not in assemble_html


def test_list_pages_use_multi_line_card_titles():
    create_template = os.path.join(os.path.dirname(__file__), "..", "src", "templates", "create.html")
    assemble_template = os.path.join(os.path.dirname(__file__), "..", "src", "templates", "assemble.html")
    for path in (create_template, assemble_template):
        with open(path) as f:
            content = f.read()
        assert "-webkit-line-clamp: 3" in content
        assert "overflow: hidden" in content


def test_ai_review_loop_shows_noted_flags_without_replacement_arrow(template_app):
    draft = AttrDict(
        id=1,
        draft_state="draft_ready",
        draft_version=1,
        format="Instagram Reel Script",
        draft_text="Summary",
        platform_content_parsed=[],
        self_audit_flags_parsed=[],
        review_converged="true",
        visual_direction_parsed={},
        review_history_parsed=[{
            "round": 1,
            "alignment_check": {"aligned": True, "issues": [], "recommendations": []},
            "self_audit_fixes": [{
                "line": "That line is already natural.",
                "rule": "voice",
                "suggestion": "This feels natural. Keep it.",
                "fix": "This feels natural. Keep it.",
            }],
        }],
    )
    with template_app.test_request_context("/create/draft/1"):
        html = render_template(
            "draft.html",
            business_name="TestBiz",
            card=AttrDict(id=1, idea="Idea"),
            treatment={},
            hook_options=[],
            draft=draft,
            draft_visuals=[],
            scope_labels={},
            trail=[],
        )

    assert "Self-audit notes" in html
    assert "Noted — no text change" in html
    assert "That line is already natural.&#39; →" not in html


def test_assets_page_documents_needs_work_to_fix_mapping(template_app):
    asset = AttrDict(
        id=1,
        platform="Instagram",
        variant_type="reel",
        asset_state="pending",
        content="Reel summary",
        posts_parsed=["Full reel script"],
        image_prompts_parsed=["none"],
        post_images=[],
        images=[],
        generated_images_parsed=[],
        videos=[],
        final_cuts=[],
        edit_plans=[],
    )
    draft = AttrDict(id=1, draft_state="shipped", format="Instagram Reel Script", draft_text="summary", platform_content_parsed=[])

    with template_app.test_request_context("/create/assets/1"):
        html = render_template(
            "assets.html",
            business_name="TestBiz",
            idea_card=AttrDict(idea="Original idea"),
            draft=draft,
            assets=[asset],
            platforms=[],
            trail=[],
        )

    assert "Needs work" in html
    assert "internal state: fix" in html


def test_reel_asset_card_shows_script_excerpt_not_duplicate_summary(template_app):
    full_script = "FULL SCRIPT: hook, beat one, beat two, closing line."
    summary = "Instagram Reel Script — duplicated summary should not be the asset-card body"
    asset = AttrDict(
        id=1,
        platform="Instagram",
        variant_type="reel",
        asset_state="pending",
        content=summary,
        posts_parsed=[full_script],
        image_prompts_parsed=["none"],
        post_images=[],
        images=[],
        generated_images_parsed=[],
        videos=[],
        final_cuts=[],
        edit_plans=[],
    )
    draft = AttrDict(
        id=1,
        draft_state="shipped",
        format="Instagram Reel Script",
        draft_text=summary,
        platform_content_parsed=[{"platform": "Instagram", "variant_type": "reel", "posts": [full_script]}],
    )

    with template_app.test_request_context("/create/assets/1"):
        html = render_template(
            "assets.html",
            business_name="TestBiz",
            idea_card=AttrDict(idea="Original idea"),
            draft=draft,
            assets=[asset],
            platforms=[],
            trail=[],
        )

    assert "Script excerpt" in html
    assert full_script in html
    assert summary + "</div>" not in html


def test_researcher_generate_button_has_loading_state():
    template = os.path.join(os.path.dirname(__file__), "..", "src", "templates", "ideas.html")
    with open(template) as f:
        content = f.read()
    assert "id=\"genStatus\"" in content
    assert "busyLabel: 'Generating…'" in content
    assert "status.textContent = 'Generating…'" in content


def test_newsletter_format_with_image_prompts_not_text_only(template_app):
    """Regression: a 'Newsletter Section' format asset on Instagram with 8
    image prompts was misclassified as text-only (because variant_type
    contained 'newsletter'), hiding the carousel slides and the 'Generate
    images' button. The template must auto-detect the carousel structure and
    show the Generate button when active image prompts exist."""
    posts = [f"Slide {i} text" for i in range(1, 9)]
    image_prompts = [f"Slide {i} prompt" for i in range(1, 9)]
    asset = AttrDict(
        id=5,
        platform="Instagram",
        variant_type="newsletter_section",  # format name, not structural type
        asset_state="pending",
        content="Carousel breaking down the ownership gap",
        posts_parsed=posts,
        image_prompts_parsed=image_prompts,
        post_images=[],
        images=[],
        generated_images_parsed=[],
        videos=[],
        final_cuts=[],
        edit_plans=[],
    )
    draft = AttrDict(
        id=1,
        draft_state="shipped",
        format="Newsletter Section",
        draft_text="Summary",
        platform_content_parsed=[],
    )

    with template_app.test_request_context("/create/assets/1"):
        html = render_template(
            "assets.html",
            business_name="TestBiz",
            idea_card=AttrDict(idea="Original idea"),
            draft=draft,
            assets=[asset],
            platforms=[],
            trail=[],
        )

    # Must NOT show "Text-only format" — it has image prompts
    assert "Text-only format" not in html
    # Must show the Generate button
    assert "Generate 8 images" in html
    # Must show carousel slides (numbered 1/8 through 8/8)
    assert "1/8" in html
    assert "8/8" in html


def test_newsletter_format_on_x_with_no_image_prompts_is_thread(template_app):
    """Regression: a 'Newsletter Section' format asset on X with 8 tweets
    and all-'none' image prompts was misclassified as text-only newsletter.
    It should render as a thread (numbered tweets), not a newsletter mock."""
    posts = [f"Tweet {i} text" for i in range(1, 9)]
    asset = AttrDict(
        id=6,
        platform="X",
        variant_type="newsletter_section",  # format name, not structural type
        asset_state="pending",
        content="Thread breaking down the ownership gap",
        posts_parsed=posts,
        image_prompts_parsed=["none"] * 8,
        post_images=[],
        images=[],
        generated_images_parsed=[],
        videos=[],
        final_cuts=[],
        edit_plans=[],
    )
    draft = AttrDict(
        id=1,
        draft_state="shipped",
        format="Newsletter Section",
        draft_text="Summary",
        platform_content_parsed=[],
    )

    with template_app.test_request_context("/create/assets/1"):
        html = render_template(
            "assets.html",
            business_name="TestBiz",
            idea_card=AttrDict(idea="Original idea"),
            draft=draft,
            assets=[asset],
            platforms=[],
            trail=[],
        )

    # Must show thread numbers (1 through 8) not newsletter mock
    # Thread posts are numbered with just the number (1, 2, 3...)
    assert ">1<" in html  # tweet 1
    assert ">8<" in html  # tweet 8
    # Must NOT render the newsletter mock content structure
    # (the CSS class exists in <style>, but the mock div must not be rendered)
    assert 'class="newsletter-mock"' not in html
    # Must NOT show "Text-only format" — X thread with 8 posts is not text-only
    assert "Text-only format" not in html


def test_reel_without_visuals_shows_generate_step_and_disables_plan(template_app):
    """A reel with active image prompts but no generated visuals must offer
    a 'Generate visuals' step and disable 'Plan final cut' until visuals exist.

    Reproduces the /create/assets/21 blocker: the operator's only button was
    'Plan final cut', which 409'd with 'No usable visual media is available'
    because the reel branch had no generate-visuals step (unlike the
    non-reel branch).
    """
    asset = AttrDict(
        id=17,
        platform="Instagram",
        variant_type="reel",
        asset_state="pending",
        content="Reel about Caribbean money scripts",
        posts_parsed=[{"label": "HOOK", "vo_text": "spoke line"}],
        image_prompts_parsed=[
            "Caribbean entrepreneur, warm-lit office, 9:16 vertical",
            "Stylized bank statement, motion graphic, 9:16 vertical",
        ],
        post_images=[],
        images=[],
        generated_images_parsed=[],
        videos=[],
        final_cuts=[],
        edit_plans=[],
        has_vo=True,
        vo_segments_parsed=[{"frame": 1, "beat_id": "b01", "duration": 5.0}],
    )
    draft = AttrDict(
        id=21,
        draft_state="shipped",
        format="Instagram Reel Script",
        draft_text="summary",
        platform_content_parsed=[],
    )

    with template_app.test_request_context("/create/assets/21"):
        html = render_template(
            "assets.html",
            business_name="TestBiz",
            idea_card=AttrDict(idea="Original idea"),
            draft=draft,
            assets=[asset],
            platforms=[],
            trail=[],
        )

    # Generate-visuals step is present with the correct count
    assert "Generate visuals" in html
    assert "generateVisuals(17, this)" in html
    assert "Generate 2 images" in html
    # Plan-final-cut button is disabled with a helpful title
    assert "Plan final cut (needs visuals)" in html
    assert "disabled" in html
    # The active edit-plan call must NOT be wired when visuals are missing
    assert "generateEditPlan(17, this)" not in html
    # VO step should NOT appear — VO already exists
    assert "Generate voice-over" not in html


def test_reel_with_visuals_enables_plan_final_cut(template_app):
    """Once a reel has generated images, the generate step disappears and
    'Plan final cut' is active (wired to generateEditPlan)."""
    asset = AttrDict(
        id=17,
        platform="Instagram",
        variant_type="reel",
        asset_state="pending",
        content="Reel about Caribbean money scripts",
        posts_parsed=[{"label": "HOOK", "vo_text": "spoke line"}],
        image_prompts_parsed=[
            "Caribbean entrepreneur, warm-lit office, 9:16 vertical",
            "Stylized bank statement, motion graphic, 9:16 vertical",
        ],
        post_images=[],
        images=[],
        generated_images_parsed=["img1.png", "img2.png"],
        videos=[],
        final_cuts=[],
        edit_plans=[],
        has_vo=True,
        vo_segments_parsed=[{"frame": 1, "beat_id": "b01", "duration": 5.0}],
    )
    draft = AttrDict(
        id=21,
        draft_state="shipped",
        format="Instagram Reel Script",
        draft_text="summary",
        platform_content_parsed=[],
    )

    with template_app.test_request_context("/create/assets/21"):
        html = render_template(
            "assets.html",
            business_name="TestBiz",
            idea_card=AttrDict(idea="Original idea"),
            draft=draft,
            assets=[asset],
            platforms=[],
            trail=[],
        )

    # No generate-visuals step when visuals already exist
    assert "Generate visuals" not in html
    # Plan final cut is wired (not disabled)
    assert "generateEditPlan(17, this)" in html
    assert "Plan final cut (needs visuals)" not in html


def test_reel_without_vo_shows_generate_vo_step_and_disables_plan(template_app):
    """A reel with spoken beats but no VO segments must offer a 'Generate
    voice-over' step and disable 'Plan final cut' until VO exists.

    Reproduces the second /create/assets/21 blocker: after generating visuals,
    'Plan final cut' 409'd with 'Reel has 6 spoken beats but only 0 VO
    segment(s)' because the operator UI had no VO generation path.
    """
    asset = AttrDict(
        id=17,
        platform="Instagram",
        variant_type="reel",
        asset_state="pending",
        content="Reel about Caribbean money scripts",
        posts_parsed=[
            {"label": "HOOK", "vo_text": "Caribbean culture teaches us…"},
            {"label": "SETUP", "vo_text": "Look at your bank statement…"},
        ],
        image_prompts_parsed=["prompt1", "prompt2"],
        post_images=[],
        images=[],
        generated_images_parsed=["img1.png", "img2.png"],
        videos=[],
        final_cuts=[],
        edit_plans=[],
        has_vo=False,
        vo_segments_parsed=[],
    )
    draft = AttrDict(
        id=21,
        draft_state="shipped",
        format="Instagram Reel Script",
        draft_text="summary",
        platform_content_parsed=[],
    )

    with template_app.test_request_context("/create/assets/21"):
        html = render_template(
            "assets.html",
            business_name="TestBiz",
            idea_card=AttrDict(idea="Original idea"),
            draft=draft,
            assets=[asset],
            platforms=[],
            trail=[],
        )

    # Generate-VO step is present with beat count
    assert "Generate voice-over" in html
    assert "generateVO(17, this)" in html
    assert "2 spoken beats" in html
    # Plan-final-cut is disabled with VO message
    assert "Plan final cut (needs VO)" in html
    # The active edit-plan call must NOT be wired when VO is missing
    assert "generateEditPlan(17, this)" not in html
    # Visuals step should NOT appear — visuals already exist
    assert "Generate visuals" not in html


def test_reel_with_vo_and_visuals_enables_plan_final_cut(template_app):
    """A reel with both VO and visuals has no generate steps and Plan final
    cut is fully active."""
    asset = AttrDict(
        id=17,
        platform="Instagram",
        variant_type="reel",
        asset_state="pending",
        content="Reel about Caribbean money scripts",
        posts_parsed=[{"label": "HOOK", "vo_text": "spoke line"}],
        image_prompts_parsed=["prompt1"],
        post_images=[],
        images=[],
        generated_images_parsed=["img1.png"],
        videos=[],
        final_cuts=[],
        edit_plans=[],
        has_vo=True,
        vo_segments_parsed=[{"frame": 1, "beat_id": "b01", "duration": 5.0}],
    )
    draft = AttrDict(
        id=21,
        draft_state="shipped",
        format="Instagram Reel Script",
        draft_text="summary",
        platform_content_parsed=[],
    )

    with template_app.test_request_context("/create/assets/21"):
        html = render_template(
            "assets.html",
            business_name="TestBiz",
            idea_card=AttrDict(idea="Original idea"),
            draft=draft,
            assets=[asset],
            platforms=[],
            trail=[],
        )

    assert "Generate voice-over" not in html
    assert "Generate visuals" not in html
    assert "generateEditPlan(17, this)" in html
    assert "needs VO" not in html
    assert "needs visuals" not in html
