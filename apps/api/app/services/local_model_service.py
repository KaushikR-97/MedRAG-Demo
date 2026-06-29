from functools import lru_cache

from app.core.config import settings

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
except Exception:  # pragma: no cover - optional unless local inference is enabled
    AutoModelForCausalLM = None
    AutoTokenizer = None
    BitsAndBytesConfig = None
    torch = None

try:
    from peft import PeftModel
except Exception:  # pragma: no cover - only needed when adapter path is configured
    PeftModel = None


class LocalHuggingFaceModel:
    """Loads BioMistral directly from Hugging Face, with optional LoRA adapter.

    For the POC, set `MODEL_PROVIDER=local_hf` and leave
    `FINETUNED_ADAPTER_PATH` empty. Later, after QLoRA fine-tuning, set the
    adapter path and the same service will attach the PEFT adapter.
    """

    def __init__(self) -> None:
        if AutoTokenizer is None or AutoModelForCausalLM is None or torch is None:
            raise RuntimeError("Install local model dependencies with: pip install -e '.[finetune]'")

        self.tokenizer = AutoTokenizer.from_pretrained(settings.base_model_name, use_fast=True)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        quantization_config = None
        if settings.local_model_load_in_4bit and BitsAndBytesConfig is not None:
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
            )

        model = AutoModelForCausalLM.from_pretrained(
            settings.base_model_name,
            device_map=settings.local_model_device,
            quantization_config=quantization_config,
            torch_dtype=torch.float16,
        )
        self.adapter_path = settings.finetuned_adapter_path.strip()
        if self.adapter_path:
            if PeftModel is None:
                raise RuntimeError("Install PEFT dependencies with: pip install -e '.[finetune]'")
            model = PeftModel.from_pretrained(model, self.adapter_path)
        self.model = model
        self.model.eval()

    @property
    def effective_model_name(self) -> str:
        if self.adapter_path:
            return f"{settings.base_model_name}+{self.adapter_path}"
        return settings.base_model_name

    def generate(self, prompt: str, *, max_new_tokens: int | None = None) -> str:
        max_new_tokens = max_new_tokens or settings.local_model_max_new_tokens
        model_limit = getattr(self.model.config, "max_position_embeddings", 4096) or 4096
        max_new_tokens = min(max_new_tokens, max(64, model_limit - 272))
        available_prompt_tokens = max(256, model_limit - max_new_tokens - 16)
        configured_input_tokens = settings.local_model_max_input_tokens
        max_prompt_tokens = min(configured_input_tokens or available_prompt_tokens, available_prompt_tokens)
        self.tokenizer.truncation_side = "left"
        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=max_prompt_tokens,
        ).to(self.model.device)
        input_len = inputs.input_ids.shape[1]
        with torch.no_grad():
            output = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=0.1,
                do_sample=False,
                repetition_penalty=1.15,
                no_repeat_ngram_size=4,
                pad_token_id=self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            )
        generated_tokens = output[0][input_len:]
        decoded = self.tokenizer.decode(generated_tokens, skip_special_tokens=True)
        return decoded.strip()


@lru_cache
def get_local_huggingface_model() -> LocalHuggingFaceModel:
    return LocalHuggingFaceModel()


get_local_finetuned_model = get_local_huggingface_model
