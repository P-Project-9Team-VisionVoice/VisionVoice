"""
eval_results JSON → 실제 스크린샷에 bbox 시각화
realscene_qwen3vl / realscene_evocua 결과 공통 사용
"""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

COLORS = {
    "click":    (239, 68, 68),
    "input":    (37, 99, 235),
    "scroll":   (107, 114, 128),
    "explain":  (34, 197, 94),
    "navigate": (168, 85, 247),
}
IMG_BASE = "/home/devlofi/HyeWon/taining_datasets"
ID_TO_IMG = {
    "naver_m_01": "naver_main.png",
    "naver_m_02": "naver_main.png",
    "naver_s_01": "naver_search_input_open.png",
    "musinsa_m_01": "musinsa_main.png",
    "musinsa_d_01": "musinsa_detail_samyang_group_special_T.png",
    "musinsa_d_02": "musinsa_short_sleeve_search.png",
    "youtube_m_01": "youtube_main.png",
    "youtube_m_02": "youtube_main.png",
    "youtube_c_01": "youtube_comments.png",
    "sheet_01":     "spreadsheets_Gradu_list.png",
}

def load_font(size=20):
    for p in [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def resolve_img(r):
    img_path = r.get("image") or ""
    if img_path and Path(img_path).exists():
        return img_path
    fname = ID_TO_IMG.get(r.get("id", ""), "")
    return f"{IMG_BASE}/{fname}"

def draw_result(img_path, result, out_path, font):
    img = Image.open(img_path).convert("RGB")
    W, H = img.size
    draw = ImageDraw.Draw(img)

    action = result.get("predicted_action") or result.get("expected_action")
    bbox_norm = result.get("bbox")
    target = result.get("target", "")
    command = result.get("command", "")
    correct = result.get("action_correct", False)
    speech = result.get("speech", "")

    header_color = (34, 197, 94) if correct else (239, 68, 68)
    status = "✓" if correct else "✗"
    draw.rectangle([0, 0, W, 50], fill=header_color)
    draw.text((8, 8), f"{status} [{action}] {command}", fill="white", font=font)

    if bbox_norm and len(bbox_norm) == 4:
        x1 = round(bbox_norm[0] / 1000 * W)
        y1 = round(bbox_norm[1] / 1000 * H)
        x2 = round(bbox_norm[2] / 1000 * W)
        y2 = round(bbox_norm[3] / 1000 * H)
        color = COLORS.get(action, (245, 158, 11))
        draw.rectangle([x1, y1, x2, y2], outline=color, width=4)
        if target:
            lx, ly, lx2, ly2 = draw.textbbox((0, 0), target, font=font)
            lw, lh = lx2 - lx + 8, ly2 - ly + 6
            label_y = max(52, y1 - lh)
            draw.rectangle([x1, label_y, x1 + lw, label_y + lh], fill=color)
            draw.text((x1 + 4, label_y + 3), target, fill="white", font=font)

    if speech:
        lines = [speech[i:i+60] for i in range(0, min(len(speech), 120), 60)]
        footer_h = 30 + len(lines) * 28
        draw.rectangle([0, H - footer_h, W, H], fill=(30, 30, 30))
        for j, line in enumerate(lines):
            draw.text((8, H - footer_h + 6 + j * 28), line, fill="white", font=font)

    img.save(out_path)

def make_summary(results, out_dir, font, model_name):
    cols = 5
    rows = (len(results) + cols - 1) // cols
    thumb_w, thumb_h = 380, 240
    gap = 8
    total_w = cols * thumb_w + (cols + 1) * gap
    total_h = rows * thumb_h + (rows + 1) * gap + 60

    summary = Image.new("RGB", (total_w, total_h), (245, 245, 245))
    draw = ImageDraw.Draw(summary)

    correct = sum(1 for r in results if r.get("action_correct"))
    avg_t = sum(r.get("elapsed_sec", 0) for r in results) / max(len(results), 1)
    header = f"{model_name}  |  {correct}/{len(results)} ({100*correct//len(results)}%)  |  avg {avg_t:.1f}s"
    draw.rectangle([0, 0, total_w, 55], fill=(30, 30, 30))
    draw.text((12, 14), header, fill="white", font=font)

    for i, r in enumerate(results):
        col = i % cols
        row = i // cols
        x = gap + col * (thumb_w + gap)
        y = 60 + gap + row * (thumb_h + gap)

        img_path = resolve_img(r)
        if Path(img_path).exists():
            thumb = Image.open(img_path).convert("RGB")
            thumb.thumbnail((thumb_w, thumb_h - 40))
            tw, th = thumb.size
            summary.paste(thumb, (x + (thumb_w - tw) // 2, y))

        color = (34, 197, 94) if r.get("action_correct") else (239, 68, 68)
        draw.rectangle([x, y + thumb_h - 38, x + thumb_w, y + thumb_h], fill=color)
        action_got = r.get("predicted_action") or "FAIL"
        draw.text((x + 4, y + thumb_h - 32), f"{r['id']}  {action_got}", fill="white", font=font)

    summary_path = out_dir / "_summary.png"
    summary.save(summary_path)
    print(f"  → 요약 그리드: {summary_path}")

def main(json_path):
    json_path = Path(json_path)
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    model_name = data.get("model", "unknown").replace(" ", "_").replace("-", "_")
    out_dir = Path("/home/devlofi/HyeWon/eval_results") / f"viz_{model_name}"
    out_dir.mkdir(parents=True, exist_ok=True)

    font = load_font(20)
    font_sm = load_font(16)
    results = data.get("results", [])
    print(f"\n시각화: {model_name} ({len(results)}개 시나리오)")
    print(f"출력: {out_dir}/")

    for r in results:
        img_path = resolve_img(r)
        if not Path(img_path).exists():
            print(f"  ✗ 이미지 없음: {r.get('id')} ({img_path})")
            continue
        status = "ok" if r.get("action_correct") else "fail"
        out_path = out_dir / f"{r['id']}_{status}.png"
        draw_result(img_path, r, out_path, font)
        mark = "✓" if r.get("action_correct") else "✗"
        action_got = r.get("predicted_action") or "PARSE_FAIL"
        print(f"  {mark} {r['id']:20s} → {action_got}")

    make_summary(results, out_dir, font_sm, model_name)
    print(f"\n✓ 완료: {out_dir}/")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/devlofi/HyeWon/eval_results/realscene_qwen3vl_20260605_142522.json"
    main(path)
