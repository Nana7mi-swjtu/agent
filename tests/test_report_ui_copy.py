from pathlib import Path


def test_chat_report_copy_describes_drafted_report_and_style_only_regeneration():
    content = Path("frontUI/src/features/chat/ui/ChatMessageItem.vue").read_text(encoding="utf-8")

    assert "证据与素材输入" in content
    assert "正式报告" in content
    assert "仅更换渲染风格重新生成" in content
