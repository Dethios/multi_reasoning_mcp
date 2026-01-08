from multi_reasoning_mcp.patcher import summarize_patch, apply_patch_text


def test_summarize_patch_detects_file():
    patch = """
    diff --git a/foo.txt b/foo.txt
    index 111..222 100644
    --- a/foo.txt
    +++ b/foo.txt
    @@ -1 +1 @@
    -old
    +new
    """
    summary = summarize_patch(patch)
    assert "foo.txt" in summary["files"]


def test_apply_patch_requires_confirm_for_delete():
    patch = """
    diff --git a/foo.txt b/foo.txt
    deleted file mode 100644
    index 111..000
    --- a/foo.txt
    +++ /dev/null
    """
    result = apply_patch_text(patch, safety_level="low")
    assert result["ok"] is False
    assert result.get("needs_confirmation") is True
