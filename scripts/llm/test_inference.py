from unsloth import FastLanguageModel
import torch

max_seq_length = 2048
load_in_4bit = True

# 1. Carica il modello base + il tuo LoRA adapter
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "spiremind_lora_model", # La cartella dove hai salvato
    max_seq_length = max_seq_length,
    load_in_4bit = load_in_4bit,
)
FastLanguageModel.for_inference(model) # Velocizza l'output del 200%

# 2. Prepara un prompt (Esempio di stato di Slay the Spire)
messages = [
    {"role": "system", "content": "You are a Slay the Spire expert bot. Output only valid game commands."},
    {"role": "user", "content": "--- SLAY THE SPIRE STATE ---\nHERO: 10 HP, 3 Energy.\nENEMIES: Louse(5HP)\nHAND: Strike, Strike, Defend\nVALID COMMANDS: ['play 1 0', 'end']\n----------------------------\nAction:"},
]

inputs = tokenizer.apply_chat_template(
    messages,
    tokenize = True,
    add_generation_prompt = True, # Fondamentale per far rispondere il bot
    return_tensors = "pt",
).to("cuda")

# 3. Genera la risposta
outputs = model.generate(input_ids = inputs, max_new_tokens = 64)
response = tokenizer.batch_decode(outputs)

print(response[0].split("<|start_header_id|>assistant<|end_header_id|>\n\n")[-1])
