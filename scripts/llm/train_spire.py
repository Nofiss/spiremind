import torch
import os

# Forza PyTorch a non usare Dynamo per le parti problematiche
os.environ["TORCH_COMPILE_DISABLE"] = "1"
# Ottimizzazione per schede Ampere/Ada Lovelace (4070)
torch.set_float32_matmul_precision('high')

from unsloth import FastLanguageModel, get_chat_template
import torch
from trl import SFTTrainer
from transformers import TrainingArguments
from datasets import load_dataset

# 1. Configurazione
max_seq_length = 2048
dtype = None # None per auto-detection (RTX 4070 usa Float16/BFloat16)
load_in_4bit = True

# 2. Carica Modello
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "unsloth/llama-3-8b-bnb-4bit", # Versione pre-quantizzata (velocissima)
    max_seq_length = max_seq_length,
    dtype = dtype,
    load_in_4bit = load_in_4bit,
)

tokenizer = get_chat_template(
    tokenizer,
    chat_template = "llama-3", # Questo imposta il template ufficiale Meta
)

# 3. Aggiungi LoRA adapters
model = FastLanguageModel.get_peft_model(
    model,
    r = 16,
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                      "gate_proj", "up_proj", "down_proj",],
    lora_alpha = 32,
    lora_dropout = 0,
    bias = "none",
    use_gradient_checkpointing = "unsloth",
    random_state = 3407,
    use_rslora = False,
    loftq_config = None,
)

model.config.use_fused_cross_entropy = False

# 4. Prepara il Dataset (adattato ai tuoi file JSONL)
def formatting_prompts_func(examples):
    convs = examples["messages"]
    texts = []
    for conv in convs:
        # Formattazione Llama-3
        t = tokenizer.apply_chat_template(conv, tokenize=False, add_generation_prompt=False)
        texts.append(t)
    return { "text" : texts, }

dataset = load_dataset("json", data_files={"train": "data/llm/train.jsonl"}, split="train")
dataset = dataset.map(formatting_prompts_func, batched = True)

# 5. Training
trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = dataset,
    dataset_text_field = "text",
    max_seq_length = max_seq_length,
    dataset_num_proc = 2,
    args = TrainingArguments(
        per_device_train_batch_size = 2,
        gradient_accumulation_steps = 4,
        warmup_steps = 5,
        max_steps = 60, # Prova con 60 passi per vedere se finisce
        learning_rate = 2e-4,
        fp16 = not torch.cuda.is_bf16_supported(),
        bf16 = torch.cuda.is_bf16_supported(),
        logging_steps = 1,
        optim = "adamw_8bit",
        weight_decay = 0.01,
        lr_scheduler_type = "linear",
        seed = 3407,
        output_dir = "outputs",
    ),
)

trainer.train()

# 6. Salva il modello
model.save_pretrained("spiremind_lora_model")
tokenizer.save_pretrained("spiremind_lora_model")
print("Training completato!")
