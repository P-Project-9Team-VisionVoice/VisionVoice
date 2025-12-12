# backend/ai/agent.py
from .config import USE_MOCK_AGENT
import re
import torch
from PIL import Image
import math

if not USE_MOCK_AGENT:
    from transformers.models.auto.tokenization_auto import AutoTokenizer
    from transformers.models.auto.modeling_auto import AutoModel
    from transformers.models.auto.image_processing_auto import AutoImageProcessor

# Qwen2.5-VL의 Smart Resize 로직 (좌표 변환용)
def smart_resize(height, width, factor=28, min_pixels=3136, max_pixels=12845056):
    if height < factor or width < factor:
        raise ValueError(f"height:{height} or width:{width} must be larger than factor:{factor}")
    elif height * width > max_pixels:
        ratio = math.sqrt(max_pixels / (height * width))
        height = int(height * ratio)
        width = int(width * ratio)
    elif height * width < min_pixels:
        ratio = math.sqrt(min_pixels / (height * width))
        height = int(height * ratio)
        width = int(width * ratio)
    
    height = round(height / factor) * factor
    width = round(width / factor) * factor
    return height, width

class OpenCUAgent:
    def __init__(self):
        if not USE_MOCK_AGENT:
            print("🧠 OpenCUA-7B 모델 로딩 중... (ARM64 최적화: SDPA 가속 ⚡️)")

            model_path = "xlangai/OpenCUA-7B"

            # 2. 토크나이저
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_path, 
                trust_remote_code=True
            )
            
            print(f"🔍 CUDA 상태: available={torch.cuda.is_available()}, device_count={torch.cuda.device_count()}")
            if torch.cuda.is_available():
                print(f"🔍 현재 GPU: {torch.cuda.get_device_name(0)}")
            
            # 3. 모델
            self.model = AutoModel.from_pretrained(
                model_path,
                dtype=torch.bfloat16,
                device_map="auto", 
                trust_remote_code=True,
                attn_implementation="eager",
                low_cpu_mem_usage=True,
            )

            # transformers 라이브러리가 요구하는 키값이 없어서 발생하는 에러를 방지
            if not hasattr(self.model.config, "vision_start_token_id"):
                # 토크나이저에서 ID를 찾거나, Qwen 기본값(151652)을 사용
                v_start = self.tokenizer.convert_tokens_to_ids("<|vision_start|>")
                v_end = self.tokenizer.convert_tokens_to_ids("<|vision_end|>")
                self.model.config.vision_start_token_id = v_start if v_start is not None else 151652
                self.model.config.vision_end_token_id = v_end if v_end is not None else 151653
            
            # 4. 이미지 프로세서
            self.image_processor = AutoImageProcessor.from_pretrained(
                model_path, 
                trust_remote_code=True
            )
            
            print(f"🔧 모델 디바이스: {self.model.device}")
            
        else:
            print("🧠 OpenCUA Mock 모드 대기 중")

    def inference(self, image_path, command, dom_text):
        if USE_MOCK_AGENT:
            return {"action": "click", "x": 0.5, "y": 0.5}, "테스트 완료"

        image = Image.open(image_path).convert('RGB')
        orig_w, orig_h = image.size

        # [1] 시스템 프롬프트
        system_prompt = (
            "You are 'VisionVoice', a helpful AI assistant for visually impaired users. "
            "Your task is to analyze the provided screenshot and web page text to help the user. "
            "1. If the user asks for a description, explain the product, content, or layout in detail using kind Korean. "
            "2. Use the provided 'DOM Text' to understand specific details (price, brand, materials). "
            "3. IMPORTANT: If you see Chinese characters (Kanji/Hanzi) or English terms in the image, DO NOT output them directly. "
            "   Instead, TRANSLATE them into Korean equivalents or explain their meaning in Korean. "
            "   (e.g., instead of '纯棉', say '순면'; instead of '黑色', say '검은색') "
            "4. Output strictly in Korean. "
            "5. If an action is needed, output the Python code."
        )

        # [2] DOM 텍스트 길이 제한 (너무 길면 AI가 헷갈림, 핵심만 전달)
        # 앞부분 1500자 + 뒷부분 500자 (보통 중요한 정보는 위/아래에 많음)
        if len(dom_text) > 2000:
            safe_dom = dom_text[:1500] + "\n...[중략]...\n" + dom_text[-500:]
        else:
            safe_dom = dom_text

        # [3] 유저 프롬프트 구성
        user_prompt_text = f"""
        [Web Page Context / DOM Text]
        {safe_dom}

        [User Command]
        {command}

        Based on the screenshot and the text above, please execute the command or provide the explanation.
        """

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image_path},
                    {"type": "text", "text": user_prompt_text},
                ],
            },
        ]

        text_input = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        
        model_inputs = self.tokenizer([text_input], return_tensors="pt")
        input_ids = model_inputs.input_ids.to(self.model.device)
        attention_mask = model_inputs.attention_mask.to(self.model.device)

        image_info = self.image_processor.preprocess(images=[image], return_tensors="pt")
        pixel_values = image_info['pixel_values'].to(dtype=torch.bfloat16, device=self.model.device)
        grid_thws = image_info['image_grid_thw'].to(self.model.device)

        print(f"⏳ AI 생각 시작... (명령어: {command})")
        print("-" * 30)

        try:
            with torch.no_grad():
                generated_ids = self.model.generate(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    pixel_values=pixel_values,
                    grid_thws=grid_thws,
                    max_new_tokens=128,
                    do_sample=False,
                    pad_token_id=self.tokenizer.eos_token_id,
                    use_cache=True,
                    return_dict_in_generate=False,
                )
        except Exception as e:
            print(f"❌ 추론 에러: {e}")
            import traceback
            traceback.print_exc()
            return {"action": "none"}, "에러 발생"

        print("\n" + "-" * 30)
        
        output_ids = generated_ids[0][len(input_ids[0]):]
        output_text = self.tokenizer.decode(output_ids, skip_special_tokens=True)
        
        return self.parse_output(output_text, orig_w, orig_h)

    def parse_output(self, text, width, height):
        click_pattern = r"click\(x=(\d+),\s*y=(\d+)\)"
        match = re.search(click_pattern, text)

        if match:
            model_x = int(match.group(1))
            model_y = int(match.group(2))
            
            # Smart Resize 역산 적용
            try:
                resized_h, resized_w = smart_resize(height, width)
                
                # 비율 계산
                rel_x = model_x / resized_w
                rel_y = model_y / resized_h
                
                # 원본 좌표로 변환
                abs_x = int(rel_x * width)
                abs_y = int(rel_y * height)
                
                print(f"📐 좌표 변환: {model_x},{model_y} (모델) -> {abs_x},{abs_y} (원본)")

                return {
                    "action": "click", 
                    "x_raw": abs_x, 
                    "y_raw": abs_y,
                    "type": "absolute_smart_resize",
                    "orig_w": width, 
                    "orig_h": height
                }, text
            except Exception as e:
                print(f"⚠️ 좌표 변환 실패: {e}")
                return {"action": "none"}, text

        return {"action": "none"}, text