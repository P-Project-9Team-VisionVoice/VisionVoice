"""
VisionVoice - Qwen3-VL-8B QLoRA Fine-tuning
DGX Spark (GB10, 128GB unified memory)
"""
import json
import torch
from pathlib import Path
from PIL import Image
from torch.utils.data import Dataset
from transformers import (
    AutoProcessor,
    Qwen3VLForConditionalGeneration,
    TrainingArguments,
    Trainer,
    BitsAndBytesConfig,
)
from peft import LoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training


MODEL_PATH = "/home/devlofi/models/Qwen3-VL-8B-Instruct"
DATA_DIR = Path("/home/devlofi/HyeWon/finetune/dataset")
OUTPUT_DIR = Path("/home/devlofi/HyeWon/finetune/output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("VisionVoice QLoRA Fine-tuning")
print("Base: Qwen3-VL-8B | HW: DGX Spark GB10")
print("=" * 60)


class VisionVoiceDataset(Dataset):
    def __init__(self, json_path, processor, max_length=4096):
        with open(json_path, encoding="utf-8") as f:
            self.data = json.load(f)
        self.processor = processor
        self.max_length = max_length
        self.img_root = DATA_DIR

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        sample = self.data[idx]

        img_path = self.img_root / sample["image"]
        image = Image.open(img_path).convert("RGB")

        convs = sample["conversations"]
        system = next((c["value"] for c in convs if c["from"] == "system"), "")
        human = next((c["value"] for c in convs if c["from"] == "human"), "")
        assistant = next((c["value"] for c in convs if c["from"] == "gpt"), "")

        # <image> 태그 제거 (processor가 별도로 처리)
        human_text = human.replace("<image>\n", "").replace("<image>", "")

        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": str(img_path)},
                    {"type": "text", "text": human_text},
                ],
            },
        ]

        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        text += assistant

        inputs = self.processor(
            text=[text],
            images=[image],
            return_tensors="pt",
        )

        input_ids = inputs["input_ids"].squeeze(0)
        attention_mask = inputs["attention_mask"].squeeze(0)

        # assistant 부분만 loss 계산 (나머지는 -100)
        labels = input_ids.clone()
        # 프롬프트 길이 계산 (assistant 답변 제외한 부분)
        prompt_text = text[: text.rfind(assistant)]
        prompt_inputs = self.processor(
            text=[prompt_text],
            images=[image],
            return_tensors="pt",
        )
        prompt_len = prompt_inputs["input_ids"].shape[1]
        labels[:prompt_len] = -100
        labels[attention_mask == 0] = -100

        result = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "labels": labels,
        }
        if "pixel_values" in inputs:
            result["pixel_values"] = inputs["pixel_values"].squeeze(0)
        if "image_grid_thw" in inputs:
            result["image_grid_thw"] = inputs["image_grid_thw"].squeeze(0)

        return result


def main():
    print("\n[1/4] 모델 & 프로세서 로딩...")
    processor = AutoProcessor.from_pretrained(MODEL_PATH, trust_remote_code=True)
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        MODEL_PATH,
        quantization_config=bnb_config,
        device_map="cuda:0",
        trust_remote_code=True,
        attn_implementation="sdpa",
    )
    model = prepare_model_for_kbit_training(model)
    model.gradient_checkpointing_enable()
    print("  ✓ 모델 로딩 완료 (4-bit QLoRA)")

    print("\n[2/4] LoRA 설정...")
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        # 비전 어텐션 레이어 포함해야 이미지 grounding 성능 향상
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    print("\n[3/4] 데이터셋 로딩...")
    train_dataset = VisionVoiceDataset(DATA_DIR / "train.json", processor)
    val_dataset = VisionVoiceDataset(DATA_DIR / "val.json", processor)
    print(f"  학습: {len(train_dataset)}개 | 검증: {len(val_dataset)}개")

    print("\n[4/4] 학습 시작...")
    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=3,
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=8,   # effective batch = 8
        learning_rate=2e-4,
        warmup_ratio=0.1,
        lr_scheduler_type="cosine",
        bf16=True,
        optim="paged_adamw_8bit",
        logging_steps=5,
        eval_strategy="epoch",
        save_strategy="steps",
        save_steps=10,
        save_total_limit=2,
        load_best_model_at_end=True,
        report_to="none",
        dataloader_num_workers=0,
        remove_unused_columns=False,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
    )

    trainer.train()

    model.save_pretrained(OUTPUT_DIR / "lora_weights")
    print(f"\n✓ LoRA 가중치 저장: {OUTPUT_DIR}/lora_weights")
    print("학습 완료!")


if __name__ == "__main__":
    main()
