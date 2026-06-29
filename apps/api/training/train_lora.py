import argparse
import json
import os
import sys
from pathlib import Path

import torch
from datasets import Dataset, load_dataset
from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
)


def format_example(example: dict) -> str:
    instruction = example["instruction"].strip()
    context = example.get("context", "").strip()
    response = example["response"].strip()
    context_block = f"\nContext:\n{context}" if context else ""
    return (
        "<s>[INST] You are MedRAG India. Answer safely, cite supplied context when available, "
        "and avoid diagnosis or prescription for patients.\n\n"
        f"Instruction:\n{instruction}{context_block} [/INST] {response}</s>"
    )


def build_dataset(train_file: str, eval_split: float) -> dict[str, Dataset]:
    dataset = load_dataset("json", data_files=train_file, split="train")
    formatted = dataset.map(lambda row: {"text": format_example(row)})
    if len(formatted) < 2 or eval_split <= 0:
        return {"train": formatted, "test": formatted.select(range(min(len(formatted), 1)))}
    return formatted.train_test_split(test_size=eval_split, seed=42)


def parse_max_memory(value: str) -> dict[int | str, str] | None:
    if not value:
        return None
    raw_value = value.strip()
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        parsed, end_index = decoder.raw_decode(raw_value)
        trailing = raw_value[end_index:].strip()
        if trailing:
            print(
                f"Warning: ignored trailing characters in --max-memory-json: {trailing!r}",
                file=sys.stderr,
            )
    if not isinstance(parsed, dict):
        raise ValueError("--max-memory-json must be a JSON object, for example '{\"0\":\"14GiB\",\"cpu\":\"24GiB\"}'")
    return {int(key) if str(key).isdigit() else key: memory for key, memory in parsed.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="QLoRA fine-tuning for the local MedRAG model.")
    parser.add_argument("--base-model", default="BioMistral/BioMistral-7B")
    parser.add_argument("--train-file", required=True)
    parser.add_argument("--output-dir", default="models/biomistral-medical")
    parser.add_argument("--epochs", type=float, default=3)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--eval-split", type=float, default=0.1)
    parser.add_argument("--lora-r", type=int, default=8)
    parser.add_argument("--lora-alpha", type=int, default=16)
    parser.add_argument("--target-modules", default="q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj")
    parser.add_argument("--max-memory-json", default='{"0":"14GiB","cpu":"24GiB"}')
    parser.add_argument("--hf-cache", default=os.environ.get("HF_HOME", ""))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    if args.hf_cache:
        os.environ["HF_HOME"] = args.hf_cache

    dataset = build_dataset(args.train_file, args.eval_split)
    tokenizer = AutoTokenizer.from_pretrained(
        args.base_model,
        cache_dir=args.hf_cache or None,
        use_fast=True,
        trust_remote_code=True,
    )
    tokenizer.pad_token = tokenizer.pad_token or tokenizer.eos_token
    tokenizer.padding_side = "right"

    def tokenize(batch: dict) -> dict:
        return tokenizer(
            batch["text"],
            truncation=True,
            max_length=args.max_length,
            padding="max_length",
        )

    tokenized = dataset.map(tokenize, batched=True, remove_columns=["text"])
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        cache_dir=args.hf_cache or None,
        quantization_config=quantization,
        device_map="auto",
        max_memory=parse_max_memory(args.max_memory_json),
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model.config.use_cache = False
    lora = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        target_modules=[item.strip() for item in args.target_modules.split(",") if item.strip()],
        lora_dropout=0.05,
        bias="none",
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        eval_strategy="epoch",
        save_strategy="epoch",
        logging_steps=1,
        learning_rate=args.lr,
        fp16=True,
        warmup_ratio=0.03,
        load_best_model_at_end=True,
        report_to=[],
        gradient_checkpointing=True,
        optim="paged_adamw_8bit",
        dataloader_pin_memory=False,
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized["test"],
        data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
    )
    torch.cuda.empty_cache()
    trainer.train()
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    print(f"Adapter saved to: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
